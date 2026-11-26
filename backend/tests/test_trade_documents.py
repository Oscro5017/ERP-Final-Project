from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select, text, inspect
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.migrations import migrate_products_stock, migrate_stock_documents
from app.models import Customer, Product, Role, StockDocument, StockDocumentLine, StockMovement, Supplier, User
from app.security import get_current_user
from app.services.products_stock import on_hand
from app.services.secure_fields import decrypt_number, decrypt_text, encrypt_text


def make_db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def enable_fk(conn, _):
        conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    with session_local() as db:
        db.add_all([
            User(id=1, username="owner", password_hash="unused", role=Role.owner),
            User(id=2, username="developer", password_hash="unused", role=Role.developer),
        ])
        db.commit()
    return engine, session_local


class API:
    def __init__(self, session_local, role=Role.owner):
        self.session_local = session_local
        self.role = role
        self.client = None

    def __enter__(self):
        def override_db():
            with self.session_local() as db:
                yield db

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[get_current_user] = lambda: User(
            id=1 if self.role == Role.owner else 2,
            username=self.role.value,
            password_hash="unused",
            role=self.role,
        )
        self.client = TestClient(app)
        return self.client

    def __exit__(self, *_):
        app.dependency_overrides.clear()


def add_product(client, name="Test product", unit="kg"):
    response = client.post("/products", json={"category": "other", "name": name, "unit": unit})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def add_supplier(client, name="Test supplier"):
    response = client.post("/suppliers", json={"name": name, "contact": "TEL_MARKER", "area": "AREA_MARKER", "note": "SUPPLIER_NOTE_MARKER"})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def inbound(client, product_id, quantity=1, **extra):
    return client.post("/trade/inbound", json={
        "lines": [{"product_id": product_id, "quantity": quantity, "unit": "kg"}],
        **extra,
    })


def test_additive_migration_is_idempotent_and_creates_expected_foreign_keys():
    engine = create_engine("sqlite:///:memory:")
    migrate_products_stock(engine)
    migrate_stock_documents(engine)
    migrate_stock_documents(engine)
    inspector = inspect(engine)
    assert {"suppliers", "stock_documents", "stock_document_lines"} <= set(inspector.get_table_names())
    assert {fk["referred_table"] for fk in inspector.get_foreign_keys("stock_document_lines")} == {"products", "stock_documents"}
    assert {fk["referred_table"] for fk in inspector.get_foreign_keys("stock_documents")} >= {"suppliers", "customers", "crop_cycles", "users"}


def test_inbound_creates_document_and_positive_movement_from_document_id():
    _, Session = make_db()
    with API(Session) as client:
        product_id = add_product(client)
        response = inbound(client, product_id, 2.5)
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["doc_type"] == "inbound" and body["status"] == "posted"
        assert body["doc_no"].startswith("IN-")
        with Session() as db:
            movement = db.scalar(select(StockMovement).where(StockMovement.source_id == body["id"]))
            assert movement.source_type == "stock_document"
            assert movement.quantity_delta == 2.5
            assert on_hand(db, product_id) == 2.5


def test_outbound_multiple_lines_decrements_each_product():
    _, Session = make_db()
    with API(Session) as client:
        p1, p2 = add_product(client, "P1"), add_product(client, "P2")
        inbound(client, p1, 5)
        inbound(client, p2, 7)
        response = client.post("/trade/outbound", json={"lines": [
            {"product_id": p1, "quantity": 2, "unit": "kg"},
            {"product_id": p2, "quantity": 3, "unit": "kg"},
        ]})
        assert response.status_code == 201, response.text
        with Session() as db:
            assert on_hand(db, p1) == 3
            assert on_hand(db, p2) == 4
            assert db.query(StockDocumentLine).filter_by(document_id=response.json()["id"]).count() == 2


def test_outbound_allows_negative_and_returns_warning():
    _, Session = make_db()
    with API(Session) as client:
        product_id = add_product(client)
        response = client.post("/trade/outbound", json={"lines": [{"product_id": product_id, "quantity": 1, "unit": "kg"}]})
        assert response.status_code == 201
        assert response.json()["warnings"] == [f"negative_balance:{product_id}"]
        with Session() as db:
            assert on_hand(db, product_id) == -1


def test_inbound_rejects_customer_id():
    _, Session = make_db()
    with API(Session) as client:
        product_id = add_product(client)
        response = client.post("/trade/inbound", json={"customer_id": 4, "lines": [{"product_id": product_id, "quantity": 1}]})
        assert response.status_code == 422


