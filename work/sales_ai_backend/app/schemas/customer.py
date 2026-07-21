from datetime import datetime

from pydantic import BaseModel, Field


class CustomerBase(BaseModel):
    name: str | None = None
    wechat_id: str | None = None
    wechat_nickname: str | None = None
    phone: str | None = None
    address: str | None = None
    source: str | None = None
    lead_source: str | None = None


class CustomerCreate(CustomerBase):
    owner_id: int | None = None
    lead_status: str | None = None
    demand_summary: str | None = None
    next_action: str | None = None


class CustomerUpdate(CustomerBase):
    owner_id: int | None = None
    lead_status: str | None = None
    pipeline_stage: str | None = None
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
    owner_name: str | None = None
    owner_username: str | None = None
    lead_status: str
    pipeline_stage: str = "lead"
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


class CustomerDuplicateGroup(BaseModel):
    reason: str
    match_value: str
    customers: list[CustomerOut]


class CustomerDuplicateResponse(BaseModel):
    items: list[CustomerDuplicateGroup]
    total: int


class CustomerMergeRequest(BaseModel):
    source_customer_id: int


class CustomerRandomAssignRequest(BaseModel):
    sales_user_ids: list[int] | None = None
    limit: int | None = Field(default=None, ge=1, le=1000)


class CustomerRandomAssignItem(BaseModel):
    sales_id: int
    sales_name: str
    assigned_count: int


class CustomerRandomAssignResponse(BaseModel):
    assigned_count: int
    sales_count: int
    remaining_unassigned: int
    items: list[CustomerRandomAssignItem]
