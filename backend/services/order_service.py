import json
import asyncio
from pathlib import Path
from typing import List, Optional, Dict
from ..schemas.order import Order

DATA_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "orders.json"

class OrderService:
    def __init__(self):
        self._lock = asyncio.Lock()
        self._orders: Dict[str, Order] = {}
        self.load_orders()

    def load_orders(self):
        if not DATA_FILE.exists():
            raise FileNotFoundError(f"Orders data file not found: {DATA_FILE}")
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            self._orders = {item["id"]: Order.model_validate(item) for item in data}

    async def get_all_orders(self) -> List[Order]:
        async with self._lock:
            return list(self._orders.values())

    async def get_order(self, order_id: str) -> Optional[Order]:
        async with self._lock:
            return self._orders.get(order_id)

    async def save_order(self, order: Order) -> None:
        async with self._lock:
            self._orders[order.id] = order

order_service = OrderService()