def test_outbound_rejects_supplier_id():
    _, Session = make_db()
    with API(Session) as client:
        product_id = add_product(client)
        response = client.post("/trade/outbound", json={"supplier_id": 4, "lines": [{"product_id": product_id, "quantity": 1}]})
        assert response.status_code == 422


@pytest.mark.parametrize("quantity", [0, -1, "NaN", "Infinity", 0.0004])
def test_document_rejects_invalid_or_rounded_zero_quantity(quantity):
    _, Session = make_db()
    with API(Session) as client:
        product_id = add_product(client)
        response = inbound(client, product_id, quantity)
        assert response.status_code == 422
        with Session() as db:
            assert db.query(StockDocument).count() == 0
            assert db.query(StockMovement).count() == 0


def test_missing_product_rejects_without_partial_document_or_movement():
    _, Session = make_db()
    with API(Session) as client:
        response = inbound(client, 987654321, 1)
        assert response.status_code == 422
        with Session() as db:
            assert db.query(StockDocument).count() == db.query(StockDocumentLine).count() == db.query(StockMovement).count() == 0


def test_soft_deleted_product_rejects_without_partial_document_or_movement():
    _, Session = make_db()
    with API(Session) as client:
        product_id = add_product(client)
        client.delete(f"/products/{product_id}")
        response = inbound(client, product_id, 1)
        assert response.status_code == 422
        with Session() as db:
            assert db.query(StockDocument).count() == db.query(StockMovement).count() == 0


def test_second_invalid_line_rolls_back_everything():
    _, Session = make_db()
    with API(Session) as client:
        p1 = add_product(client, "Valid line")
        p2 = add_product(client, "Invalid line", "l")
        response = client.post("/trade/inbound", json={"lines": [
            {"product_id": p1, "quantity": 1, "unit": "kg"},
            {"product_id": p2, "quantity": -1, "unit": "kg"},
        ]})
        assert response.status_code == 422
        with Session() as db:
            assert db.query(StockDocument).count() == db.query(StockDocumentLine).count() == db.query(StockMovement).count() == 0


def test_unconvertible_unit_posts_document_with_warning_and_no_movement_for_line():
    _, Session = make_db()
    with API(Session) as client:
        product_id = add_product(client, unit="kg")
        response = inbound(client, product_id, 1, lines=[{"product_id": product_id, "quantity": 1, "unit": "l"}])
        # The helper's lines key is replaced; the unit mismatch is a warning under D10.
        assert response.status_code == 201, response.text
        assert response.json()["warnings"] == [f"unit_mismatch:{product_id}"]
        with Session() as db:
            assert db.query(StockMovement).count() == 0


def test_unit_price_calculates_line_amount_with_half_up_rounding():
    _, Session = make_db()
    with API(Session) as client:
        product_id = add_product(client)
        response = client.post("/trade/inbound", json={"lines": [{
            "product_id": product_id, "quantity": 1, "unit_price": "0.005",
        }]})
        assert response.status_code == 201, response.text
        body = response.json()
        assert Decimal(str(body["lines"][0]["unit_price"])) == Decimal("0.01")
        assert Decimal(str(body["lines"][0]["line_amount"])) == Decimal("0.01")
        assert body["total_amount"]["is_masked"] is False
        assert Decimal(str(body["total_amount"]["value"])) == Decimal("0.01")


def test_matching_supplied_line_amount_within_one_satang_is_accepted():
    _, Session = make_db()
    with API(Session) as client:
        product_id = add_product(client)
        response = client.post("/trade/inbound", json={"lines": [{
            "product_id": product_id, "quantity": 1, "unit_price": "1.00", "line_amount": "1.01",
        }]})
        assert response.status_code == 201, response.text


def test_mismatched_supplied_line_amount_rolls_back():
    _, Session = make_db()
    with API(Session) as client:
        product_id = add_product(client)
        response = client.post("/trade/inbound", json={"lines": [{
            "product_id": product_id, "quantity": 1, "unit_price": "1.00", "line_amount": "1.02",
        }]})
        assert response.status_code == 422
        with Session() as db:
            assert db.query(StockDocument).count() == db.query(StockMovement).count() == 0


