import asyncio
import json
import logging
import time
import uuid
from typing import Optional, List, Dict, Any
from fastapi import WebSocket, WebSocketDisconnect

from ..schemas.order import Order, CustomerProfile
from ..schemas.session import TranscriptBubble, ActionRecord, CallSummary
from ..schemas.ws_events import (
    ReadyEvent, StateEvent, UserTranscriptEvent, AgentTextDeltaEvent,
    AgentSentenceEvent, AgentInterruptedEvent, ToolStartedEvent, ToolResultEvent,
    ConfirmationRequestEvent, AudioHeaderEvent, CallSummaryEvent, ErrorEvent, PongEvent
)
from ..agent.customer_agent import CustomerSupportAgent
from ..voice.stt import STTPipeline
from ..voice.tts import TTSPipeline, VoiceUnavailableError
from ..voice.chunker import SentenceChunker

logger = logging.getLogger("call_session")

class CallSession:
    def __init__(self, session_id: str, order: Order, language: str = "en-IN"):
        self.session_id = session_id
        self.order = order
        self.language = language
        self.state: str = "idle"
        self.created_at = time.time()
        self.last_activity_at = time.time()
        self.ended_at: Optional[float] = None

        # Client WebSocket
        self.ws: Optional[WebSocket] = None
        self._ws_lock = asyncio.Lock()

        # Transcript & actions
        self.transcript: List[TranscriptBubble] = []
        self.actions_taken: List[ActionRecord] = []
        self.reference_ids: Dict[str, str] = {}
        self.feedback_rating: Optional[int] = None
        self.feedback_comment: Optional[str] = None

        # Subsystems
        self.chunker = SentenceChunker()
        self.tts = TTSPipeline()
        self.stt: Optional[STTPipeline] = None
        self.agent: Optional[CustomerSupportAgent] = None

        # Audio & streaming controls
        self.is_muted = False
        self.is_agent_speaking = False
        self.current_sentence_id = ""
        self.current_sentence_text = ""
        self.spoken_chars_estimate = 0
        self._current_tts_task: Optional[asyncio.Task] = None
        self._audio_queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=100)

        # Silence timer tasks
        self._silence_task: Optional[asyncio.Task] = None
        self.silence_warnings_given = 0

        # Turn concurrency lock
        self._turn_lock = asyncio.Lock()

    async def attach_ws(self, websocket: WebSocket):
        """Attach a WebSocket connection. If another WS was attached, disconnect it cleanly."""
        async with self._ws_lock:
            if self.ws and self.ws != websocket:
                try:
                    await self.ws.send_text(
                        ErrorEvent(code="SESSION_TAKEOVER", user_message="Another tab connected to this session.", recoverable=False).model_dump_json()
                    )
                    await self.ws.close()
                except Exception:
                    pass
            self.ws = websocket
            self.last_activity_at = time.time()

    async def send_json(self, event_data: dict | str):
        """Send a JSON event to client safely."""
        async with self._ws_lock:
            if self.ws:
                try:
                    payload = event_data if isinstance(event_data, str) else json.dumps(event_data)
                    await self.ws.send_text(payload)
                except Exception as exc:
                    logger.warning(f"[Session {self.session_id}] Error sending JSON: {exc}")

    async def send_binary(self, data: bytes):
        """Send raw binary audio data to client safely."""
        async with self._ws_lock:
            if self.ws:
                try:
                    await self.ws.send_bytes(data)
                except Exception as exc:
                    logger.warning(f"[Session {self.session_id}] Error sending binary: {exc}")

    async def set_state(self, new_state: str):
        self.state = new_state
        await self.send_json(StateEvent(state=new_state).model_dump())

    def reset_silence_timer(self):
        """Reset customer silence timer."""
        if self._silence_task and not self._silence_task.done():
            self._silence_task.cancel()
        self.silence_warnings_given = 0
        self._silence_task = asyncio.create_task(self._silence_watchdog())

    async def _silence_watchdog(self):
        try:
            # Generous buffer: give the customer at least 25 seconds to process and answer without interruption
            await asyncio.sleep(25.0)
            if self.state in ["listening", "idle"] and not self.is_agent_speaking and not self.ended_at:
                logger.info(f"[Session {self.session_id}] 25s patient check-in.")
                # Gentle check-in without repeating instructions
                await self._play_tts_phrase("Take your time, I am right here whenever you are ready.")

            # After 35 more seconds (total 60s of complete silence): graceful wrap-up
            await asyncio.sleep(35.0)
            if self.state in ["listening", "idle"] and not self.is_agent_speaking and not self.ended_at:
                logger.info(f"[Session {self.session_id}] 60s silence reached. Ending call gracefully.")
                await self._play_tts_phrase("Since I have not heard from you, I will let you go for now. You can call back anytime. Goodbye!")
                await self.end_call()
        except asyncio.CancelledError:
            pass

    async def init_session(self):
        """Initialize Agent, STT, and warm connections."""
        await self.set_state("connecting")

        # 1. Initialize Agent
        self.agent = CustomerSupportAgent(
            session_id=self.session_id,
            order=self.order,
            on_text_delta=self._on_agent_text_delta,
            on_tool_started=self._on_agent_tool_started,
            on_tool_result=self._on_agent_tool_result,
            on_filler=self._on_agent_filler,
            language=self.language
        )
        await self.agent.start()

        # 2. Initialize STT
        self.stt = STTPipeline(
            language_code=self.language,
            on_transcript=self.on_customer_speech_transcript
        )
        stt_ok = await self.stt.connect()
        if not stt_ok:
            logger.warning(f"[Session {self.session_id}] STT connect failed, continuing in text fallback mode.")
            await self.send_json(ErrorEvent(
                code="STT_DEGRADED",
                user_message="Voice transcription is temporarily unavailable. You can continue speaking or typing.",
                recoverable=True
            ).model_dump())

        # Notify ready
        await self.send_json(ReadyEvent(session_id=self.session_id).model_dump())
        await self.set_state("listening")

        # Warm start initial greeting - crisp 1-sentence opening
        cust_first_name = self.order.customer.name.split()[0]
        item_name = self.order.items[0].name if self.order.items else "your item"
        initial_greeting_prompt = f"[System: Greet {cust_first_name} in exactly ONE short, friendly sentence about their {item_name} and ask how you can help. Keep it under 20 words. Do not repeat order details.]"
        asyncio.create_task(self.process_agent_turn(initial_greeting_prompt, is_system_prompt=True))
        self.reset_silence_timer()

    def _on_agent_text_delta(self, delta: str):
        asyncio.create_task(self.send_json(AgentTextDeltaEvent(delta=delta).model_dump()))

    def _on_agent_tool_started(self, tool_name: str, args: dict):
        display_name = tool_name.replace("_", " ").capitalize()
        asyncio.create_task(self.send_json(ToolStartedEvent(name=f"Checking {display_name}...").model_dump()))

    def _on_agent_tool_result(self, tool_name: str, ok: bool, summary: str, data: dict):
        record = ActionRecord(
            tool=tool_name,
            ok=ok,
            summary=summary,
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            data=data
        )
        self.actions_taken.append(record)

        # Track references
        if "refund_id" in data:
            self.reference_ids["refund_id"] = data["refund_id"]
        if "pickup_id" in data:
            self.reference_ids["pickup_id"] = data["pickup_id"]
        if "voucher_code" in data:
            self.reference_ids["voucher_code"] = data["voucher_code"]
        if "ticket_id" in data:
            self.reference_ids["ticket_id"] = data["ticket_id"]

        asyncio.create_task(self.send_json(ToolResultEvent(name=tool_name, ok=ok, summary=summary).model_dump()))

    def _on_agent_filler(self, phrase: str):
        # Speak filler phrase
        asyncio.create_task(self._play_tts_phrase(phrase))

    def on_customer_speech_transcript(self, text: str, final: bool):
        """Called by STT when customer speech is transcribed."""
        if not text:
            return
        logger.info(f"[Session {self.session_id}] Final speech transcript: '{text}'")
        asyncio.create_task(self.on_customer_utterance(text, is_voice=True))

    async def on_customer_utterance(self, text: str, is_voice: bool = True):
        """Handle user input (either spoken via STT or typed in chat input)."""
        self.last_activity_at = time.time()
        self.reset_silence_timer()

        # Check for barge-in: customer spoke/typed while agent was speaking
        if self.is_agent_speaking:
            await self.handle_barge_in()

        # Emit user transcript to frontend
        bubble = TranscriptBubble(
            id=f"msg-{uuid.uuid4().hex[:6]}",
            speaker="customer",
            text=text,
            timestamp=time.strftime("%H:%M:%S", time.localtime()),
            interrupted=False
        )
        self.transcript.append(bubble)
        await self.send_json(UserTranscriptEvent(text=text, final=True).model_dump())

        # Process through agent turn
        await self.process_agent_turn(text, is_system_prompt=False)

    async def handle_barge_in(self):
        """Immediate barge-in interruption: cancel TTS and cancel in-flight agent turn."""
        logger.info(f"[Session {self.session_id}] Barge-in detected. Halting agent speech.")
        self.is_agent_speaking = False

        # Mark bubble as interrupted
        if self.current_sentence_id and self.transcript:
            for b in reversed(self.transcript):
                if b.speaker == "agent" and not b.interrupted:
                    b.interrupted = True
                    break

        # Cancel TTS task
        if self._current_tts_task and not self._current_tts_task.done():
            self._current_tts_task.cancel()

        # Cancel agent LLM stream
        if self.agent:
            await self.agent.interrupt()

        # Send agent_interrupted event to client
        await self.send_json(AgentInterruptedEvent(
            id=self.current_sentence_id or "prev",
            spoken_up_to=self.spoken_chars_estimate
        ).model_dump())

    async def process_agent_turn(self, utterance: str, is_system_prompt: bool = False):
        """Process turn through customer agent and stream completed sentences to TTS."""
        async with self._turn_lock:
            await self.set_state("thinking")
            agent_bubble_id = f"msg-{uuid.uuid4().hex[:6]}"
            full_reply_text = ""

            try:
                if not self.agent:
                    return

                # Create sentence queue for pipelined TTS
                sentence_queue: asyncio.Queue[Optional[str]] = asyncio.Queue()

                async def tts_worker():
                    while True:
                        sentence = await sentence_queue.get()
                        if sentence is None:
                            break
                        await self._play_tts_phrase(sentence)
                        sentence_queue.task_done()

                tts_task = asyncio.create_task(tts_worker())

                # Hook text delta to chunker
                original_on_delta = self.agent.on_text_delta

                def delta_handler(delta: str):
                    if original_on_delta:
                        original_on_delta(delta)
                    completed = self.chunker.add_token(delta)
                    for s in completed:
                        sentence_queue.put_nowait(s)

                self.agent.on_text_delta = delta_handler

                # Execute LLM turn
                full_reply_text = await self.agent.chat_turn(utterance)

                # Flush remaining sentence
                for s in self.chunker.flush():
                    sentence_queue.put_nowait(s)

                # Signal end of sentences
                await sentence_queue.put(None)
                await tts_task

            except asyncio.CancelledError:
                logger.info(f"[Session {self.session_id}] Turn was cancelled.")
            except Exception as exc:
                logger.error(f"[Session {self.session_id}] Error in agent turn: {exc}")
                await self.send_json(ErrorEvent(
                    code="AGENT_ERROR",
                    user_message="I experienced a temporary glitch. Please try again or type your message.",
                    recoverable=True
                ).model_dump())
            finally:
                if full_reply_text:
                    bubble = TranscriptBubble(
                        id=agent_bubble_id,
                        speaker="agent",
                        text=full_reply_text,
                        timestamp=time.strftime("%H:%M:%S", time.localtime()),
                        interrupted=False
                    )
                    self.transcript.append(bubble)

                self.is_agent_speaking = False
                self.is_muted = False
                await self.set_state("listening")

    async def _play_tts_phrase(self, phrase: str):
        """Synthesize and stream audio chunks for a single sentence."""
        if not phrase or not phrase.strip():
            return

        self.current_sentence_id = f"sent-{uuid.uuid4().hex[:6]}"
        self.current_sentence_text = phrase
        self.spoken_chars_estimate = 0
        self.is_agent_speaking = True
        await self.set_state("speaking")

        # Emit sentence event to client
        await self.send_json(AgentSentenceEvent(id=self.current_sentence_id, text=phrase).model_dump())

        # Emit audio header
        await self.send_json(AudioHeaderEvent(
            format="pcm16",
            sample_rate=24000,
            sentence_id=self.current_sentence_id
        ).model_dump())

        try:
            async for chunk in self.tts.synthesize_stream(phrase, lang=self.language):
                if not self.is_agent_speaking:
                    break
                await self.send_binary(chunk)
                # Roughly estimate spoken characters
                self.spoken_chars_estimate = min(len(phrase), self.spoken_chars_estimate + 10)
        except VoiceUnavailableError:
            logger.warning(f"[Session {self.session_id}] Voice is unavailable, continuing in text.")
            await self.send_json(ErrorEvent(
                code="VOICE_UNAVAILABLE",
                user_message="Voice is currently unavailable; continuing in typed text.",
                recoverable=True
            ).model_dump())
        except asyncio.CancelledError:
            logger.info(f"[Session {self.session_id}] TTS playback cancelled for sentence {self.current_sentence_id}.")
        except Exception as exc:
            logger.warning(f"[Session {self.session_id}] TTS error: {exc}")

    async def receive_pcm_frame(self, pcm_frame: bytes):
        """Receive mic frame from client and forward to STT."""
        if self.is_muted or self.state == "ended" or self.is_agent_speaking:
            return
        self.last_activity_at = time.time()
        if self.stt and self.stt.is_connected:
            await self.stt.send_audio(pcm_frame)

    async def confirm_action(self, action_id: str, decision: bool):
        """Handle action confirmation from confirmation card."""
        user_text = "Yes, please proceed." if decision else "No, I would like to change something."
        await self.on_customer_utterance(user_text, is_voice=False)

    async def end_call(self):
        """End the call session and generate summary."""
        self.ended_at = time.time()
        await self.set_state("ended")

        if self._silence_task:
            self._silence_task.cancel()
        if self.stt:
            await self.stt.close()
        if self.agent:
            await self.agent.stop()

        summary = self.get_summary()
        await self.send_json(CallSummaryEvent(summary=summary.model_dump()).model_dump())

    def get_summary(self) -> CallSummary:
        resolution = "resolved"
        if "ticket_id" in self.reference_ids:
            resolution = "escalated"
        elif not self.actions_taken:
            resolution = "abandoned"

        summary_parts = []
        if "refund_id" in self.reference_ids:
            summary_parts.append(f"Refund initiated (ID: {self.reference_ids['refund_id']})")
        if "pickup_id" in self.reference_ids:
            summary_parts.append(f"Return pickup scheduled (ID: {self.reference_ids['pickup_id']})")
        if "voucher_code" in self.reference_ids:
            summary_parts.append(f"Compensation voucher issued (Code: {self.reference_ids['voucher_code']})")
        if "ticket_id" in self.reference_ids:
            summary_parts.append(f"Escalated to human support (Ticket: {self.reference_ids['ticket_id']})")

        if not summary_parts:
            summary_parts.append("Inquiry answered without changes to order.")

        summary_text = " • ".join(summary_parts)
        duration = (self.ended_at or time.time()) - self.created_at

        return CallSummary(
            session_id=self.session_id,
            order_id=self.order.id,
            resolution=resolution,
            reference_ids=self.reference_ids,
            actions_taken=self.actions_taken,
            summary_text=summary_text,
            rating=self.feedback_rating,
            feedback_comment=self.feedback_comment,
            duration_seconds=round(duration, 1)
        )

