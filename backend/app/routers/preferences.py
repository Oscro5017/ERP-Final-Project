from fastapi import APIRouter, Depends, Response
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import AutomationPreference, User
from ..schemas import AutomationKey, AutomationPreferenceUpdate
from ..security import get_current_user

router = APIRouter(prefix="/preferences", tags=["preferences"])


@router.get("/automation", response_model=dict[str, str])
def list_automation(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = db.scalars(select(AutomationPreference).where(AutomationPreference.user_id == user.id)).all()
    return {row.key: row.mode for row in rows}


@router.put("/automation/{key}", status_code=204)
def set_automation(
    key: AutomationKey,
    payload: AutomationPreferenceUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    row = db.scalar(select(AutomationPreference).where(
        AutomationPreference.user_id == user.id, AutomationPreference.key == key
    ))
    if row is None:
        row = AutomationPreference(user_id=user.id, key=key)
        db.add(row)
    row.mode = payload.mode
    db.commit()
    return Response(status_code=204)


@router.delete("/automation/{key}", status_code=204)
def clear_automation(key: AutomationKey, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    db.execute(delete(AutomationPreference).where(
        AutomationPreference.user_id == user.id, AutomationPreference.key == key
    ))
    db.commit()
    return Response(status_code=204)