def test_line_amount_without_unit_price_is_rejected():
    _, Session = make_db()
    with API(Session) as client:
        product_id = add_product(client)
        response = client.post("/trade/inbound", json={"lines": [{
            "product_id": product_id, "quantity": 1, "line_amount": "1.00",
        }]})
        assert response.status_code == 422


def test_no_price_has_no_money_tokens_or_total():
    _, Session = make_db()
    with API(Session) as client:
        product_id = add_product(client)
        response = inbound(client, product_id, 1)
        assert response.status_code == 201
        assert response.json()["total_amount"] is None
        with Session() as db:
            line = db.scalar(select(StockDocumentLine))
            assert line.unit_price_encrypted is None and line.line_amount_encrypted is None


def test_document_numbers_increment_per_day_and_type():
    from app.services import stock_documents

    _, Session = make_db()
    with API(Session) as client:
        product_id = add_product(client)
        first = inbound(client, product_id, 1, doc_date="2026-11-24").json()
        second = inbound(client, product_id, 1, doc_date="2026-11-24").json()
        outbound = client.post("/trade/outbound", json={"doc_date": "2026-11-24", "lines": [{"product_id": product_id, "quantity": 1}]}).json()
        next_day = inbound(client, product_id, 1, doc_date="2026-11-25").json()
        assert [first["doc_no"], second["doc_no"], outbound["doc_no"], next_day["doc_no"]] == [
            "IN-261124-001", "IN-261124-002", "OUT-261124-001", "IN-261125-001",
        ]


def test_document_void_reverses_movements_and_is_consistently_conflict_on_repeat():
    _, Session = make_db()
    with API(Session) as client:
        product_id = add_product(client)
        document = inbound(client, product_id, 2).json()
        assert client.post(f"/trade/documents/{document['id']}/void", json={"reason": "VOID_MARKER"}).status_code == 200
        assert client.post(f"/trade/documents/{document['id']}/void", json={"reason": "VOID_MARKER"}).status_code == 409
        with Session() as db:
            assert on_hand(db, product_id) == 0
            movement = db.scalar(select(StockMovement).where(StockMovement.source_id == document["id"]))
            assert movement.voided_at is not None
            saved = db.get(StockDocument, document["id"])
            assert decrypt_text(saved.void_reason_encrypted) == "VOID_MARKER"


def test_voided_document_cannot_be_edited():
    _, Session = make_db()
    with API(Session) as client:
        product_id = add_product(client)
        document = inbound(client, product_id, 1).json()
        client.post(f"/trade/documents/{document['id']}/void", json={})
        response = client.patch(f"/trade/documents/{document['id']}", json={"note": "new"})
        assert response.status_code == 409


def test_patch_accepts_note_and_reference_but_rejects_lines_and_quantities():
    _, Session = make_db()
    with API(Session) as client:
        product_id = add_product(client)
        document = inbound(client, product_id, 1).json()
        patched = client.patch(f"/trade/documents/{document['id']}", json={"note": "PRIVATE_NOTE", "reference_no": "REF-1"})
        assert patched.status_code == 200
        assert patched.json()["note"] == "PRIVATE_NOTE" and patched.json()["reference_no"] == "REF-1"
        rejected = client.patch(f"/trade/documents/{document['id']}", json={"lines": [], "quantity": 10})
        assert rejected.status_code == 422


def test_trade_document_filters_and_pagination():
    _, Session = make_db()
    with API(Session) as client:
        p1, p2 = add_product(client, "Filter one"), add_product(client, "Filter two")
        inbound_doc = inbound(client, p1, 1, doc_date="2026-11-23").json()
        outbound_doc = client.post("/trade/outbound", json={"doc_date": "2026-11-24", "lines": [{"product_id": p2, "quantity": 1}]}).json()
        filtered = client.get("/trade/documents", params={"doc_type": "inbound", "from": "2026-11-23", "to": "2026-11-23", "product_id": p1}).json()
        assert filtered["total"] == 1 and filtered["items"][0]["id"] == inbound_doc["id"]
        page = client.get("/trade/documents", params={"limit": 1, "offset": 1}).json()
        assert page["total"] == 2 and len(page["items"]) == 1
        assert client.get("/trade/documents", params={"from": "2026-11-25", "to": "2026-11-24"}).status_code == 422
        assert client.get("/trade/documents", params={"status": "nonsense"}).status_code == 422


