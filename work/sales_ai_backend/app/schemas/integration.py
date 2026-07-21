from datetime import datetime

from pydantic import BaseModel, Field


class WebsiteLeadCreate(BaseModel):
    external_id: str | None = Field(default=None, max_length=120)
    name: str | None = Field(default=None, max_length=80)
    phone: str | None = Field(default=None, max_length=32)
    wechat_id: str | None = Field(default=None, max_length=80)
    wechat_nickname: str | None = Field(default=None, max_length=120)
    address: str | None = Field(default=None, max_length=255)
    source: str | None = Field(default=None, max_length=80)
    campaign: str | None = Field(default=None, max_length=120)
    page_url: str | None = Field(default=None, max_length=500)
    referrer: str | None = Field(default=None, max_length=500)
    message: str | None = Field(default=None, max_length=5000)
    utm_source: str | None = Field(default=None, max_length=120)
    utm_medium: str | None = Field(default=None, max_length=120)
    utm_campaign: str | None = Field(default=None, max_length=120)
    utm_term: str | None = Field(default=None, max_length=120)
    utm_content: str | None = Field(default=None, max_length=120)


class WebsiteLeadResponse(BaseModel):
    accepted: bool
    created: bool
    customer_id: int
    duplicate_of_id: int | None = None
    message: str


class IntegrationFollowupOut(BaseModel):
    id: int
    customer_id: int
    user_id: int
    content: str
    source: str
    status: str
    call_recording_id: int | None
    upload_record_id: int | None
    next_followup_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class IntegrationCallSummary(BaseModel):
    id: int
    call_mode: str
    call_status: str
    duration_seconds: int | None
    intent_level: str | None
    intent_score: int | None
    next_action: str | None
    created_at: datetime


class IntegrationAiRobotCallSummary(BaseModel):
    id: int
    provider: str
    status: str
    high_intent: bool
    intent_level: str | None
    intent_score: int | None
    duration_seconds: int | None
    created_at: datetime


class IntegrationCustomerOut(BaseModel):
    id: int
    name: str | None
    phone: str | None
    wechat_id: str | None
    wechat_nickname: str | None
    address: str | None
    source: str | None
    lead_source: str | None
    lead_status: str
    pipeline_stage: str
    intent_level: str
    intent_score: int
    demand_summary: str | None
    concerns: str | None
    product_interest: str | None
    budget: str | None
    purchase_time: str | None
    next_action: str | None
    owner_id: int | None
    owner_name: str | None = None
    last_followup_at: datetime | None
    created_at: datetime
    updated_at: datetime
    latest_followup: IntegrationFollowupOut | None = None
    latest_call: IntegrationCallSummary | None = None
    latest_ai_robot_call: IntegrationAiRobotCallSummary | None = None

    model_config = {"from_attributes": True}


class IntegrationLeadListResponse(BaseModel):
    items: list[IntegrationCustomerOut]
    total: int
    page: int
    page_size: int
