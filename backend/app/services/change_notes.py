"""Record what changed on a record after it was saved, and why.

Every value is stored encrypted, because a change may involve money or names.
Reasons typed by the owner are optional; notes the system writes itself
(for example "moved 2 days before the computed date") go in ``auto_note``.
"""
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import ChangeNote, Role
from .secure_fields import encrypt_text, present_text_safe

_TABLE = "change_notes"


@dataclass(frozen=True)
class PresentedChange:
    id: int
    field: str
    old_value: str | None
    new_value: str | None
    reason: str | None
    auto_note: str | None
    user_id: int | None
    created_at: datetime
    is_masked: bool
    decrypt_failed: bool


def as_text(value) -> str | None:
    """A stable text form, so equal values compare equal and read well later."""
    if value is None:
        return None
    if isinstance(value, Enum):
        value = value.value
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value.normalize(), "f")
    if isinstance(value, float):
        return format(Decimal(str(value)).normalize(), "f")
    return str(value)


def _encrypt(value: str | None) -> bytes | None:
    return encrypt_text(value).encode("ascii") if value is not None else None


def _clean(text: str | None) -> str | None:
    text = (text or "").strip()
    return text or None


def record_change(
    db: Session,
    *,
    entity_type: str,
    entity_id: int,
    field: str,
    old,
    new,
    user_id: int | None = None,
    reason: str | None = None,
    auto_note: str | None = None,
) -> ChangeNote | None:
    """Add one note, or nothing when the value did not really change."""
    old_text, new_text = as_text(old), as_text(new)
    if old_text == new_text:
        return None
    note = ChangeNote(
        entity_type=entity_type,
        entity_id=entity_id,
        field=field,
        old_value_encrypted=_encrypt(old_text),
        new_value_encrypted=_encrypt(new_text),
        reason_encrypted=_encrypt(_clean(reason)),
        auto_note_encrypted=_encrypt(_clean(auto_note)),
        user_id=user_id,
    )
    db.add(note)
    return note


def record_changes(
    db: Session,
    *,
    entity_type: str,
    entity_id: int,
    before: dict,
    after: dict,
    user_id: int | None = None,
    reason: str | None = None,
    auto_notes: dict[str, str] | None = None,
) -> list[ChangeNote]:
    """Note every field in ``after`` whose value differs from ``before``."""
    notes = []
    for field, new in after.items():
        note = record_change(
            db,
            entity_type=entity_type,
            entity_id=entity_id,
            field=field,
            old=before.get(field),
            new=new,
            user_id=user_id,
            reason=reason,
            auto_note=(auto_notes or {}).get(field),
        )
        if note is not None:
            notes.append(note)
    if notes:
        db.flush()
    return notes


def list_changes(db: Session, entity_type: str, entity_id: int, role: Role | str) -> list[PresentedChange]:
    """Oldest first; values are masked for anyone but the owner."""
    rows = db.scalars(select(ChangeNote).where(
        ChangeNote.entity_type == entity_type,
        ChangeNote.entity_id == entity_id,
    ).order_by(ChangeNote.created_at, ChangeNote.id)).all()
    presented = []
    for row in rows:
        values = {}
        failed = False
        for name in ("old_value", "new_value", "reason", "auto_note"):
            token = getattr(row, f"{name}_encrypted")
            if token is None:
                values[name] = None
                continue
            result = present_text_safe(token, role, table=_TABLE, row_id=row.id, field=name)
            values[name] = result.value
            failed = failed or result.decrypt_failed
        presented.append(PresentedChange(
            id=row.id,
            field=row.field,
            user_id=row.user_id,
            created_at=row.created_at,
            is_masked=role not in (Role.owner, Role.owner.value),
            decrypt_failed=failed,
            **values,
        ))
    return presented
