import asyncio
import logging
from typing import AsyncIterator, Optional, Callable
from gnani.stt import (
    GnaniSTTStreamClient,
    StreamTranscriptEvent,
    StreamConnectedEvent,
    StreamErrorEvent,
    StreamConnectionError
)
from ..config import settings

logger = logging.getLogger("voice_stt")

class STTPipeline:
    def __init__(self, language_code: str = "en-IN", on_transcript: Optional[Callable[[str, bool], None]] = None):
        self.language_code = language_code
        self.api_key = settings.GNANI_API_KEY
        self.model = settings.GNANI_STT_MODEL
        self.client: Optional[GnaniSTTStreamClient] = None
        self.is_connected = False
        self.on_transcript = on_transcript
        self._listen_task: Optional[asyncio.Task] = None
        self._closing = False
        self.force_fail = False

        # Grace window buffer (600 - 800 ms)
        self.grace_ms = 700
        self._pending_transcript = ""
        self._grace_timer_task: Optional[asyncio.Task] = None

    async def connect(self, retry_count: int = 2) -> bool:
        """Connect to Gnani STT with up to retry_count retries."""
        if self.force_fail:
            logger.warning("[STT] Force fail flag is set.")
            return False

        for attempt in range(1, retry_count + 1):
            try:
                logger.info(f"[STT] Connecting to Gnani STT (attempt {attempt}/{retry_count})...")
                self.client = GnaniSTTStreamClient(
                    api_key=self.api_key,
                    language_code=self.language_code,
                    model=self.model,
                    sample_rate=16000,
                    enable_itn=True
                )
                conn = await self.client.connect()
                logger.info(f"[STT] Connected successfully: {conn.message}")
                self.is_connected = True
                self._listen_task = asyncio.create_task(self._listen_loop())
                return True
            except Exception as exc:
                logger.warning(f"[STT] Connect attempt {attempt} failed: {exc}")
                await asyncio.sleep(0.5)

        logger.error("[STT] All STT connection attempts failed.")
        return False

    async def send_audio(self, pcm_frame: bytes) -> None:
        """Send a 1,024-byte 16kHz PCM frame."""
        if not self.is_connected or not self.client:
            return
        try:
            await self.client.send_audio(pcm_frame)
        except Exception as exc:
            logger.warning(f"[STT] Failed to send audio: {exc}")

    async def _listen_loop(self):
        if not self.client:
            return
        try:
            async for event in self.client.events():
                if self._closing:
                    break
                if isinstance(event, StreamTranscriptEvent):
                    text = event.text.strip()
                    if text:
                        logger.info(f"[STT Transcript]: '{text}'")
                        self._handle_transcript_with_grace(text)
                elif isinstance(event, StreamErrorEvent):
                    logger.error(f"[STT Error]: {event.message}")
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.warning(f"[STT] Listen loop exited with error: {exc}")
        finally:
            self.is_connected = False

    def _handle_transcript_with_grace(self, text: str):
        if self._grace_timer_task and not self._grace_timer_task.done():
            self._grace_timer_task.cancel()

        if self._pending_transcript:
            self._pending_transcript += " " + text
        else:
            self._pending_transcript = text

        self._grace_timer_task = asyncio.create_task(self._wait_grace_and_emit())

    async def _wait_grace_and_emit(self):
        try:
            await asyncio.sleep(self.grace_ms / 1000.0)
            merged_text = self._pending_transcript.strip()
            self._pending_transcript = ""
            if merged_text and self.on_transcript:
                self.on_transcript(merged_text, True)
        except asyncio.CancelledError:
            pass

    async def close(self):
        self._closing = True
        if self._grace_timer_task:
            self._grace_timer_task.cancel()
        if self._listen_task:
            self._listen_task.cancel()
        if self.client:
            try:
                await self.client.close()
            except Exception:
                pass
        self.is_connected = False

