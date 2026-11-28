from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Notification, Role, User, utc_now
from ..schemas import NotificationResponse, PushDeviceRegister
from ..security import get_current_user
from ..services.notifications import forget_device, present_text, register_device

router = APIRouter(tags=["notifications"])


def _present(row: Notification, role: Role) -> NotificationResponse:
    return NotificationResponse(
        id=row.id, kind=row.kind,
        title=present_text(row.title_encrypted, role, row.id, "title"),
        body=present_text(row.body_encrypted, role, row.id, "body"),
        activity_id=row.activity_id, crop_cycle_id=row.crop_cycle_id, product_id=row.product_id,
        scheduled_for=row.scheduled_for, sent_at=row.sent_at, read_at=row.read_at, push_error=row.push_error,
        is_masked=role != Role.owner,
    )


@router.get("/notifications", response_model=list[NotificationResponse])
def list_notifications(
    unread: bool = Query(False), limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    statement = select(Notification).where(Notification.user_id == user.id)
    if unread:
        statement = statement.where(Notification.read_at.is_(None))
    rows = db.scalars(statement.order_by(Notification.scheduled_for.desc(), Notification.id.desc()).limit(limit)).all()
    return [_present(row, user.role) for row in rows]


@router.post("/notifications/{notification_id}/read", response_model=NotificationResponse)
def mark_read(notification_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    row = db.get(Notification, notification_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status_code=404, detail="Notification not found")
    row.read_at = row.read_at or utc_now()
    db.commit()
    return _present(row, user.role)


@router.post("/notifications/read-all", status_code=204)
def mark_all_read(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    db.execute(update(Notification).where(Notification.user_id == user.id, Notification.read_at.is_(None)).values(read_at=utc_now()))
    db.commit()
    return Response(status_code=204)


@router.post("/push-devices", status_code=204)
def add_push_device(payload: PushDeviceRegister, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """The phone app sends its Firebase token after login."""
    register_device(db, user.id, payload.token)
    db.commit()
    return Response(status_code=204)


@router.post("/push-devices/remove", status_code=204)
def remove_push_device(payload: PushDeviceRegister, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    """Called on logout so the phone stops receiving pushes."""
    forget_device(db, payload.token)
    db.commit()
    return Response(status_code=204)
