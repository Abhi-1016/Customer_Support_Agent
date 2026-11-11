from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from .order import Order, CustomerProfile

class CreateSessionRequest(BaseModel):
    order_id: str
    language: str = "en-IN"

class CreateSessionResponse(BaseModel):
    session_id: str
    token: str
    ws_url: str
    order_id: str
    order_snapshot: Order
    customer_profile: CustomerProfile

class SessionFeedbackRequest(BaseModel):
    rating: int = Field(..., ge=1, le=5)
    comment: Optional[str] = None

class TranscriptBubble(BaseModel):
    id: str
    speaker: str  # "customer" | "agent" | "system"
    text: str
    timestamp: str
    interrupted: bool = False
    action_chip: Optional[str] = None

class ActionRecord(BaseModel):
    tool: str
    ok: bool
    summary: str
    timestamp: str
    data: Dict[str, Any] = {}

class CallSummary(BaseModel):
    session_id: str
    order_id: str
    resolution: str  # "resolved" | "escalated" | "abandoned"
    reference_ids: Dict[str, str] = {}  # e.g. {"refund_id": "...", "pickup_id": "...", "voucher_code": "...", "ticket_id": "..."}
    actions_taken: List[ActionRecord] = []
    summary_text: str
    rating: Optional[int] = None
    feedback_comment: Optional[str] = None
    duration_seconds: float = 0.0

