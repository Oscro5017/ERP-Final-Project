"""Morning reminders: kept in the app, and pushed to the owner's phone as a short summary.

Every morning (08:00 by default) the Pi looks for:
- planned activities with a reminder, due in ``notify_lead_days`` days or today;
- fresh-produce lots that reach their warning window.

Each reminder is stored once (``dedupe_key``) with its full text, encrypted, for the app.
The push itself carries only a count, so no farm details pass through Google's servers.
"""
import hashlib
import logging
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Activity, Notification, ProductShelfLife, PushDevice, Role, User, utc_now
from .freshness import build_lots
from .push_fcm import InvalidDeviceToken, PushNotConfigured
from .secure_fields import decrypt_text, encrypt_text, safe_decrypt_text

logger = logging.getLogger(__name__)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.strip().encode("utf-8")).hexdigest()


def register_device(db: Session, user_id: int, token: str) -> PushDevice:
    digest = token_hash(token)
    device = db.scalar(select(PushDevice).where(PushDevice.token_hash == digest))
    if device is None:
        device = PushDevice(user_id=user_id, token_hash=digest, token_encrypted=encrypt_text(token.strip()).encode("ascii"))
        db.add(device)
    device.user_id = user_id
    device.last_seen_at = utc_now()
    return device


def forget_device(db: Session, token: str) -> bool:
    device = db.scalar(select(PushDevice).where(PushDevice.token_hash == token_hash(token)))
    if device is None:
        return False
    db.delete(device)
    return True


def _activity_title(activity: Activity) -> str:
    if not activity.is_encrypted:
        return activity.title
    return safe_decrypt_text(activity.title, table="activities", row_id=activity.id, field="title").value


def _add(db: Session, user_id: int, kind: str, key: str, title: str, body: str | None, **links) -> bool:
    if db.scalar(select(Notification.id).where(Notification.dedupe_key == key)) is not None:
        return False
    db.add(Notification(
        user_id=user_id, kind=kind, dedupe_key=key, scheduled_for=utc_now(),
        title_encrypted=encrypt_text(title).encode("ascii"),
        body_encrypted=encrypt_text(body).encode("ascii") if body else None,
        **links,
    ))
    return True


def build_reminders(db: Session, today: date, lead_days: int = 2) -> int:
    """Store today's reminders for every owner; returns how many are new."""
    owners = db.scalars(select(User).where(User.role == Role.owner)).all()
    if not owners:
        return 0
    created = 0
    soon = today + timedelta(days=lead_days)
    activities = db.scalars(select(Activity).where(
        Activity.deleted_at.is_(None),
        Activity.status == "pending",
        Activity.remind.is_(True),
        Activity.planned_date.in_({today, soon}),
    ).order_by(Activity.planned_date, Activity.id)).all()
    for activity in activities:
        when = "วันนี้" if activity.planned_date == today else f"อีก {lead_days} วัน"
        for owner in owners:
            created += _add(
                db, owner.id, "activity_due", f"activity:{activity.id}:{activity.planned_date}:{owner.id}",
                f"{when}: {_activity_title(activity)}", f"กำหนด {activity.planned_date.isoformat()}",
                activity_id=activity.id, crop_cycle_id=activity.cycle_id,
            )

    for setting in db.scalars(select(ProductShelfLife)).all():
        for lot in build_lots(db, setting)[0]:
            if lot.remaining <= 0 or not (today <= lot.expires_on <= today + timedelta(days=setting.warn_days)):
                continue
            for owner in owners:
                created += _add(
                    db, owner.id, "lot_expiring", f"lot:{setting.product_id}:{lot.key}:{lot.expires_on}:{owner.id}",
                    "ผักใกล้หมดอายุ", f"ล็อตรับเข้า {lot.received_on.isoformat()} เหลือ {lot.remaining:g} หมดอายุ {lot.expires_on.isoformat()}",
                    product_id=setting.product_id, crop_cycle_id=lot.cycle_id,
                )
    db.flush()
    return created


def send_pushes(db: Session, sender) -> int:
    """One summary push per owner for reminders not pushed yet; returns how many phones were reached."""
    pending = db.scalars(select(Notification).where(
        Notification.sent_at.is_(None), Notification.push_error.is_(None)
    )).all()
    by_user: dict[int, list[Notification]] = {}
    for notification in pending:
        by_user.setdefault(notification.user_id, []).append(notification)
    reached = 0
    for user_id, notifications in by_user.items():
        devices = db.scalars(select(PushDevice).where(PushDevice.user_id == user_id)).all()
        error = None
        if sender is None:
            error = "push_not_configured"
        elif not devices:
            error = "no_device"
        else:
            for device in devices:
                try:
                    sender.send(
                        decrypt_text(device.token_encrypted), "งานฟาร์มวันนี้",
                        f"มีการแจ้งเตือน {len(notifications)} รายการ เปิดแอปเพื่อดูรายละเอียด",
                        {"kind": "reminders", "count": str(len(notifications))},
                    )
                    reached += 1
                except InvalidDeviceToken:
                    db.delete(device)
                except Exception as exc:  # network or Google error; the reminders stay in the app
                    logger.warning("Push to a device failed: %s", type(exc).__name__)
                    error = type(exc).__name__[:200]
        now = utc_now()
        for notification in notifications:
            if error:
                notification.push_error = error
            else:
                notification.sent_at = now
    db.flush()
    return reached


def make_sender(settings):
    from .push_fcm import FcmSender

    try:
        return FcmSender(settings.fcm_credentials_file)
    except PushNotConfigured:
        return None


def run_morning_reminders(db: Session, settings, today: date | None = None, sender=None) -> int:
    from .activities import today_bangkok

    created = build_reminders(db, today or today_bangkok(), settings.notify_lead_days)
    send_pushes(db, sender if sender is not None else make_sender(settings))
    db.commit()
    return created


def present_text(token: bytes | None, role, row_id: int, field: str) -> str | None:
    """Owners read reminders; anyone else sees the encrypted text."""
    if token is None:
        return None
    if role == Role.owner:
        return safe_decrypt_text(token, table="notifications", row_id=row_id, field=field).value
    return token.decode("ascii")

