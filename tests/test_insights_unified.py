from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.migrations import migrate_unified_insights
from app.models import Batch, CropCycle, CropType, Insight, Recommendation, Role, Table, Task, User
from app.security import get_current_user
from app.services.secure_fields import decrypt_text, encrypt_text


def make_db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def enable_fk(conn, _):
        conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    with Session() as db:
        db.add_all([
            User(id=1, username="owner", password_hash="unused", role=Role.owner),
            User(id=2, username="developer", password_hash="unused", role=Role.developer),
            Table(id=1, table_number=1),
            Batch(id=1, batch_number=1, start_date=date(2025, 1, 1)),
            CropType(id=1, name="Green Oak", nursery_days=14, growth_days=30),
            CropCycle(id=1, table_id=1, batch_id=1, crop_type_id=1, nursery_start=date(2025, 1, 1), cycle_code="250101"),
        ])
        db.commit()
    return engine, Session


class API:
    def __init__(self, Session, role=Role.owner):
        self.Session = Session
        self.role = role

    def __enter__(self):
        def override_db():
            with self.Session() as db:
                yield db

        app.dependency_overrides[get_db] = override_db
        user_id = 1 if self.role == Role.owner else 2
        app.dependency_overrides[get_current_user] = lambda: User(
            id=user_id, username=self.role.value, password_hash="unused", role=self.role
        )
        self.client = TestClient(app)
        return self.client

    def __exit__(self, *_):
        app.dependency_overrides.clear()


def test_recommendation_migration_is_additive_encrypted_and_idempotent():
    engine, Session = make_db()
    with Session() as db:
        db.add(Recommendation(
            kind="recommendation",
            title="LEGACY_TITLE_MARKER",
            message="LEGACY_MESSAGE_MARKER",
            reason="LEGACY_REASON_MARKER",
            status="pending",
        ))
        db.commit()
    migrate_unified_insights(engine)
    migrate_unified_insights(engine)
    with Session() as db:
        rows = db.scalars(select(Insight)).all()
        legacy = db.scalar(select(Recommendation))
        assert len(rows) == 1
        row = rows[0]
        assert row.legacy_recommendation_id == legacy.id
        assert row.status == "new" and row.kind == "recommendation" and row.source == "rule"
        assert decrypt_text(row.title_encrypted) == "LEGACY_TITLE_MARKER"
        assert "LEGACY_MESSAGE_MARKER" in decrypt_text(row.body_encrypted)
        assert "LEGACY_REASON_MARKER" in decrypt_text(row.body_encrypted)
        assert b"LEGACY_TITLE_MARKER" not in row.title_encrypted


def test_unified_insight_owner_reads_plaintext_and_developer_gets_ciphertext():
    _engine, Session = make_db()
    with Session() as db:
        row = Insight(
            kind="insight", source="rule", title_encrypted=encrypt_text("PRIVATE_TITLE").encode("ascii"),
            body_encrypted=encrypt_text("PRIVATE_BODY").encode("ascii"),
            severity="high", status="new",
        )
        db.add(row)
        db.commit()
        insight_id = row.id
    with API(Session) as client:
        response = client.get(f"/insights/{insight_id}")
        assert response.status_code == 200 and response.json()["title"] == "PRIVATE_TITLE"
    with API(Session, Role.developer) as client:
        response = client.get(f"/insights/{insight_id}")
        assert response.status_code == 200 and response.json()["is_masked"] is True
        assert response.json()["title"] != "PRIVATE_TITLE" and response.json()["body"] != "PRIVATE_BODY"


def test_insight_list_filters_paginates_and_updates_status():
    _engine, Session = make_db()
    with Session() as db:
        for kind, status in (("insight", "new"), ("alert", "seen"), ("recommendation", "new")):
            db.add(Insight(kind=kind, source="manual", title_encrypted=encrypt_text(kind).encode("ascii"), body_encrypted=encrypt_text("body").encode("ascii"), severity="info", status=status))
        db.commit()
    with API(Session) as client:
        page = client.get("/insights?status=new&limit=1")
        assert page.status_code == 200 and page.json()["total"] == 2 and len(page.json()["items"]) == 1
        filtered = client.get("/insights?kind=alert&status=seen")
        assert filtered.json()["total"] == 1
        insight_id = filtered.json()["items"][0]["id"]
        updated = client.patch(f"/insights/{insight_id}/status", json={"status": "dismissed"})
        assert updated.status_code == 200 and updated.json()["status"] == "dismissed"
        assert client.patch(f"/insights/{insight_id}/status", json={"status": "pending"}).status_code == 422
        assert client.get("/insights/999").status_code == 404


def test_insight_endpoints_require_authentication():
    _engine, Session = make_db()
    with API(Session) as client:
        app.dependency_overrides.pop(get_current_user, None)
        assert client.get("/insights").status_code == 401
        assert client.patch("/insights/1/status", json={"status": "seen"}).status_code == 401
