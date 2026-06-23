from datetime import datetime

from pydantic import BaseModel


class CustomerBase(BaseModel):
    name: str | None = None
    phone: str | None = None
    address: str | None = None
    source: str | None = None


class CustomerCreate(CustomerBase):
    owner_id: int | None = None


class CustomerUpdate(CustomerBase):
    intent_level: str | None = None
    intent_score: int | None = None
    demand_summary: str | None = None
    concerns: str | None = None
    product_interest: str | None = None
    budget: str | None = None
    purchase_time: str | None = None
    next_action: str | None = None


class CustomerOut(CustomerBase):
    id: int
    owner_id: int | None
    intent_level: str
    intent_score: int
    demand_summary: str | None
    concerns: str | None
    product_interest: str | None
    budget: str | None
    purchase_time: str | None
    next_action: str | None
    last_followup_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CustomerListResponse(BaseModel):
    items: list[CustomerOut]
    total: int
    page: int
    page_size: int

