from datetime import datetime

from pydantic import BaseModel, Field


class SalesCallbackStart(BaseModel):
    customer_id: int | None = None
    sales_id: int | None = None
    sales_phone: str | None = Field(default=None, max_length=32)
    customer_phone: str | None = Field(default=None, max_length=32)
    provider: str | None = Field(default=None, max_length=40)
    remark: str | None = Field(default=None, max_length=500)


class SalesCallbackWebhook(BaseModel):
    provider_call_id: str = Field(min_length=1, max_length=120)
    event_type: str = Field(min_length=1, max_length=60)
    status: str | None = Field(default=None, max_length=32)
    duration_seconds: int | None = Field(default=None, ge=0)
    recording_url: str | None = Field(default=None, max_length=500)
    transcript: str | None = Field(default=None, max_length=50000)
    failure_reason: str | None = Field(default=None, max_length=1000)
    payload: dict | None = None


class SalesCallbackOut(BaseModel):
    id: int
    customer_id: int
    sales_id: int
    call_attempt_id: int | None
    provider: str
    provider_call_id: str
    sales_phone: str
    customer_phone: str
    status: str
    failure_reason: str | None
    remark: str | None
    recording_url: str | None
    started_at: datetime | None
    bridged_at: datetime | None
    ended_at: datetime | None
    duration_seconds: int | None
    created_at: datetime
    updated_at: datetime
    customer_name: str | None = None
    sales_name: str | None = None
    call_status: str | None = None

    model_config = {"from_attributes": True}


class SalesCallbackListResponse(BaseModel):
    items: list[SalesCallbackOut]
    total: int
    page: int
    page_size: int
