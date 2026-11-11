import asyncio
import time
import logging
from typing import Dict, Optional
from .call_session import CallSession
from ..schemas.order import Order

logger = logging.getLogger("session_manager")

class SessionManager:
    def __init__(self):
        self._sessions: Dict[str, CallSession] = {}
        self._order_to_session: Dict[str, str] = {}
        self._lock = asyncio.Lock()
        self._cleanup_task: Optional[asyncio.Task] = None

    async def get_or_create_session(self, session_id: str, order: Order, language: str = "en-IN") -> CallSession:
        async with self._lock:
            # Check if this order already has an active session
            existing_sess_id = self._order_to_session.get(order.id)
            if existing_sess_id and existing_sess_id in self._sessions:
                existing_session = self._sessions[existing_sess_id]
                # If still active, reuse or return
                if existing_session.state != "ended" and (time.time() - existing_session.last_activity_at) < 300:
                    logger.info(f"Reusing existing session {existing_sess_id} for order {order.id}")
                    return existing_session

            # Create new session
            session = CallSession(session_id=session_id, order=order, language=language)
            self._sessions[session_id] = session
            self._order_to_session[order.id] = session_id
            return session

    async def get_session(self, session_id: str) -> Optional[CallSession]:
        async with self._lock:
            session = self._sessions.get(session_id)
            if session:
                # Check 5-minute expiry
                if session.state == "ended" and (time.time() - session.ended_at) > 300:
                    return None
            return session

    async def cleanup_loop(self):
        while True:
            try:
                await asyncio.sleep(60)
                now = time.time()
                async with self._lock:
                    to_remove = []
                    for sid, s in self._sessions.items():
                        # If ended and > 5 mins inactive, or abandoned > 10 mins
                        if s.state == "ended" and s.ended_at and (now - s.ended_at) > 300:
                            to_remove.append(sid)
                        elif (now - s.last_activity_at) > 600:
                            to_remove.append(sid)

                    for sid in to_remove:
                        sess = self._sessions.pop(sid, None)
                        if sess and sess.order.id in self._order_to_session:
                            if self._order_to_session[sess.order.id] == sid:
                                del self._order_to_session[sess.order.id]
                        logger.info(f"Cleaned up expired session {sid}")
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning(f"Error in session cleanup: {exc}")

session_manager = SessionManager()

