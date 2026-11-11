import asyncio
import datetime
import json
import logging
import re
import time
import uuid
from typing import Optional, List, Dict, Any
from fastapi import WebSocket, WebSocketDisconnect

from ..schemas.order import Order, CustomerProfile
from ..schemas.session import TranscriptBubble, ActionRecord, CallSummary
from ..schemas.ws_events import (
    ReadyEvent, StateEvent, UserTranscriptEvent, AgentTextDeltaEvent,
    AgentSentenceEvent, AgentInterruptedEvent, ToolStartedEvent, ToolResultEvent,
    ConfirmationRequestEvent, AudioHeaderEvent, CallSummaryEvent, ErrorEvent, PongEvent,
    InteractiveOptionsEvent, InteractiveOption
)
from ..agent.customer_agent import CustomerSupportAgent
from ..voice.stt import STTPipeline
from ..voice.tts import TTSPipeline, VoiceUnavailableError
from ..voice.chunker import SentenceChunker

logger = logging.getLogger("call_session")

def build_predictive_greeting_prompt(order: Order) -> str:
    """Construct an empathetic, context-rich initial greeting prompt based on order telemetry."""
    cust_name = order.customer.name.split()[0]
    item_name = order.items[0].name if order.items else "your item"

    # 1. Delayed order
    if order.delayed or order.days_delayed > 0:
        last_loc = order.tracking[-1].location if order.tracking else "the logistics hub"
        delay_days = order.days_delayed or 2
        return (
            f"[System: Greet {cust_name}. Notice that their {item_name} is currently delayed by {delay_days} days at {last_loc}. "
            f"Proactively acknowledge the delay in ONE crisp, empathetic sentence and ask if they are inquiring about the delivery timeline or would like to explore options. "
            f"Keep it under 25 words. Do not ask for their order ID.]"
        )

    # 2. In Transit or Out for Delivery
    if order.status == "In Transit":
        last_status = order.tracking[-1].status.lower() if order.tracking else ""
        if "out for delivery" in last_status:
            return (
                f"[System: Greet {cust_name}. Notice that their {item_name} is Out for Delivery today. "
                f"In ONE crisp sentence, tell them the courier is out for delivery and ask if they have specific delivery instructions or need driver details. "
                f"Keep it under 22 words.]"
            )
        else:
            return (
                f"[System: Greet {cust_name}. Notice that their {item_name} is in transit with delivery expected soon. "
                f"In ONE crisp sentence, ask how you can assist with their shipment today. Keep it under 20 words.]"
            )

    # 3. Cancelled Order
    if order.status == "Cancelled":
        if order.already_refunded and order.refund_id:
            return (
                f"[System: Greet {cust_name}. Notice their order for {item_name} is cancelled and refund {order.refund_id} has been processed. "
                f"Proactively ask in ONE sentence if they are checking on refund reflection or need something else. Keep it under 22 words.]"
            )
        return (
            f"[System: Greet {cust_name}. Notice their order for {item_name} is cancelled. "
            f"In ONE sentence, ask how you can assist with their cancelled order today. Keep it under 18 words.]"
        )

    # 4. Delivered Order
    if order.status == "Delivered":
        if order.replacement_requested and order.replacement_id:
            return (
                f"[System: Greet {cust_name}. Notice that a replacement order ({order.replacement_order_id}) has been booked. "
                f"Ask in ONE sentence if they are inquiring about their exchange pickup or have a new question. Keep it under 20 words.]"
            )
        if order.pickup_scheduled:
            return (
                f"[System: Greet {cust_name}. Notice that a return pickup is already scheduled for their {item_name} (ID {order.pickup_scheduled.id}). "
                f"Ask in ONE sentence if they need to check or modify the pickup or have another question. Keep it under 22 words.]"
            )

        del_date_str = "recently"
        if order.delivered_on:
            try:
                dt = datetime.datetime.fromisoformat(order.delivered_on.replace("Z", "+00:00")).date()
                del_date_str = dt.strftime("%B %d")
            except Exception:
                pass

        if not order.returnable:
            return (
                f"[System: Greet {cust_name}. Notice their {item_name} was delivered on {del_date_str}. "
                f"In ONE crisp sentence, ask how you can assist them with this purchase today. Keep it under 18 words.]"
            )

        return (
            f"[System: Greet {cust_name}. Notice their {item_name} was delivered on {del_date_str}. "
            f"In ONE crisp sentence, ask how the item is working for them or if they need assistance with a return or exchange. Keep it under 22 words.]"
        )

    # 5. Processing Order
    return (
        f"[System: Greet {cust_name}. Notice their order for {item_name} is currently being packed. "
        f"In ONE crisp sentence, ask if they would like an update on dispatch or wish to make any changes. Keep it under 20 words.]"
    )

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
        self._tts_lock = asyncio.Lock()
        self.last_agent_text: str = ""

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
            # Generous buffer: give the customer at least 35 seconds to process and answer without interruption
            await asyncio.sleep(35.0)
            if self.state in ["listening", "idle"] and not self.is_agent_speaking and not self.ended_at:
                logger.info(f"[Session {self.session_id}] 35s patient check-in.")
                # Gentle check-in without repeating instructions
                await self._play_tts_phrase("Take your time, I am right here whenever you are ready.")

            # After 35 more seconds (total 70s of complete silence): graceful wrap-up
            await asyncio.sleep(35.0)
            if self.state in ["listening", "idle"] and not self.is_agent_speaking and not self.ended_at:
                logger.info(f"[Session {self.session_id}] 70s silence reached. Ending call gracefully.")
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

        # Predictive context initial greeting tailored to order telemetry
        initial_greeting_prompt = build_predictive_greeting_prompt(self.order)
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
        if "replacement_id" in data:
            self.reference_ids["replacement_id"] = data["replacement_id"]
        if "replacement_order_id" in data:
            self.reference_ids["replacement_order_id"] = data["replacement_order_id"]
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
            prev_agent_utterance = self.last_agent_text

            try:
                if not self.agent:
                    return

                # Create sentence queue for pipelined TTS with deduplication guard
                sentence_queue: asyncio.Queue[Optional[str]] = asyncio.Queue()
                spoken_sentences = set()

                async def tts_worker():
                    while True:
                        sentence = await sentence_queue.get()
                        if sentence is None:
                            break
                        cleaned = sentence.strip()
                        # Deduplication: never speak the exact same instruction/sentence twice in the same turn
                        if cleaned and cleaned not in spoken_sentences:
                            spoken_sentences.add(cleaned)
                            await self._play_tts_phrase(cleaned)
                        sentence_queue.task_done()

                tts_task = asyncio.create_task(tts_worker())

                # Hook text delta to a fresh SentenceChunker instance for this turn
                chunker = SentenceChunker()

                def delta_handler(delta: str):
                    self._on_agent_text_delta(delta)
                    completed = chunker.add_token(delta)
                    for s in completed:
                        sentence_queue.put_nowait(s)

                self.agent.on_text_delta = delta_handler

                try:
                    # Execute LLM turn
                    full_reply_text = await self.agent.chat_turn(utterance)

                    # Flush remaining sentence
                    for s in chunker.flush():
                        sentence_queue.put_nowait(s)

                    # Signal end of sentences
                    await sentence_queue.put(None)
                    await tts_task

                    # Fallback guard: ensure 100% of generated responses are spoken aloud
                    if not spoken_sentences and full_reply_text.strip():
                        logger.info(f"[Session {self.session_id}] Fallback guard: synthesizing complete reply text.")
                        await self._play_tts_phrase(full_reply_text.strip())

                finally:
                    # Always restore base delta handler so closures never nest across turns
                    self.agent.on_text_delta = self._on_agent_text_delta

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
                    self.last_agent_text = full_reply_text
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

                # Multimodal In-Call UI Chips (P1): evaluate if contextual options should be presented
                if not is_system_prompt and full_reply_text:
                    await self._evaluate_interactive_options(full_reply_text)

                # Automatic conversation closure and feedback trigger
                if not is_system_prompt and full_reply_text and self._check_should_close(utterance, prev_agent_utterance, full_reply_text):
                    logger.info(f"[Session {self.session_id}] Customer indicated closure ('{utterance}'). Closing session automatically.")
                    # Wait briefly so that client's speakers finish outputting the goodbye audio
                    await asyncio.sleep(2.5)
                    await self.end_call()

    async def _evaluate_interactive_options(self, reply_text: str):
        """Evaluate agent response text to present 1-tap interactive UI chips on the frontend."""
        clean = reply_text.lower()

        # 1. Resolution preference: Replacement vs Refund
        if any(k in clean for k in ["replacement", "refund"]) and any(k in clean for k in ["prefer", "would you like", "choose", "option"]):
            amount_str = f"₹{int(self.order.payment.amount)}"
            await self.send_json(InteractiveOptionsEvent(
                kind="resolution",
                title="Select Your Preferred Resolution",
                options=[
                    InteractiveOption(
                        id="opt_replace",
                        label="Instant Replacement",
                        sublabel="Free replacement item + hand-to-hand exchange",
                        value="I prefer an instant replacement."
                    ),
                    InteractiveOption(
                        id="opt_refund",
                        label="Full Refund",
                        sublabel=f"{amount_str} returned to your original payment method",
                        value="I prefer a full refund."
                    )
                ]
            ).model_dump())
            return

        # 2. Address confirmation
        if "registered address" in clean or ("address" in clean and ("pick" in clean or "registered" in clean or "pick it up" in clean)):
            addr = self.order.customer.address
            await self.send_json(InteractiveOptionsEvent(
                kind="address",
                title="Confirm Pickup & Delivery Address",
                options=[
                    InteractiveOption(
                        id="opt_reg_addr",
                        label="Use Registered Address",
                        sublabel=addr,
                        value=f"Yes, please pick it up from my registered address: {addr}."
                    ),
                    InteractiveOption(
                        id="opt_diff_addr",
                        label="Use a Different Address",
                        sublabel="Specify alternate location for pickup",
                        value="I want to use a different address."
                    )
                ]
            ).model_dump())
            return

        # 3. Slot / Date selection
        if any(k in clean for k in ["preferred pickup", "time slot", "pickup day", "morning or afternoon", "pickup slot", "day and time"]):
            await self.send_json(InteractiveOptionsEvent(
                kind="slot",
                title="Choose Pickup Time Slot",
                options=[
                    InteractiveOption(
                        id="opt_tmrw_morn",
                        label="Tomorrow Morning",
                        sublabel="Thursday, Nov 12 • 9:00 AM - 12:00 PM",
                        value="Tomorrow morning works best for me."
                    ),
                    InteractiveOption(
                        id="opt_tmrw_aft",
                        label="Tomorrow Afternoon",
                        sublabel="Thursday, Nov 12 • 12:00 PM - 4:00 PM",
                        value="Tomorrow afternoon works best for me."
                    ),
                    InteractiveOption(
                        id="opt_friday_morn",
                        label="Friday Morning",
                        sublabel="Friday, Nov 13 • 9:00 AM - 12:00 PM",
                        value="Friday morning works best for me."
                    )
                ]
            ).model_dump())
            return

    def _check_should_close(self, user_text: str, prev_agent_text: str, current_agent_reply: str) -> bool:
        """Detect if customer says 'that is not required' / 'no that's all' and call should automatically close."""
        clean_user = re.sub(r'[^\w\s]', '', user_text.lower()).strip()
        user_words = set(clean_user.split())

        # If user is asking for an actual new action or topic, do not close
        action_keywords = {"cancel", "refund", "return", "status", "change", "pickup", "delivery", "track", "address", "slot", "when", "how", "item"}
        if action_keywords.intersection(user_words):
            return False

        closure_phrases = [
            "not required", "that is not required", "thats not required", "not needed",
            "that is not needed", "nothing else", "no that is all", "no thats all",
            "no that will be all", "no thanks", "no thank you", "thats all", "that is all",
            "im good", "i am good", "all good", "all set", "nope", "that's it", "thats it",
            "nothing more", "nahin", "nahi", "kuch nahi", "bas yahi tha", "bas itna hi",
            "bye", "goodbye", "good bye"
        ]
        is_closure_input = any(p in clean_user for p in closure_phrases) or clean_user in ["no", "nope", "nah", "na"]

        prev_asked_else = any(p in prev_agent_text.lower() for p in [
            "anything else", "anything that i can help", "anything i can help",
            "anything i can assist", "help you with today", "aur koi sahayata",
            "can i help with", "can i assist with"
        ])

        agent_said_farewell = any(w in current_agent_reply.lower() for w in [
            "goodbye", "good bye", "have a wonderful day", "have a great day",
            "take care", "alvida", "thank you for contacting", "thank you for reaching out"
        ])

        return (is_closure_input and prev_asked_else) or (is_closure_input and agent_said_farewell) or agent_said_farewell

    async def _play_tts_phrase(self, phrase: str):
        """Synthesize and stream audio chunks for a single sentence."""
        if not phrase or not phrase.strip():
            return

        async with self._tts_lock:
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
                chunk_count = 0
                async for chunk in self.tts.synthesize_stream(phrase, lang=self.language):
                    if not self.is_agent_speaking:
                        break
                    chunk_count += 1
                    await self.send_binary(chunk)
                    # Roughly estimate spoken characters
                    self.spoken_chars_estimate = min(len(phrase), self.spoken_chars_estimate + 10)
                logger.info(f"[Session {self.session_id}] Spoken phrase emitted ({chunk_count} chunks): '{phrase[:50]}...'")
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
        if self.is_muted or self.state != "listening" or self.is_agent_speaking:
            return
        self.last_activity_at = time.time()
        if self.stt:
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
        if "replacement_id" in self.reference_ids:
            summary_parts.append(f"Instant replacement confirmed (ID: {self.reference_ids['replacement_id']}, Order: {self.reference_ids.get('replacement_order_id', 'Pending')})")
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

