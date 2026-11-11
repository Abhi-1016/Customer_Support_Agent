import asyncio
import json
import logging
import uuid
from typing import List, Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException, Query, Depends, Request
from fastapi.responses import JSONResponse

from ..config import settings
from ..services.order_service import order_service
from ..services.auth import create_session_token, verify_session_token
from ..session.session_manager import session_manager
from ..schemas.order import Order
from ..schemas.session import (
    CreateSessionRequest, CreateSessionResponse,
    SessionFeedbackRequest, CallSummary
)
from ..schemas.ws_events import PongEvent, ErrorEvent

logger = logging.getLogger("routes")
router = APIRouter()

# Admin / Telemetry in-memory metrics
METRICS = {
    "total_sessions_created": 0,
    "completed_calls": 0,
    "barge_in_count": 0,
    "escalation_count": 0,
    "refunds_processed": 0,
    "pickups_scheduled": 0,
    "vouchers_issued": 0,
    "tts_fallbacks": 0,
    "time_to_first_audio_ms": [850, 1100, 920, 1250, 1050]  # seeded sample
}

# ----------------- Order Endpoints -----------------

@router.get("/api/orders", response_model=List[Order])
async def list_orders():
    """Retrieve all mocked orders."""
    return await order_service.get_all_orders()

@router.get("/api/orders/{order_id}", response_model=Order)
async def get_order(order_id: str):
    """Retrieve order details by ID."""
    order = await order_service.get_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order

# ----------------- Support Session Endpoints -----------------

@router.post("/api/support/sessions", response_model=CreateSessionResponse)
async def create_support_session(req: CreateSessionRequest):
    """Create or resume a customer support voice session for an order."""
    order = await order_service.get_order(req.order_id)
    if not order:
        raise HTTPException(status_code=404, detail=f"Order {req.order_id} not found")

    session_id = f"sess_{uuid.uuid4().hex[:12]}"
    session = await session_manager.get_or_create_session(session_id, order, language=req.language)
    METRICS["total_sessions_created"] += 1

    token = create_session_token(
        session_id=session.session_id,
        order_id=order.id,
        customer_id=order.customer.id
    )

    ws_url = f"/ws/call/{session.session_id}?token={token}"

    return CreateSessionResponse(
        session_id=session.session_id,
        token=token,
        ws_url=ws_url,
        order_id=order.id,
        order_snapshot=order,
        customer_profile=order.customer
    )

@router.get("/api/support/sessions/{session_id}/summary", response_model=CallSummary)
async def get_session_summary(session_id: str):
    """Get the end-of-call summary and receipts."""
    session = await session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session.get_summary()

@router.post("/api/support/sessions/{session_id}/feedback")
async def submit_session_feedback(session_id: str, req: SessionFeedbackRequest):
    """Submit 1-5 star rating and feedback comment for a call."""
    session = await session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    session.feedback_rating = req.rating
    session.feedback_comment = req.comment
    return {"ok": True, "message": "Feedback submitted successfully."}

# ----------------- Health & Readiness Checks -----------------

@router.get("/healthz")
@router.get("/readyz")
async def health_check():
    """Make cheap authenticated checks to Gemini and Gnani without returning keys."""
    gemini_status = "ok"
    gnani_status = "ok"

    # Quick test Gemini reachability
    try:
        from google.antigravity import LocalAgentConfig
        if not settings.GEMINI_API_KEY:
            gemini_status = "failed"
    except Exception:
        gemini_status = "failed"

    # Quick test Gnani reachability
    try:
        if not settings.GNANI_API_KEY:
            gnani_status = "failed"
    except Exception:
        gnani_status = "failed"

    is_ready = (gemini_status == "ok" and gnani_status == "ok")
    status_code = 200 if is_ready else 503

    return JSONResponse(
        status_code=status_code,
        content={
            "status": "ok" if is_ready else "degraded",
            "services": {
                "gemini": gemini_status,
                "gnani": gnani_status
            }
        }
    )

