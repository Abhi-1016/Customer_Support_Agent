import datetime
import logging
import uuid
from typing import Dict, Any, Optional, Tuple
from ..services.order_service import order_service
from ..schemas.order import Order, PickupDetails, EscalationTicket

logger = logging.getLogger("order_tools")

# Mock holiday list (ISO format YYYY-MM-DD)
MOCK_HOLIDAYS = {"2026-11-15", "2026-11-26", "2026-12-25", "2027-01-01", "2027-01-26"}

def validate_pickup_date(pickup_date_str: str, today: datetime.date) -> Tuple[bool, str]:
    try:
        p_date = datetime.date.fromisoformat(pickup_date_str)
    except ValueError:
        return False, "Invalid date format. Please provide date as YYYY-MM-DD."

    days_ahead = (p_date - today).days
    if days_ahead < 1:
        return False, "Pickup date must be tomorrow or later."
    if days_ahead > 7:
        return False, "Pickup date cannot be scheduled more than 7 days in advance."
    if p_date.weekday() == 6:  # Sunday is 6
        return False, f"{pickup_date_str} is a Sunday. Couriers do not operate on Sundays."
    if pickup_date_str in MOCK_HOLIDAYS:
        return False, f"{pickup_date_str} is a public holiday. Courier services are closed."

    return True, "Valid"

def get_next_available_slots(today: datetime.date, requested_date_str: str) -> list[dict]:
    alternatives = []
    curr = today + datetime.timedelta(days=1)
    while len(alternatives) < 2 and (curr - today).days <= 7:
        d_str = curr.isoformat()
        if curr.weekday() != 6 and d_str not in MOCK_HOLIDAYS and d_str != requested_date_str:
            alternatives.append({"date": d_str, "window": "morning"})
            if len(alternatives) < 2:
                alternatives.append({"date": d_str, "window": "afternoon"})
        curr += datetime.timedelta(days=1)
    return alternatives[:2]

def calculate_callback_eta(now_dt: datetime.datetime) -> str:
    # Business hours: 09:00 to 18:00
    hour = now_dt.hour
    is_weekend = now_dt.weekday() >= 5

    if not is_weekend and 9 <= hour < 18:
        eta_time = now_dt + datetime.timedelta(minutes=30)
        return f"within 30 minutes (around {eta_time.strftime('%I:%M %p')})"
    else:
        # Next business morning at 9:30 AM
        next_day = now_dt + datetime.timedelta(days=1)
        while next_day.weekday() >= 5:
            next_day += datetime.timedelta(days=1)
        morning_dt = next_day.replace(hour=9, minute=30, second=0, microsecond=0)
        return f"next business morning ({morning_dt.strftime('%A, %B %d at %I:%M %p')})"

class ToolContext:
    def __init__(self, session_id: str, bound_order_id: str):
        self.session_id = session_id
        self.bound_order_id = bound_order_id
        self.today = datetime.date(2026, 11, 11)  # Anchored demo date
        self.now_dt = datetime.datetime(2026, 11, 11, 11, 30, 0)
        # Failure simulation hooks for demo/testing
        self.force_pickup_fail = False
        self.force_refund_fail = False
        self.force_slot_full = False

