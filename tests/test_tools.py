import pytest
import datetime
from backend.tools.order_tools import OrderTools, ToolContext, validate_pickup_date, MOCK_HOLIDAYS
from backend.services.order_service import order_service
from backend.voice.normalizer import tts_normalize
from backend.voice.chunker import SentenceChunker

@pytest.fixture(autouse=True)
def reload_orders():
    order_service.load_orders()

@pytest.mark.asyncio
async def test_order_scope_enforcement():
    ctx = ToolContext(session_id="test_sess", bound_order_id="ORD-1001")
    tools = OrderTools(ctx)
    # Attempting to query an order different from bound order
    res = await tools.get_order_status("ORD-1002")
    assert res["ok"] is False
    assert res["code"] == "ORDER_SCOPE_MISMATCH"

@pytest.mark.asyncio
async def test_get_order_status_success():
    ctx = ToolContext(session_id="test_sess", bound_order_id="ORD-1001")
    tools = OrderTools(ctx)
    res = await tools.get_order_status("ORD-1001")
    assert res["ok"] is True
    assert res["data"]["status"] == "Delivered"
    assert res["data"]["returnable"] is True
    assert res["data"]["return_window_days_remaining"] > 0

@pytest.mark.asyncio
async def test_refund_outside_return_window():
    # ORD-1003 was delivered 25 days ago
    ctx = ToolContext(session_id="test_sess", bound_order_id="ORD-1003")
    tools = OrderTools(ctx)
    res = await tools.process_refund("ORD-1003", reason="Item defective")
    assert res["ok"] is False
    assert res["code"] == "OUTSIDE_RETURN_WINDOW"

@pytest.mark.asyncio
async def test_refund_non_returnable_item():
    # ORD-1004 is innerwear (non-returnable)
    ctx = ToolContext(session_id="test_sess", bound_order_id="ORD-1004")
    tools = OrderTools(ctx)
    res = await tools.process_refund("ORD-1004", reason="Changed mind")
    assert res["ok"] is False
    assert res["code"] == "NON_RETURNABLE"

@pytest.mark.asyncio
async def test_refund_idempotency():
    ctx = ToolContext(session_id="test_sess", bound_order_id="ORD-1001")
    tools = OrderTools(ctx)
    # First refund call
    res1 = await tools.process_refund("ORD-1001", reason="Damaged item")
    assert res1["ok"] is True
    ref1 = res1["data"]["refund_id"]

    # Second refund call (repeat)
    res2 = await tools.process_refund("ORD-1001", reason="Damaged item")
    assert res2["ok"] is True
    assert res2["code"] == "ALREADY_REFUNDED"
    assert res2["data"]["refund_id"] == ref1

@pytest.mark.asyncio
async def test_schedule_pickup_validation():
    ctx = ToolContext(session_id="test_sess", bound_order_id="ORD-1001")
    tools = OrderTools(ctx)

    # Date in past
    res_past = await tools.schedule_pickup("ORD-1001", "2026-11-10", "Indiranagar", "morning")
    assert res_past["ok"] is False
    assert res_past["code"] == "INVALID_DATE"

    # Sunday test: 2026-11-15 is Sunday
    res_sunday = await tools.schedule_pickup("ORD-1001", "2026-11-15", "Indiranagar", "morning")
    assert res_sunday["ok"] is False
    assert "Sunday" in res_sunday["message"]

    # Valid pickup: 2026-11-12 (Thursday)
    res_valid = await tools.schedule_pickup("ORD-1001", "2026-11-12", "Indiranagar, Bangalore", "morning")
    assert res_valid["ok"] is True
    assert "pickup_id" in res_valid["data"]

    # Idempotency test: repeat pickup returns existing ID
    res_repeat = await tools.schedule_pickup("ORD-1001", "2026-11-12", "Indiranagar, Bangalore", "morning")
    assert res_repeat["ok"] is True
    assert res_repeat["code"] == "ALREADY_SCHEDULED"
    assert res_repeat["data"]["pickup_id"] == res_valid["data"]["pickup_id"]

@pytest.mark.asyncio
async def test_voucher_issuance_and_cap():
    ctx = ToolContext(session_id="test_sess", bound_order_id="ORD-1002")
    tools = OrderTools(ctx)

    # First voucher
    v1 = await tools.issue_voucher("ORD-1002", amount=400, reason="delayed_delivery")
    assert v1["ok"] is True
    code = v1["data"]["voucher_code"]

    # Second voucher attempt (capped at 1)
    v2 = await tools.issue_voucher("ORD-1002", amount=400, reason="delayed_delivery")
    assert v2["ok"] is False
    assert v2["code"] == "VOUCHER_ALREADY_ISSUED"
    assert v2["data"]["voucher_code"] == code

@pytest.mark.asyncio
async def test_cancel_order_processing_only():
    # Processing order ORD-1007
    ctx1 = ToolContext(session_id="test_sess", bound_order_id="ORD-1007")
    tools1 = OrderTools(ctx1)
    c1 = await tools1.cancel_order("ORD-1007", reason="Found better price")
    assert c1["ok"] is True
    assert c1["data"]["status"] == "Cancelled"

    # In Transit order ORD-1002 cannot be cancelled directly
    ctx2 = ToolContext(session_id="test_sess", bound_order_id="ORD-1002")
    tools2 = OrderTools(ctx2)
    c2 = await tools2.cancel_order("ORD-1002", reason="Changed mind")
    assert c2["ok"] is False
    assert c2["code"] == "CANNOT_CANCEL"

def test_tts_normalize():
    # Order IDs read digit by digit
    norm_ord = tts_normalize("Your order ORD-1001 has been updated.")
    assert "O R D-one zero zero one" in norm_ord or "O R D" in norm_ord

    # Rupee amounts
    norm_inr = tts_normalize("The refund amount is ₹1,299 to your account.")
    assert "1299 rupees" in norm_inr

    # Dollar amounts
    norm_usd = tts_normalize("Here is a $5 coupon code.")
    assert "5 dollars" in norm_usd

    # Date normalization
    norm_date = tts_normalize("Delivery scheduled for 2026-11-15.")
    assert "November" in norm_date

def test_sentence_chunker():
    chunker = SentenceChunker()
    # Sentence with abbreviation 'Mr.' and number '3.5'
    tokens = ["Hello ", "Mr. ", "Sharma! ", "Your order will arrive in 3.5 ", "hours. ", "Have a great day."]
    sentences = []
    for t in tokens:
        sentences.extend(chunker.add_token(t))
    sentences.extend(chunker.flush())

    assert len(sentences) == 3
    assert sentences[0] == "Hello Mr. Sharma!"
    assert sentences[1] == "Your order will arrive in 3.5 hours."
    assert sentences[2] == "Have a great day."

