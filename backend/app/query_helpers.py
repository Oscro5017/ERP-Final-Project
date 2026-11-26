from sqlalchemy import Select, select
from sqlalchemy.orm import Session


def active_rows(statement: Select, model) -> Select:
    return statement.where(model.deleted_at.is_(None))


def get_active(db: Session, model, row_id: int):
    statement = active_rows(select(model).where(model.id == row_id), model)
    return db.scalar(statement)