def test_supplier_crud_encrypts_fields_duplicate_warns_and_soft_deletes():
    _, Session = make_db()
    with API(Session) as client:
        supplier_id = add_supplier(client, "MARKER_SUPPLIER")
        duplicate = add_supplier(client, " marker_supplier ")
        assert duplicate != supplier_id
        assert "duplicate_name" in client.get(f"/suppliers/{supplier_id}").json()["warnings"]
        with Session() as db:
            first = db.get(Supplier, supplier_id)
            assert decrypt_text(first.name_encrypted) == "MARKER_SUPPLIER"
            assert decrypt_text(first.contact_encrypted) == "TEL_MARKER"
            assert decrypt_text(first.area_encrypted) == "AREA_MARKER"
            assert decrypt_text(first.note_encrypted) == "SUPPLIER_NOTE_MARKER"
        updated = client.patch(f"/suppliers/{supplier_id}", json={"area": "NEW_AREA"})
        assert updated.status_code == 200 and updated.json()["area"] == "NEW_AREA"
        assert client.delete(f"/suppliers/{supplier_id}").status_code == 204
        listing = client.get("/suppliers").json()
        assert supplier_id not in [item["id"] for item in listing["items"]]


def test_deleted_supplier_cannot_be_used_on_new_inbound_but_old_document_is_readable():
    _, Session = make_db()
    with API(Session) as client:
        product_id = add_product(client)
        supplier_id = add_supplier(client, "Historical supplier")
        document = inbound(client, product_id, 1, supplier_id=supplier_id).json()
        client.delete(f"/suppliers/{supplier_id}")
        rejected = inbound(client, product_id, 1, supplier_id=supplier_id)
        assert rejected.status_code == 422
        old = client.get(f"/trade/documents/{document['id']}").json()
        assert old["supplier_name"] == "Historical supplier"


def test_outbound_requires_existing_customer_when_customer_is_supplied():
    _, Session = make_db()
    with API(Session) as client:
        product_id = add_product(client)
        response = client.post("/trade/outbound", json={"customer_id": 12345, "lines": [{"product_id": product_id, "quantity": 1}]})
        assert response.status_code == 422


def test_developer_gets_ciphertext_and_owner_gets_plaintext_for_supplier_and_document():
    _, Session = make_db()
    with API(Session) as client:
        product_id = add_product(client, "PRIVATE_PRODUCT")
        supplier_id = add_supplier(client, "PRIVATE_SUPPLIER")
        document = inbound(client, product_id, 1, supplier_id=supplier_id, note="PRIVATE_NOTE",
                           lines=[{"product_id": product_id, "quantity": 1, "unit": "kg", "unit_price": "98765.43"}]).json()
        assert document["note"] == "PRIVATE_NOTE"
        app.dependency_overrides[get_current_user] = lambda: User(id=2, username="developer", password_hash="unused", role=Role.developer)
        supplier_view = client.get(f"/suppliers/{supplier_id}").json()
        document_view = client.get(f"/trade/documents/{document['id']}").json()
        assert supplier_view["is_masked"] is True and supplier_view["name"] != "PRIVATE_SUPPLIER"
        assert document_view["is_masked"] is True and document_view["note"] != "PRIVATE_NOTE"
        assert document_view["lines"][0]["product_name"] != "PRIVATE_PRODUCT"
        assert document_view["lines"][0]["unit_price"] != "98765.43"
        assert document_view["total_amount"]["is_masked"] is True


def test_database_has_no_plaintext_markers_for_encrypted_supplier_document_and_money_fields():
    _, Session = make_db()
    with API(Session) as client:
        product_id = add_product(client, "DB_PRIVATE_PRODUCT")
        supplier_id = add_supplier(client, "DB_PRIVATE_SUPPLIER")
        document = inbound(client, product_id, 1, supplier_id=supplier_id, note="DB_PRIVATE_NOTE",
                           lines=[{"product_id": product_id, "quantity": 1, "unit": "kg", "unit_price": "98765.43"}]).json()
        with Session() as db:
            supplier = db.get(Supplier, supplier_id)
            doc = db.get(StockDocument, document["id"])
            line = db.scalar(select(StockDocumentLine).where(StockDocumentLine.document_id == doc.id))
            tokens = [supplier.name_encrypted, supplier.contact_encrypted, supplier.area_encrypted, supplier.note_encrypted,
                      doc.note_encrypted, line.unit_price_encrypted, line.line_amount_encrypted]
            raw = b" ".join(token for token in tokens if token)
            for marker in (b"DB_PRIVATE_SUPPLIER", b"TEL_MARKER", b"AREA_MARKER", b"SUPPLIER_NOTE_MARKER", b"DB_PRIVATE_NOTE", b"98765.43"):
                assert marker not in raw
            assert all(token.startswith(b"gAAAA") for token in tokens if token)


