import os
import sqlite3
import subprocess
import sys
from pathlib import Path

from tests.test_backend_hygiene_security import TEST_FERNET_KEY

BACKEND = Path(__file__).resolve().parents[1]


def run_seed(*args):
    env = {**os.environ, "ENCRYPTION_KEY": TEST_FERNET_KEY, "APP_ENV": "development"}
    env.pop("DATABASE_URL", None)
    return subprocess.run([sys.executable, "-m", "scripts.seed_demo", *args], cwd=BACKEND, env=env,
                          capture_output=True, text=True, encoding="utf-8", timeout=300)


def test_demo_database_covers_every_area(tmp_path):
    target = tmp_path / "demo.db"
    result = run_seed(str(target))
    assert result.returncode == 0, result.stdout + result.stderr
    with sqlite3.connect(target) as db:
        count = lambda table, where="1=1": db.execute(f"select count(*) from {table} where {where}").fetchone()[0]  # noqa: E731
        assert count("products") == 10
        assert count("crop_cycles", "deleted_at is null") == 12
        assert {row[0] for row in db.execute("select status from crop_cycles where deleted_at is null")} == {
            "nursery", "bushed", "harvesting", "harvested"}
        assert count("harvest_entries", "voided_at is null") == 11
        assert count("activities", "kind = 'nursery'") == 12
        assert count("stock_documents", "status = 'void'") == 1
        assert count("sales_orders") == 5
        assert count("stock_waste") == 1
        assert count("finance_entries", "status = 'posted'") > 5
        assert count("insights") == 3 and count("weather_logs") == 30

    again = run_seed(str(target))
    assert again.returncode != 0 and "--replace" in again.stdout + again.stderr


def test_demo_refuses_the_real_database():
    result = run_seed("erp.db", "--replace")
    assert result.returncode != 0 and "erp.db" in result.stdout + result.stderr
