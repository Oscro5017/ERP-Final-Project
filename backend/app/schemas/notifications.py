"""Reminders in the app and the phones that receive pushes."""
from datetime import datetime

from pydantic import BaseModel, Field

from .common import DecryptionStatusResponse


class NotificationResponse(DecryptionStatusResponse):
    id: int
    kind: str
    title: str
    body: str | None = None
    activity_id: int | None = None
    crop_cycle_id: int | None = None
    product_id: int | None = None
    scheduled_for: datetime
    sent_at: datetime | None = None
    read_at: datetime | None = None
    push_error: str | None = None
    is_masked: bool


class PushDeviceRegister(BaseModel):
    token: str = Field(min_length=20, max_length=4096)
