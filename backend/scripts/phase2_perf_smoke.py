"""Measure finance summary and dashboard latency over 2,000 encrypted entries.

Run with: python -m scripts.phase2_perf_smoke
The script uses a temporary SQLite database and never reads the farm database.
"""

from __future__ import annotations

import os

os.environ["ENCRYPTION_KEY"] = "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA="
os.environ["JWT_SECRET"] = "phase2-performance-smoke-local-only-secret"

from datetime import date
from decimal import Decimal
from statistics import median
from tempfile import TemporaryDirectory
from time import perf_counter

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app
from app.models import FinanceEntry, Role, User
from app.security import get_current_user
from app.services.secure_fields import encrypt_number, encrypt_text


ENTRY_COUNT = 2_000
SAMPLE_COUNT = 8


def main() -> None:
    with TemporaryDirectory(prefix="phase2-perf-") as temp_dir:
        engine = create_engine(f"sqlite:///{temp_dir}/phase2-perf.db")
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
        today = date.today()
        with Session() as db:
            db.add(User(id=1, username="perf-owner", password_hash="unused", role=Role.owner))
            db.flush()
            db.add_all([
                FinanceEntry(
                    entry_date=today,
                    direction="income" if index % 2 == 0 else "expense",
                    category="sale" if index % 2 == 0 else "purchase",
                    amount_encrypted=encrypt_number(Decimal("123.45")).encode("ascii"),
                    description_encrypted=encrypt_text(f"performance-row-{index}").encode("ascii"),
                    is_auto=False,
                    status="posted",
                    created_by=1,
                )
                for index in range(ENTRY_COUNT)
            ])
            db.commit()

        def override_db():
            with Session() as db:
                yield db

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[get_current_user] = lambda: User(
            id=1, username="perf-owner", password_hash="unused", role=Role.owner
        )
        try:
            with TestClient(app) as client:
                first_day = today.replace(day=1).isoformat()
                summary_path = f"/finance/summary?from={first_day}&to={today.isoformat()}"
                targets = {
                    "finance_summary": summary_path,
                    "dashboard_summary": "/dashboard/summary",
                }
                for name, path in targets.items():
                    timings = []
                    for iteration in range(SAMPLE_COUNT + 2):
                        started = perf_counter()
                        response = client.get(path)
                        elapsed_ms = (perf_counter() - started) * 1000
                        if response.status_code != 200:
                            raise RuntimeError(f"{name} failed: {response.status_code} {response.text}")
                        if iteration >= 2:
                            timings.append(elapsed_ms)
                    print(
                        f"{name}: rows={ENTRY_COUNT} samples={SAMPLE_COUNT} "
                        f"median_ms={median(timings):.2f} max_ms={max(timings):.2f}"
                    )
                print(f"database=temporary SQLite | machine=local host | as_of={today.isoformat()}")
        finally:
            app.dependency_overrides.clear()
            engine.dispose()


if __name__ == "__main__":
    main()
