from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Insight, User
from ..schemas import InsightResponse, InsightStatusUpdate
from ..security import get_current_user
from ..services.secure_fields import present_text_safe

router = APIRouter(prefix="/insights", tags=["insights"])
_KINDS = {"insight", "recommendation", "alert"}
_STATUSES = {"new", "seen", "dismissed", "done"}


def _present(insight: Insight, user: User) -> InsightResponse:
    title = present_text_safe(insight.title_encrypted, user.role, table="insights", row_id=insight.id, field="title")
    body = present_text_safe(insight.body_encrypted, user.role, table="insights", row_id=insight.id, field="body")
    return InsightResponse(
        id=insight.id,
        kind=insight.kind,
        source=insight.source,
        title=title.value,
        body=body.value,
        severity=insight.severity,
        valid_from=insight.valid_from,
        valid_until=insight.valid_until,
        crop_cycle_id=insight.crop_cycle_id,
        task_id=insight.task_id,
        status=insight.status,
        is_masked=user.role.value != "owner",
        decrypt_failed=title.decrypt_failed or body.decrypt_failed,
        created_at=insight.created_at,
        updated_at=insight.updated_at,
    )


@router.get("")
def list_insights(
    kind: str | None = None,
    status: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if kind is not None and kind not in _KINDS:
        raise HTTPException(status_code=422, detail="Invalid insight kind")
    if status is not None and status not in _STATUSES:
        raise HTTPException(status_code=422, detail="Invalid insight status")
    statement = select(Insight)
    if kind is not None:
        statement = statement.where(Insight.kind == kind)
    if status is not None:
        statement = statement.where(Insight.status == status)
    total = db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    rows = db.scalars(statement.order_by(Insight.created_at.desc(), Insight.id.desc()).limit(limit).offset(offset)).all()
    return {"items": [_present(row, user) for row in rows], "total": total}


@router.get("/{insight_id}", response_model=InsightResponse)
def get_insight(insight_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    insight = db.get(Insight, insight_id)
    if insight is None:
        raise HTTPException(status_code=404, detail="Insight not found")
    return _present(insight, user)


@router.patch("/{insight_id}/status", response_model=InsightResponse)
def update_insight_status(
    insight_id: int,
    payload: InsightStatusUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    insight = db.get(Insight, insight_id)
    if insight is None:
        raise HTTPException(status_code=404, detail="Insight not found")
    insight.status = payload.status
    db.commit()
    db.refresh(insight)
    return _present(insight, user)
