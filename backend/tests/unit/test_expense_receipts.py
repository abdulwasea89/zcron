import hashlib
import tempfile
import struct
import zlib
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, UploadFile
from sqlalchemy import create_engine
from sqlmodel import Session, SQLModel, select
from starlette.requests import Request

from app.api.v1.routes import expenses
from app.models.audit_log import AuditLog
from app.models.expense_receipt import ExpenseReceipt
from app.models.operating_expense import OperatingExpense


def png(pixel=b"\xff\xff\xff"):
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">2I5B", 1, 1, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"\x00" + pixel)) + chunk(b"IEND", b""))


def upload(image, filename="receipt.png"):
    file = tempfile.SpooledTemporaryFile(max_size=6 * 1024 * 1024)
    file.write(image)
    file.seek(0)
    return UploadFile(file, filename=filename)


@pytest.fixture
def store(monkeypatch):
    async def inline_validation(function, *args):
        # Keep real image validation; thread-pool scheduling is outside this database test.
        return function(*args)

    monkeypatch.setattr(expenses, "run_in_threadpool", inline_validation)
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as db:
        class AsyncFacade:
            async def get(self, *args, **kwargs):
                return db.get(*args, **kwargs)

            async def execute(self, statement):
                return db.execute(statement)

            async def flush(self):
                db.flush()

            def add(self, row):
                db.add(row)

        db.add(OperatingExpense(id="expense", organization_id="gym", category="utilities", description="Power",
                                amount=Decimal("20.00"), currency="USD", incurred_on=date(2026, 1, 1), created_by="owner"))
        db.commit()
        yield db, AsyncFacade()
    engine.dispose()


def request():
    return Request({"type": "http", "headers": [], "client": ("127.0.0.1", 1000)})


@pytest.mark.asyncio
async def test_expense_receipt_upload_replay_download_and_ledger_metadata(store):
    db, session = store
    ctx = SimpleNamespace(org_id="gym", user_id="owner")
    image = png()
    for key in ("upload", "upload", "same-file-new-key"):
        await expenses.attach_receipt("expense", request(), upload(image, "untrusted.svg"),
                                      idempotency_key=key, ctx=ctx, session=session)
        db.commit()
    receipt = db.get(ExpenseReceipt, "expense")
    assert receipt.media_type == "image/png"
    assert receipt.sha256 == hashlib.sha256(image).hexdigest()
    assert len(db.exec(select(AuditLog).where(AuditLog.action == "expense.receipt_attached")).all()) == 1
    output = await expenses.list_expenses(ctx=ctx, session=session)
    assert output.items[0].has_receipt is True
    assert "image_data" not in output.model_dump_json()
    download = await expenses.download_receipt("expense", request(), ctx=ctx, session=session)
    assert download.body == image
    assert download.headers["cache-control"] == "private, no-store"
    assert download.headers["content-type"] == "image/png"
    assert "attachment" in download.headers["content-disposition"]
    with pytest.raises(HTTPException) as error:
        await expenses.attach_receipt("expense", request(), upload(png(b"\x00\x00\x00")),
                                      idempotency_key="different", ctx=ctx, session=session)
    assert error.value.status_code == 409
    assert db.get(ExpenseReceipt, "expense").image_data == image


@pytest.mark.asyncio
@pytest.mark.parametrize("image,status", [(b"", 422), (b"<svg>unsafe</svg>", 422),
                                          (b"not an image", 422), (b"x" * (5 * 1024 * 1024 + 1), 413)])
async def test_bad_upload_does_not_attach_evidence(store, image, status):
    db, session = store
    with pytest.raises(HTTPException) as error:
        await expenses.attach_receipt("expense", request(), upload(image),
                                      idempotency_key="bad-image", ctx=SimpleNamespace(org_id="gym", user_id="owner"),
                                      session=session)
    assert error.value.status_code == status
    assert db.get(ExpenseReceipt, "expense") is None


@pytest.mark.asyncio
async def test_foreign_workspace_cannot_read_or_upload_receipt(store):
    _, session = store
    ctx = SimpleNamespace(org_id="foreign", user_id="owner")
    with pytest.raises(HTTPException) as error:
        await expenses.download_receipt("expense", request(), ctx=ctx, session=session)
    assert error.value.status_code == 404
    with pytest.raises(HTTPException) as error:
        await expenses.attach_receipt("expense", request(), upload(png()),
                                      idempotency_key="foreign", ctx=ctx, session=session)
    assert error.value.status_code == 404


@pytest.mark.asyncio
async def test_void_keeps_existing_evidence_readable_but_blocks_new_uploads(store):
    from app.core.security import now_utc

    db, session = store
    ctx = SimpleNamespace(org_id="gym", user_id="owner")
    await expenses.attach_receipt("expense", request(), upload(png()), idempotency_key="before-void", ctx=ctx, session=session)
    db.get(OperatingExpense, "expense").voided_at = now_utc()
    db.commit()
    assert (await expenses.download_receipt("expense", request(), ctx=ctx, session=session)).body == png()
    with pytest.raises(HTTPException) as error:
        await expenses.attach_receipt("expense", request(), upload(png()), idempotency_key="after-void", ctx=ctx, session=session)
    assert error.value.status_code == 409


def test_receipt_migration_keeps_existing_expense_rows(monkeypatch):
    from importlib import import_module

    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    migration = import_module("app.db.migrations.versions.h0c1d2e3f4g5_expense_receipts")
    engine = create_engine("sqlite://")
    try:
        with engine.begin() as connection:
            for table in ("operating_expenses", "organizations", "users"):
                connection.exec_driver_sql(f"CREATE TABLE {table} (id VARCHAR PRIMARY KEY)")
            connection.exec_driver_sql("INSERT INTO operating_expenses VALUES ('existing')")
            monkeypatch.setattr(migration, "op", Operations(MigrationContext.configure(connection)))
            migration.upgrade()
            assert connection.exec_driver_sql("SELECT id FROM operating_expenses").scalar_one() == "existing"
            migration.downgrade()
            assert connection.exec_driver_sql("SELECT id FROM operating_expenses").scalar_one() == "existing"
    finally:
        engine.dispose()
