from datetime import date
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from app.database import Base, get_db
from app.main import app
from app.models import Batch, CropCycle, CropType, Role, Table, User, StockMovement, FinanceEntry
from app.security import get_current_user
from app.services.products_stock import on_hand
from app.services.secure_fields import decrypt_number


def test_phase2_workflow_harvest_inputs_trade_finance_and_void():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    @event.listens_for(engine, "connect")
    def enable_fk(conn, _): conn.execute("PRAGMA foreign_keys=ON")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    with Session() as db:
        db.add_all([User(id=1, username="owner", password_hash="unused", role=Role.owner),
                    User(id=2, username="developer", password_hash="unused", role=Role.developer),
                    Table(id=1, table_number=1), Batch(id=1, batch_number=1, start_date=date(2025,1,1)),
                    CropType(id=1, name="Green Oak", nursery_days=14, growth_days=30)])
        db.commit()
    def override_db():
        with Session() as db: yield db
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: User(id=1, username="owner", password_hash="x", role=Role.owner)
    try:
        client = TestClient(app)
        product = client.post("/products", json={"category":"vegetable","name":"E2E Oak","unit":"kg"}).json()["id"]
        assert client.patch("/crop-types/1/product-mapping", json={"product_id":product}).status_code == 200
        cycle = client.post("/crop-cycles", json={"table_id":1,"batch_id":1,"crop_type_id":1,"nursery_start":"2025-01-01","harvest_quantity_kg":30}).json()["id"]
        supplier = client.post("/suppliers", json={"name":"E2E supplier"}).json()["id"]
        inbound = client.post("/trade/inbound", json={"doc_date":"2025-03-01","supplier_id":supplier,"lines":[{"product_id":product,"quantity":2,"unit":"kg","unit_price":10}]})
        assert inbound.status_code == 201
        outgoing = client.post("/trade/outbound", json={"doc_date":"2025-03-02","crop_cycle_id":cycle,"lines":[{"product_id":product,"quantity":20,"unit":"kg","unit_price":90}]})
        assert outgoing.status_code == 201
        with Session() as db:
            assert on_hand(db, product) == 12
            assert db.scalar(select(FinanceEntry).where(FinanceEntry.source_id==outgoing.json()["id"])).direction == "income"
        voided = client.post(f"/trade/documents/{outgoing.json()['id']}/void", json={"reason":"e2e"})
        assert voided.status_code == 200
        with Session() as db:
            assert on_hand(db, product) == 32
            assert db.scalar(select(StockMovement).where(StockMovement.source_id==outgoing.json()["id"], StockMovement.voided_at.is_(None))) is None
    finally:
        app.dependency_overrides.clear()