class OrderTools:
    def __init__(self, context: ToolContext):
        self.ctx = context

    def _check_order_scope(self, order_id: str) -> Optional[Dict[str, Any]]:
        if order_id != self.ctx.bound_order_id:
            logger.warning(f"Order scope mismatch: {order_id} != bound {self.ctx.bound_order_id}")
            return {
                "ok": False,
                "code": "ORDER_SCOPE_MISMATCH",
                "message": f"Security restriction: You can only take actions on your active order {self.ctx.bound_order_id}.",
                "data": {}
            }
        return None

    async def get_order_status(self, order_id: str) -> Dict[str, Any]:
        """Check order status, tracking, and eligibility information."""
        scope_err = self._check_order_scope(order_id)
        if scope_err:
            return scope_err

        order = await order_service.get_order(order_id)
        if not order:
            return {"ok": False, "code": "ORDER_NOT_FOUND", "message": f"Order {order_id} not found.", "data": {}}

        # Calculate return window days remaining
        days_remaining = 0
        if order.status == "Delivered" and order.delivered_on:
            try:
                del_dt = datetime.datetime.fromisoformat(order.delivered_on.replace("Z", "+00:00")).date()
                elapsed = (self.ctx.today - del_dt).days
                days_remaining = max(0, 10 - elapsed)
            except Exception:
                days_remaining = 0

        last_event = order.tracking[-1].model_dump() if order.tracking else {}

        return {
            "ok": True,
            "code": "SUCCESS",
            "message": f"Order {order_id} is currently {order.status}.",
            "data": {
                "order_id": order.id,
                "status": order.status,
                "eta": order.eta,
                "last_event": last_event,
                "delayed": order.delayed,
                "days_delayed": order.days_delayed,
                "payment_method": order.payment.method,
                "amount": order.payment.amount,
                "delivered_on": order.delivered_on,
                "return_window_days_remaining": days_remaining,
                "returnable": order.returnable,
                "already_refunded": order.already_refunded,
                "refund_id": order.refund_id,
                "pickup_scheduled": order.pickup_scheduled.model_dump() if order.pickup_scheduled else None,
                "voucher_issued": order.voucher_issued,
                "voucher_code": order.voucher_code
            }
        }

    async def process_refund(self, order_id: str, reason: str) -> Dict[str, Any]:
        """Process a refund for an eligible order (Delivered within return window, or cancelled)."""
        scope_err = self._check_order_scope(order_id)
        if scope_err:
            return scope_err

        if self.ctx.force_refund_fail:
            return {
                "ok": False,
                "code": "PAYMENT_GATEWAY_ERROR",
                "message": "The payment gateway encountered an error while processing the refund. Our specialist team has been notified.",
                "data": {}
            }

        order = await order_service.get_order(order_id)
        if not order:
            return {"ok": False, "code": "ORDER_NOT_FOUND", "message": "Order not found.", "data": {}}

        # Idempotency check: if already refunded, return existing reference
        if order.already_refunded and order.refund_id:
            return {
                "ok": True,
                "code": "ALREADY_REFUNDED",
                "message": f"Refund was already processed with ID {order.refund_id}. Funds will reflect within 3 to 5 business days.",
                "data": {
                    "refund_id": order.refund_id,
                    "amount": order.payment.amount,
                    "eta_days": "3 to 5 business days",
                    "payment_method": order.payment.method,
                    "is_duplicate": True
                }
            }

        # Eligibility check
        if order.status == "Delivered":
            if not order.returnable:
                return {
                    "ok": False,
                    "code": "NON_RETURNABLE",
                    "message": "This item is marked non-returnable due to hygiene or perishable goods policy.",
                    "data": {}
                }
            # Check return window (10 days)
            if order.delivered_on:
                del_dt = datetime.datetime.fromisoformat(order.delivered_on.replace("Z", "+00:00")).date()
                if (self.ctx.today - del_dt).days > 10:
                    return {
                        "ok": False,
                        "code": "OUTSIDE_RETURN_WINDOW",
                        "message": "The 10-day return window for this order has expired.",
                        "data": {}
                    }
        elif order.status == "Processing":
            pass # Eligible for cancel + refund
        elif order.status == "In Transit":
            return {
                "ok": False,
                "code": "IN_TRANSIT_NOT_CANCELLABLE",
                "message": "Orders currently in transit cannot be refunded directly. Please refuse delivery or initiate a return upon receipt.",
                "data": {}
            }
        elif order.status == "Cancelled":
            if order.already_refunded:
                return {
                    "ok": True,
                    "code": "ALREADY_REFUNDED",
                    "message": f"Order was cancelled and refund {order.refund_id} has been initiated.",
                    "data": {"refund_id": order.refund_id, "amount": order.payment.amount, "eta_days": "3 to 5 business days"}
                }
        else:
            return {
                "ok": False,
                "code": "NOTHING_TO_REFUND",
                "message": f"Order in status '{order.status}' is not eligible for refund.",
                "data": {}
            }

        # Issue refund
        refund_id = f"REF-{uuid.uuid4().hex[:6].upper()}"
        order.already_refunded = True
        order.refund_id = refund_id
        order.payment.already_refunded = True
        order.payment.refund_id = refund_id
        await order_service.save_order(order)

        return {
            "ok": True,
            "code": "SUCCESS",
            "message": f"Refund of ₹{int(order.payment.amount)} successfully initiated. Reference ID is {refund_id}.",
            "data": {
                "refund_id": refund_id,
                "amount": order.payment.amount,
                "eta_days": "3 to 5 business days",
                "payment_method": order.payment.method
            }
        }

    async def schedule_pickup(self, order_id: str, date: str, address: str, time_window: str) -> Dict[str, Any]:
        """Schedule a return courier pickup for a delivered, returnable item."""
        scope_err = self._check_order_scope(order_id)
        if scope_err:
            return scope_err

        if self.ctx.force_pickup_fail:
            return {
                "ok": False,
                "code": "COURIER_SERVICE_UNAVAILABLE",
                "message": "Courier pickup service is currently unavailable for this pin code. Please try again later or escalate.",
                "data": {}
            }

        order = await order_service.get_order(order_id)
        if not order:
            return {"ok": False, "code": "ORDER_NOT_FOUND", "message": "Order not found.", "data": {}}

        if order.status != "Delivered":
            return {
                "ok": False,
                "code": "ORDER_NOT_DELIVERED",
                "message": f"Pickups can only be scheduled for delivered orders. Current status: {order.status}",
                "data": {}
            }

        if not order.returnable:
            return {
                "ok": False,
                "code": "NON_RETURNABLE",
                "message": "This item is not eligible for return pickup.",
                "data": {}
            }

        # Validate time window
        norm_window = time_window.strip().lower()
        if norm_window not in ["morning", "afternoon", "evening"]:
            return {
                "ok": False,
                "code": "INVALID_TIME_WINDOW",
                "message": "Please choose a valid time slot: morning (9 AM - 12 PM), afternoon (12 PM - 4 PM), or evening (4 PM - 8 PM).",
                "data": {}
            }

        # Validate date
        is_valid_date, date_msg = validate_pickup_date(date, self.ctx.today)
        if not is_valid_date:
            return {
                "ok": False,
                "code": "INVALID_DATE",
                "message": date_msg,
                "data": {"suggested_slots": get_next_available_slots(self.ctx.today, date)}
            }

        # Simulate full slot if requested or tested
        if self.ctx.force_slot_full or date.endswith("-99"):
            alt_slots = get_next_available_slots(self.ctx.today, date)
            return {
                "ok": False,
                "code": "SLOT_FULL",
                "message": f"The {norm_window} slot on {date} is fully booked.",
                "data": {"suggested_alternatives": alt_slots}
            }

        # Validate address non-empty
        if not address or len(address.strip()) < 5:
            return {
                "ok": False,
                "code": "INVALID_ADDRESS",
                "message": "Please provide a valid and complete pickup address.",
                "data": {}
            }

        # Idempotent check
        if order.pickup_scheduled:
            pickup = order.pickup_scheduled
            return {
                "ok": True,
                "code": "ALREADY_SCHEDULED",
                "message": f"Pickup is already scheduled for {pickup.date} ({pickup.window}) with reference {pickup.id}.",
                "data": {
                    "pickup_id": pickup.id,
                    "date": pickup.date,
                    "window": pickup.window,
                    "address": pickup.address,
                    "courier_note": "Courier will call 30 minutes before arrival.",
                    "is_duplicate": True
                }
            }

        pickup_id = f"PKP-{uuid.uuid4().hex[:6].upper()}"
        pickup_details = PickupDetails(
            id=pickup_id,
            date=date,
            window=norm_window,
            address=address,
            courier_note="Courier will call 30 minutes before arrival."
        )
        order.pickup_scheduled = pickup_details
        await order_service.save_order(order)

        return {
            "ok": True,
            "code": "SUCCESS",
            "message": f"Return pickup scheduled for {date} during {norm_window}. Reference ID is {pickup_id}.",
            "data": {
                "pickup_id": pickup_id,
                "date": date,
                "window": norm_window,
                "address": address,
                "courier_note": "Courier will call 30 minutes before arrival."
            }
        }

    async def escalate_to_human(self, order_id: str, summary: str, priority: str = "medium", reason_code: str = "customer_request") -> Dict[str, Any]:
        """Escalate issue to a human support specialist or manager."""
        scope_err = self._check_order_scope(order_id)
        if scope_err:
            return scope_err

        order = await order_service.get_order(order_id)
        if not order:
            return {"ok": False, "code": "ORDER_NOT_FOUND", "message": "Order not found.", "data": {}}

        # Idempotent check: if escalation ticket already exists, return it
        if order.escalation_ticket:
            ticket = order.escalation_ticket
            return {
                "ok": True,
                "code": "ALREADY_ESCALATED",
                "message": f"An escalation ticket ({ticket.ticket_id}) is already active. Callback expected {ticket.callback_eta}.",
                "data": {
                    "ticket_id": ticket.ticket_id,
                    "callback_eta": ticket.callback_eta,
                    "priority": ticket.priority,
                    "is_duplicate": True
                }
            }

        ticket_id = f"TKT-{uuid.uuid4().hex[:6].upper()}"
        callback_eta = calculate_callback_eta(self.ctx.now_dt)

        ticket = EscalationTicket(
            ticket_id=ticket_id,
            summary=summary,
            priority=priority,
            reason_code=reason_code,
            callback_eta=callback_eta,
            created_at=self.ctx.now_dt.isoformat()
        )
        order.escalation_ticket = ticket
        await order_service.save_order(order)

        return {
            "ok": True,
            "code": "SUCCESS",
            "message": f"Escalation ticket {ticket_id} created. A senior specialist will call you {callback_eta}.",
            "data": {
                "ticket_id": ticket_id,
                "callback_eta": callback_eta,
                "priority": priority,
                "summary": summary
            }
        }

    async def issue_voucher(self, order_id: str, amount: float = 400.0, reason: str = "delivery_delay") -> Dict[str, Any]:
        """Issue a goodwill apology voucher (capped at one per order)."""
        scope_err = self._check_order_scope(order_id)
        if scope_err:
            return scope_err

        order = await order_service.get_order(order_id)
        if not order:
            return {"ok": False, "code": "ORDER_NOT_FOUND", "message": "Order not found.", "data": {}}

        if order.voucher_issued:
            return {
                "ok": False,
                "code": "VOUCHER_ALREADY_ISSUED",
                "message": f"A compensation voucher ({order.voucher_code}) has already been issued for this order. We can only issue one voucher per order.",
                "data": {"voucher_code": order.voucher_code}
            }

        code = f"SPHERE-{uuid.uuid4().hex[:4].upper()}-5"
        order.voucher_issued = True
        order.voucher_code = code
        await order_service.save_order(order)

        return {
            "ok": True,
            "code": "SUCCESS",
            "message": f"A ₹{int(amount)} discount voucher ({code}) has been added to your account for future purchases.",
            "data": {
                "voucher_code": code,
                "amount": amount,
                "reason": reason
            }
        }

    async def cancel_order(self, order_id: str, reason: str) -> Dict[str, Any]:
        """Cancel an order in Processing status and initiate refund."""
        scope_err = self._check_order_scope(order_id)
        if scope_err:
            return scope_err

        order = await order_service.get_order(order_id)
        if not order:
            return {"ok": False, "code": "ORDER_NOT_FOUND", "message": "Order not found.", "data": {}}

        if order.status == "Cancelled":
            return {
                "ok": True,
                "code": "ALREADY_CANCELLED",
                "message": f"Order {order_id} is already cancelled. Refund reference: {order.refund_id or 'Processing'}.",
                "data": {"order_id": order_id, "refund_id": order.refund_id}
            }

        if order.status != "Processing":
            return {
                "ok": False,
                "code": "CANNOT_CANCEL",
                "message": f"Order cannot be cancelled because it is already in '{order.status}' status.",
                "data": {}
            }

        order.status = "Cancelled"
        refund_id = f"REF-{uuid.uuid4().hex[:6].upper()}"
        order.already_refunded = True
        order.refund_id = refund_id
        order.payment.already_refunded = True
        order.payment.refund_id = refund_id
        await order_service.save_order(order)

        return {
            "ok": True,
            "code": "SUCCESS",
            "message": f"Order {order_id} has been cancelled and a full refund of ₹{int(order.payment.amount)} has been initiated (Reference {refund_id}).",
            "data": {
                "order_id": order_id,
                "status": "Cancelled",
                "refund_id": refund_id,
                "amount": order.payment.amount
            }
        }

