"""Phase 3 step 2 migration: targets for old activities, input applications become activities."""
from datetime import date, datetime

from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.migrations import migrate_activity_records
from app.models import (
    Activity, ActivityItem, ActivityTarget, Batch, CropCycle, CropType, InputApplication, InputItem, Product,
    StockMovement, Table,
)
from app.services.products_stock import on_hand
from app.services.secure_fields import decrypt_number, decrypt_text, encrypt_number, encrypt_text, hash_catalog_name


def _database(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'records.db'}")
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        # Phase 2 allowed one posted automatic finance entry per source.
        connection.execute(text("DROP INDEX uq_finance_entries_auto_posted_source"))
        connection.execute(text(
            "CREATE UNIQUE INDEX uq_finance_entries_auto_posted_source ON finance_entries (source_type, source_id) "
            "WHERE is_auto = 1 AND status = 'posted' AND source_id IS NOT NULL"
        ))
    Session = sessionmaker(bind=engine)
    with Session() as db:
        db.add_all([
            Table(id=1, table_number=4),
            Batch(id=1, batch_number=1, start_date=date(2026, 1, 1)),
            CropType(id=1, name="คะน้า", nursery_days=10, growth_days=30),
            Product(id=1, category="fertilizer", name_encrypted=encrypt_text("ปุ๋ย").encode(), name_hash=hash_catalog_name("ปุ๋ย"), unit="kg"),
        ])
        db.flush()
        db.add(CropCycle(id=1, table_id=1, batch_id=1, crop_type_id=1, nursery_start=date(2026, 1, 1)))
        db.flush()
        db.add_all([
            Activity(id=1, kind="transplant", cycle_id=1, title="ย้ายปลูก โต๊ะ 4", planned_date=date(2026, 1, 11), status="done", source="auto"),
            Activity(id=2, kind="general", title=encrypt_text("ซ่อมปั๊ม"), is_encrypted=True, planned_date=date(2026, 1, 12), source="manual"),
        ])
        fertilize = InputApplication(
            id=10, cycle_id=1, applied_date=date(2026, 1, 20), category="ปุ๋ย",
            note_encrypted=encrypt_text("หลังฝน").encode(), created_at=datetime(2026, 1, 20), updated_at=datetime(2026, 1, 20),
        )
        fertilize.items.extend([
            InputItem(item_name_encrypted=encrypt_text("ปุ๋ย").encode(), quantity_encrypted=encrypt_number("2").encode(), unit="kg", product_id=1),
            InputItem(item_name_encrypted=encrypt_text("น้ำหมัก").encode(), quantity_encrypted=encrypt_number("1").encode(), unit="ลิตร"),
        ])
        spray = InputApplication(id=11, cycle_id=1, applied_date=date(2026, 1, 25), category="ยาชีวภาพ", deleted_at=datetime(2026, 1, 26))
        db.add_all([fertilize, spray])
        db.add_all([
            StockMovement(id=1, product_id=1, quantity_delta=5, movement_type="receipt", occurred_at=datetime(2026, 1, 1)),
            StockMovement(id=2, product_id=1, quantity_delta=-2, movement_type="application",
                          source_type="input_application", source_id=10, occurred_at=datetime(2026, 1, 20)),
        ])
        db.commit()
    return engine, Session


def test_conversion_moves_input_applications_into_activities_once(tmp_path):
    engine, Session = _database(tmp_path)

    first = migrate_activity_records(engine)
    second = migrate_activity_records(engine)

    assert first == {"targets": 1, "done_dates": 1, "applications": 2, "items": 2, "movements": 1}
    assert second == {"targets": 0, "done_dates": 0, "applications": 0, "items": 0, "movements": 0}
    with Session() as db:
        transplant = db.get(Activity, 1)
        assert (transplant.done_on, transplant.started_on) == (date(2026, 1, 11), date(2026, 1, 11))
        assert [(t.crop_cycle_id, t.table_id, t.share) for t in db.scalars(select(ActivityTarget).where(ActivityTarget.activity_id == 1))] == [(1, 1, 1.0)]
        assert db.get(Activity, 2).done_on is None  # not done, so no finish date

        converted = db.scalar(select(Activity).where(Activity.legacy_input_application_id == 10))
        assert (converted.kind, converted.status, converted.source) == ("fertilize", "done", "manual")
        assert (converted.planned_date, converted.done_on, converted.cycle_id) == (date(2026, 1, 20), date(2026, 1, 20), 1)
        assert decrypt_text(converted.title) == "ปุ๋ย" and decrypt_text(converted.note_encrypted) == "หลังฝน"
        items = db.scalars(select(ActivityItem).where(ActivityItem.activity_id == converted.id).order_by(ActivityItem.id)).all()
        assert [(decrypt_text(i.item_name_encrypted), decrypt_number(i.quantity_encrypted), i.product_id) for i in items] == [
            ("ปุ๋ย", 2, 1), ("น้ำหมัก", 1, None),
        ]
        movement = db.get(StockMovement, 2)
        assert (movement.source_type, movement.source_id) == ("activity", converted.id)
        assert on_hand(db, 1) == 3

        spray = db.scalar(select(Activity).where(Activity.legacy_input_application_id == 11))
        assert spray.kind == "spray" and spray.deleted_at is not None
        assert decrypt_text(spray.title) == "ยาชีวภาพ"
    engine.dispose()


def test_finance_index_allows_one_entry_per_cycle_after_upgrade(tmp_path):
    engine, _Session = _database(tmp_path)
    migrate_activity_records(engine)
    with engine.connect() as connection:
        index_sql = connection.execute(text(
            "SELECT sql FROM sqlite_master WHERE name = 'uq_finance_entries_auto_posted_source'"
        )).scalar()
        assert "coalesce(crop_cycle_id, 0)" in index_sql
        assert connection.exec_driver_sql("PRAGMA integrity_check").scalar() == "ok"
    engine.dispose()
