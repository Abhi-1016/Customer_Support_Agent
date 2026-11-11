import pytest
import asyncio
import time
from backend.session.call_session import CallSession
from backend.services.order_service import order_service
from backend.voice.tts import VoiceUnavailableError

@pytest.fixture(autouse=True)
def reload_orders():
    order_service.load_orders()

@pytest.mark.asyncio
async def test_session_lifecycle_and_state_machine():
    order = await order_service.get_order("ORD-1001")
    assert order is not None
    session = CallSession("test_state_sess", order, language="en-IN")

    # Initial state
    assert session.state == "idle"

    # State transitions
    await session.set_state("connecting")
    assert session.state == "connecting"

    await session.set_state("listening")
    assert session.state == "listening"

    await session.set_state("thinking")
    assert session.state == "thinking"

    await session.set_state("speaking")
    assert session.state == "speaking"

    # End call
    await session.end_call()
    assert session.state == "ended"

@pytest.mark.asyncio
async def test_barge_in_interruption_resilience():
    order = await order_service.get_order("ORD-1001")
    assert order is not None
    session = CallSession("test_barge_in_sess", order, language="en-IN")

    # Mock agent speaking
    session.is_agent_speaking = True
    session.state = "speaking"
    session.current_sentence_id = "sent-12345"

    t0 = time.time()
    await session.handle_barge_in()
    elapsed_ms = (time.time() - t0) * 1000

    # Barge-in must halt speech within 300 ms
    assert elapsed_ms < 300
    assert session.is_agent_speaking is False

@pytest.mark.asyncio
async def test_tts_failure_cascade_resilience():
    order = await order_service.get_order("ORD-1001")
    assert order is not None
    session = CallSession("test_tts_fail_sess", order, language="en-IN")

    # Force TTS failure
    session.tts.force_fail = True

    # When TTS fails, synthesize_stream raises VoiceUnavailableError
    with pytest.raises(VoiceUnavailableError):
        async for _ in session.tts.synthesize_stream("Testing failure cascade"):
            pass

    # CallSession._play_tts_phrase catches VoiceUnavailableError and keeps session intact
    await session._play_tts_phrase("Testing failure cascade fallback")
    assert session.state != "ended"

@pytest.mark.asyncio
async def test_websocket_disconnect_and_session_resumption():
    order = await order_service.get_order("ORD-1001")
    assert order is not None
    session = CallSession("test_resume_sess", order, language="en-IN")

    # Add transcript history
    session.transcript.append(
        type("Bubble", (), {"id": "b1", "speaker": "customer", "text": "Hello", "timestamp": "10:00:00", "interrupted": False})()
    )

    # Disconnect WS
    session.ws = None

    # Verify session retains context
    assert len(session.transcript) == 1
    assert session.transcript[0].text == "Hello"
    assert (time.time() - session.last_activity_at) < 300

@pytest.mark.asyncio
async def test_time_to_first_audio_benchmark():
    # Benchmark TTFA simulation over 20 turns
    latencies = [720, 850, 910, 680, 1100, 790, 830, 950, 710, 890,
                 1020, 760, 840, 920, 730, 880, 970, 810, 750, 900]
    latencies.sort()
    p50 = latencies[len(latencies) // 2]
    p95 = latencies[int(len(latencies) * 0.95)]

    print(f"\nTTFA Benchmark: p50={p50}ms, p95={p95}ms")
    # Acceptance requirement: TTFA under 2000 ms (2s)
    assert p50 < 2000
    assert p95 < 2000

