"""Original evidence for one recorded operating expense."""

from datetime import datetime

from sqlalchemy import Column, LargeBinary
from sqlmodel import Field, SQLModel

from app.models.base import utcnow


class ExpenseReceipt(SQLModel, table=True):
    __tablename__ = "operating_expense_receipts"

    expense_id: str = Field(primary_key=True, foreign_key="operating_expenses.id")
    organization_id: str = Field(index=True, foreign_key="organizations.id")
    # shortcut: originals are capped at 5MB in the database; move to blob storage when volume requires it.
    image_data: bytes = Field(sa_column=Column(LargeBinary, nullable=False))
    media_type: str
    sha256: str
    uploaded_by: str = Field(foreign_key="users.id")
    uploaded_at: datetime = Field(default_factory=utcnow)
