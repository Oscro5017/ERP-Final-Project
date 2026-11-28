"""Remembered auto/manual choices."""
from typing import Literal

from pydantic import BaseModel


AutomationKey = Literal[
    "order_planting", "planting_cycles", "cycle_tasks", "harvest_stock",
    "order_fill", "outbound_finance", "inbound_finance", "order_close",
    "seed_stock", "auto_stage",
]


class AutomationPreferenceUpdate(BaseModel):
    mode: Literal["auto", "manual"]
