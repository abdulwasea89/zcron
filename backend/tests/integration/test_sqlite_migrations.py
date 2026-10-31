"""Exercise the real Alembic chain against an empty SQLite database."""
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine

from app.db.session import _upgrade_sqlite_late_migration_columns


def test_existing_sqlite_audit_logs_gain_chain_key():
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE audit_logs (id TEXT PRIMARY KEY)")
        connection.exec_driver_sql("INSERT INTO audit_logs (id) VALUES ('existing')")
        _upgrade_sqlite_late_migration_columns(connection)
        _upgrade_sqlite_late_migration_columns(connection)
        connection.exec_driver_sql("INSERT INTO audit_logs (id, chain_key) VALUES ('new', 'lane')")
        assert connection.exec_driver_sql("SELECT id, chain_key FROM audit_logs ORDER BY id").all() == [
            ("existing", None), ("new", "lane")
        ]
        indexes = connection.exec_driver_sql("PRAGMA index_list(audit_logs)").all()
        assert any(row[1] == "ix_audit_logs_chain_key" for row in indexes)


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
