import jwt
import time
from typing import Optional, Dict, Any
from ..config import settings

ALGORITHM = "HS256"

def create_session_token(session_id: str, order_id: str, customer_id: str) -> str:
    now = int(time.time())
    payload = {
        "sub": session_id,
        "order_id": order_id,
        "customer_id": customer_id,
        "iat": now,
        "exp": now + 600  # 10 minutes expiry
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=ALGORITHM)

def verify_session_token(token: str) -> Optional[Dict[str, Any]]:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[ALGORITHM])
        return payload
    except (jwt.PyJWTError, Exception):
        return None