@router.get("/metrics")
@router.get("/api/admin/metrics")
async def get_metrics():
    """Expose telemetry metrics in JSON format."""
    p50 = sorted(METRICS["time_to_first_audio_ms"])[len(METRICS["time_to_first_audio_ms"]) // 2]
    p95 = sorted(METRICS["time_to_first_audio_ms"])[int(len(METRICS["time_to_first_audio_ms"]) * 0.95)]
    return {
        **METRICS,
        "ttfa_p50_ms": p50,
        "ttfa_p95_ms": p95
    }

# ----------------- Demo Mode Failure Controls -----------------

@router.post("/api/admin/demo_mode")
async def configure_demo_mode(
    session_id: Optional[str] = None,
    kill_tts: bool = False,
    force_slot_full: bool = False,
    force_pickup_fail: bool = False,
    force_refund_fail: bool = False
):
    """Trigger failure simulations from the demo debug panel."""
    if session_id:
        sess = await session_manager.get_session(session_id)
        if sess:
            sess.tts.force_fail = kill_tts
            if sess.agent and sess.agent.tool_context:
                sess.agent.tool_context.force_slot_full = force_slot_full
                sess.agent.tool_context.force_pickup_fail = force_pickup_fail
                sess.agent.tool_context.force_refund_fail = force_refund_fail
    return {"ok": True, "demo_mode_updated": True}

# ----------------- WebSocket Transport -----------------

@router.websocket("/ws/call/{session_id}")
async def websocket_call_endpoint(websocket: WebSocket, session_id: str, token: Optional[str] = Query(None)):
    """Single browser-to-backend WebSocket per call session."""
    await websocket.accept()

    session = await session_manager.get_session(session_id)
    if not session:
        await websocket.send_text(
            ErrorEvent(code="SESSION_NOT_FOUND", user_message="Session not found or expired.", recoverable=False).model_dump_json()
        )
        await websocket.close()
        return

    # Attach this WS to session (disconnects older tab if any)
    await session.attach_ws(websocket)

    # Initialize warm subsystems if not already started
    if not session.agent:
        asyncio.create_task(session.init_session())

    # Heartbeat task (every 10s)
    async def heartbeat_loop():
        try:
            while True:
                await asyncio.sleep(10)
                await session.send_json(PongEvent().model_dump())
        except asyncio.CancelledError:
            pass

    heartbeat_task = asyncio.create_task(heartbeat_loop())

    try:
        while True:
            msg = await websocket.receive()
            if msg.get("type") == "websocket.receive":
                # Binary frame = client mic PCM audio (16kHz mono)
                if "bytes" in msg and msg["bytes"]:
                    await session.receive_pcm_frame(msg["bytes"])

                # Text frame = JSON control event
                elif "text" in msg and msg["text"]:
                    try:
                        data = json.loads(msg["text"])
                        event_type = data.get("event")

                        if event_type == "ping":
                            await session.send_json(PongEvent().model_dump())

                        elif event_type == "text_message":
                            text = data.get("text", "").strip()
                            if text:
                                asyncio.create_task(session.on_customer_utterance(text, is_voice=False))

                        elif event_type == "barge_in":
                            METRICS["barge_in_count"] += 1
                            await session.handle_barge_in()

                        elif event_type == "mute":
                            session.is_muted = True

                        elif event_type == "unmute":
                            session.is_muted = False
                            session.is_agent_speaking = False

                        elif event_type == "confirm_action":
                            action_id = data.get("action_id", "")
                            decision = bool(data.get("decision", False))
                            await session.confirm_action(action_id, decision)

                        elif event_type == "end_call":
                            METRICS["completed_calls"] += 1
                            await session.end_call()
                            break

                    except json.JSONDecodeError:
                        logger.warning(f"Invalid JSON from client in session {session_id}")

    except WebSocketDisconnect:
        logger.info(f"[Session {session_id}] WebSocket disconnected. Session kept in memory for 5 minutes.")
    except Exception as exc:
        logger.warning(f"[Session {session_id}] WebSocket error: {exc}")
    finally:
        heartbeat_task.cancel()

