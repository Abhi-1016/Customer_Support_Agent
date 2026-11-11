from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

class CustomerProfile(BaseModel):
    id: str
    name: str
    phone: str
    email: str
    address: str

class OrderItem(BaseModel):
    id: str
    name: str
    quantity: int
    price: float
    image: str
    returnable: bool = True

class TrackingEvent(BaseModel):
    status: str
    location: str
    timestamp: str

class PaymentSummary(BaseModel):
    method: str
    amount: float
    subtotal: float
    shipping: float = 0.0
    tax: float = 0.0
    already_refunded: bool = False
    refund_id: Optional[str] = None

class PickupDetails(BaseModel):
    id: str
    date: str
    window: str
    address: str
    courier_note: Optional[str] = None

class EscalationTicket(BaseModel):
    ticket_id: str
    summary: str
    priority: str
    reason_code: str
    callback_eta: str
    created_at: str

class Order(BaseModel):
    id: str
    customer: CustomerProfile
    items: List[OrderItem]
    status: str  # Processing, In Transit, Delivered, Cancelled
    placed_at: str
    delivered_on: Optional[str] = None
    return_window_end: Optional[str] = None
    returnable: bool = True
    already_refunded: bool = False
    refund_id: Optional[str] = None
    delayed: bool = False
    days_delayed: int = 0
    eta: Optional[str] = None
    tracking: List[TrackingEvent] = []
    payment: PaymentSummary
    pickup_scheduled: Optional[PickupDetails] = None
    voucher_issued: bool = False
    voucher_code: Optional[str] = None
    escalation_ticket: Optional[EscalationTicket] = None
    replacement_requested: bool = False
    replacement_id: Optional[str] = None
    replacement_order_id: Optional[str] = None
    replacement_details: Optional[Dict[str, Any]] = None

