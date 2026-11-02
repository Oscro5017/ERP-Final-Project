from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import InputCatalog
from .secure_fields import decrypt_text, encrypt_text, hash_catalog_name, normalize_catalog_name


def normalize_item_name(value: str) -> str:
    return (value or "").strip()


def upsert_input_catalog(db: Session, item_name: str, unit: str | None = None, category: str | None = None) -> InputCatalog:
    text = normalize_item_name(item_name)
    if not text:
        raise ValueError("item_name is required")

    name_hash = hash_catalog_name(text)
    catalog = db.scalar(select(InputCatalog).where(InputCatalog.name_hash == name_hash))
    now = datetime.now(UTC)

    if catalog is None:
        catalog = InputCatalog(
            name_encrypted=encrypt_text(text).encode("ascii"),
            name_hash=name_hash,
            last_unit=unit.strip() if unit and unit.strip() else None,
            last_category=category.strip() if category and category.strip() else None,
            last_used_at=now,
            use_count=1,
        )
        db.add(catalog)
        db.flush()
        return catalog

    catalog.last_unit = unit.strip() if unit and unit.strip() else catalog.last_unit
    catalog.last_category = category.strip() if category and category.strip() else catalog.last_category
    catalog.last_used_at = now
    catalog.use_count += 1
    return catalog


def suggest_input_catalog(db: Session, query: str, limit: int = 10) -> list[InputCatalog]:
    q = normalize_catalog_name(query)
    if not q:
        return []
    matches = [
        item
        for item in db.scalars(select(InputCatalog)).all()
        if q in normalize_catalog_name(decrypt_text(item.name_encrypted))
    ]
    matches.sort(
        key=lambda item: (
            item.use_count,
            item.last_used_at.timestamp() if item.last_used_at else float("-inf"),
        ),
        reverse=True,
    )
    return matches[:limit]
