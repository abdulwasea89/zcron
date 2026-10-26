"""Admin evidence fields submitted to Stripe for a card dispute."""

from pydantic import BaseModel, ConfigDict, Field


class DisputeEvidenceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customer_name: str | None = Field(default=None, max_length=500)
    customer_email_address: str | None = Field(default=None, max_length=500)
    customer_communication: str | None = Field(default=None, max_length=10_000)
    product_description: str | None = Field(default=None, max_length=10_000)
    service_date: str | None = Field(default=None, max_length=100)
    access_activity_log: str | None = Field(default=None, max_length=10_000)
    refund_policy: str | None = Field(default=None, max_length=10_000)
    refund_policy_disclosure: str | None = Field(default=None, max_length=10_000)
    cancellation_policy: str | None = Field(default=None, max_length=10_000)
    cancellation_policy_disclosure: str | None = Field(default=None, max_length=10_000)
    uncategorized_text: str | None = Field(default=None, max_length=10_000)
    uncategorized_file: str | None = Field(default=None, max_length=255)
    submit: bool = False
