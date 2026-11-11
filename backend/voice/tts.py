import asyncio
import logging
from typing import AsyncIterator, Optional
from gnani.tts import GnaniTTSRealtimeClient, GnaniTTSStreamClient, GnaniTTSClient, AudioConfig
from ..config import settings
from .normalizer import tts_normalize

logger = logging.getLogger("voice_tts")

# Map voices to high-clarity female voice 'Devika'
VOICE_MAP = {
    "sia": "Devika",
    "saanvi": "Devika",
    "devika": "Devika",
    "default": "Devika"
}

class VoiceUnavailableError(Exception):
    """Raised when all TTS modalities (WebSocket, SSE, REST) fail."""
    pass

class TTSPipeline:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.GNANI_API_KEY
        self.model = settings.GNANI_TTS_MODEL
        configured_voice = settings.GNANI_TTS_VOICE
        self.voice = VOICE_MAP.get(configured_voice.lower(), "Devika")
        self.audio_config = AudioConfig(sample_rate=24000)
        self.ws_client = GnaniTTSRealtimeClient(api_key=self.api_key)
        self.sse_client = GnaniTTSStreamClient(api_key=self.api_key)
        self.rest_client = GnaniTTSClient(api_key=self.api_key)
        # Demo simulation flag
        self.force_fail = False

    def get_voice_for_language(self, lang: str) -> str:
        return self.voice

    async def synthesize_stream(self, text: str, lang: str = "en-IN") -> AsyncIterator[bytes]:
        """Synthesize text into raw PCM audio chunks following the failure cascade:
        1. WebSocket (lowest latency)
        2. SSE
        3. REST
        4. Raise VoiceUnavailableError (for fallback to text-only mode)
        """
        if self.force_fail:
            logger.warning("[TTS] Force fail active, triggering fallback cascade.")
            raise VoiceUnavailableError("TTS simulated failure.")

        normalized_text = tts_normalize(text, lang)
        if not normalized_text:
            return

        voice = self.get_voice_for_language(lang)

        # 1. Try WebSocket with explicit 24kHz AudioConfig
        try:
            logger.info(f"[TTS WS] Synthesizing crisp voice '{voice}' at 24kHz: '{normalized_text[:40]}...'")
            got_any = False
            async for chunk in self.ws_client.synthesize(
                normalized_text,
                voice=voice,
                model=self.model,
                language=lang,
                audio_config=self.audio_config,
                speed=1.0
            ):
                got_any = True
                yield chunk
            if got_any:
                return
        except Exception as ws_err:
            logger.warning(f"[TTS WS] Failed ({ws_err}), cascading to SSE...")

        # 2. Try SSE with explicit 24kHz AudioConfig
        try:
            logger.info(f"[TTS SSE] Falling back to SSE: '{normalized_text[:40]}...'")
            loop = asyncio.get_running_loop()
            def run_sse():
                return list(self.sse_client.synthesize_stream(
                    normalized_text,
                    voice=voice,
                    model=self.model,
                    language=lang,
                    audio_config=self.audio_config,
                    speed=1.0
                ))
            chunks = await loop.run_in_executor(None, run_sse)
            if chunks:
                for chunk in chunks:
                    yield chunk
                return
        except Exception as sse_err:
            logger.warning(f"[TTS SSE] Failed ({sse_err}), cascading to REST...")

        # 3. Try REST with explicit 24kHz AudioConfig
        try:
            logger.info(f"[TTS REST] Falling back to REST: '{normalized_text[:40]}...'")
            loop = asyncio.get_running_loop()
            def run_rest():
                return self.rest_client.synthesize(
                    normalized_text,
                    voice=voice,
                    model=self.model,
                    language=lang,
                    audio_config=self.audio_config,
                    speed=1.0
                )
            wav_bytes = await loop.run_in_executor(None, run_rest)
            if wav_bytes:
                # Strip 44-byte WAV header to yield raw PCM
                pcm_bytes = wav_bytes[44:] if len(wav_bytes) > 44 and wav_bytes[:4] == b"RIFF" else wav_bytes
                yield pcm_bytes
                return
        except Exception as rest_err:
            logger.error(f"[TTS REST] Failed ({rest_err}). All TTS modalities exhausted.")

        # 4. If all fail, raise VoiceUnavailableError
        raise VoiceUnavailableError("All TTS channels (WebSocket, SSE, REST) failed.")
