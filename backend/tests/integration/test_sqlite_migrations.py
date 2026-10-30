"""Exercise the real Alembic chain against an empty SQLite database."""
import os
import sqlite3
import subprocess
import sys
from pathlib import Path


def test_fresh_sqlite_upgrade_creates_foreign_keys_and_retail_tables(tmp_path):
    db_path = tmp_path / "fresh.sqlite"
    env = {**os.environ, "USE_CLOUD_DB": "no", "LOCAL_DATABASE_URL": f"sqlite+aiosqlite:///{db_path}"}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=Path(__file__).resolve().parents[2], env=env, capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stderr
    with sqlite3.connect(db_path) as db:
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        assert {"retail_products", "retail_stock_movements"} <= tables
        for table, column in [("organization_members", "family_owner_member_id"),
                              ("attendance", "credit_subscription_id"),
                              ("subscriptions", "scheduled_plan_id"),
                              ("leads", "first_contacted_by_user_id")]:
            assert column in {row[3] for row in db.execute(f"PRAGMA foreign_key_list({table})")}