def test_bad_ciphertext_does_not_break_document_read_and_sets_decrypt_failed():
    _, Session = make_db()
    with API(Session) as client:
        product_id = add_product(client)
        document = inbound(client, product_id, 1, note="CORRUPT_NOTE",
                           lines=[{"product_id": product_id, "quantity": 1, "unit": "kg", "unit_price": "10.00"}]).json()
        with Session() as db:
            doc = db.get(StockDocument, document["id"])
            line = db.scalar(select(StockDocumentLine).where(StockDocumentLine.document_id == doc.id))
            doc.note_encrypted = b"invalid-token"
            line.line_amount_encrypted = b"invalid-token"
            db.commit()
        response = client.get(f"/trade/documents/{document['id']}")
        assert response.status_code == 200
        assert response.json()["decrypt_failed"] is True
        assert response.json()["total_amount"] is None


def test_trade_endpoints_require_authentication():
    _, Session = make_db()
    def override_db():
        with Session() as db:
            yield db
    app.dependency_overrides[get_db] = override_db
    try:
        client = TestClient(app)
        assert client.get("/trade/documents").status_code == 401
        assert client.get("/suppliers").status_code == 401
    finally:
        app.dependency_overrides.clear()


def test_naive_date_is_kept_as_local_bangkok_calendar_date(monkeypatch):
    from app.services import stock_documents

    monkeypatch.setattr(stock_documents, "_today_bangkok", lambda: date(2026, 11, 24))
    _, Session = make_db()
    with API(Session) as client:
        product_id = add_product(client)
        response = inbound(client, product_id, 1, doc_date="2026-11-24")
        assert response.status_code == 201
        assert response.json()["doc_date"] == "2026-11-24"
        assert response.json()["doc_no"] == "IN-261124-001"


def test_document_date_more_than_one_year_ahead_is_rejected(monkeypatch):
    from app.services import stock_documents

    monkeypatch.setattr(stock_documents, "_today_bangkok", lambda: date(2026, 11, 24))
    _, Session = make_db()
    with API(Session) as client:
        product_id = add_product(client)
        response = inbound(client, product_id, 1, doc_date="2027-11-25")
        assert response.status_code == 422


def test_duplicate_document_number_retry_uses_next_available_sequence():
    _, Session = make_db()
    with API(Session) as client:
        product_id = add_product(client)
        first = inbound(client, product_id, 1, doc_date="2026-11-24").json()
        with Session() as db:
            db.add(StockDocument(
                doc_no="IN-261124-005", doc_type="inbound", doc_date=date(2026, 11, 24), status="posted",
            ))
            db.commit()
        second = inbound(client, product_id, 1, doc_date="2026-11-24").json()
        assert first["doc_no"] == "IN-261124-001"
        assert second["doc_no"] == "IN-261124-006"


def test_movement_quantity_is_rounded_to_three_decimals_and_doc_line_is_consistent():
    _, Session = make_db()
    with API(Session) as client:
        product_id = add_product(client)
        response = inbound(client, product_id, "1.2345")
        assert response.status_code == 201
        assert response.json()["lines"][0]["quantity"] == 1.235
        with Session() as db:
            movement = db.scalar(select(StockMovement).where(StockMovement.source_id == response.json()["id"]))
            assert movement.quantity_delta == 1.235


def test_supplier_create_update_and_document_write_are_atomic_on_commit_failure(monkeypatch):
    _, Session = make_db()
    with API(Session) as client:
        product_id = add_product(client)
        session_class = Session.class_
        original = session_class.commit
        calls = {"count": 0}
        def fail_first(self):
            calls["count"] += 1
            if calls["count"] == 1:
                self.rollback()
                raise RuntimeError("synthetic commit failure")
            return original(self)
        monkeypatch.setattr(session_class, "commit", fail_first)
        with pytest.raises(RuntimeError):
            inbound(client, product_id, 1)
        monkeypatch.setattr(session_class, "commit", original)
        with Session() as db:
            assert db.query(StockDocument).count() == db.query(StockMovement).count() == 0
