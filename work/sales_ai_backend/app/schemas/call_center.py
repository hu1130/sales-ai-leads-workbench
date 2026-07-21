from datetime import datetime

from pydantic import BaseModel, Field


class CallCampaignCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    scenario: str = "lead_filter"
    script_id: int | None = None
    owner_id: int | None = None
    description: str | None = None
    planned_start_at: datetime | None = None
    planned_end_at: datetime | None = None
    customer_ids: list[int] = Field(default_factory=list)
    assigned_user_id: int | None = None


class CallCampaignUpdate(BaseModel):
    name: str | None = None
    scenario: str | None = None
    script_id: int | None = None
    owner_id: int | None = None
    description: str | None = None
    planned_start_at: datetime | None = None
    planned_end_at: datetime | None = None


class CallCampaignOut(BaseModel):
    id: int
    name: str
    scenario: str
    script_id: int | None
    status: str
    owner_id: int | None
    description: str | None
    total_count: int
    called_count: int
    connected_count: int
    high_intent_count: int
    planned_start_at: datetime | None
    planned_end_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    created_by: int | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CallCampaignListResponse(BaseModel):
    items: list[CallCampaignOut]
    total: int
    page: int
    page_size: int


class CallTargetImport(BaseModel):
    customer_ids: list[int]
    assigned_user_id: int | None = None
    keep_customer_owner: bool = True


class CallTargetAssign(BaseModel):
    assigned_user_id: int


class CallTargetUpdate(BaseModel):
    assigned_user_id: int | None = None
    status: str | None = None
    next_followup_at: datetime | None = None


class CallTargetOut(BaseModel):
    id: int
    campaign_id: int
    customer_id: int
    assigned_user_id: int | None
    phone: str | None
    contact_name: str | None
    status: str
    last_attempt_id: int | None
    call_count: int
    last_called_at: datetime | None
    next_followup_at: datetime | None
    created_at: datetime
    updated_at: datetime
    customer_name: str | None = None
    customer_intent_level: str | None = None
    customer_intent_score: int | None = None
    customer_demand_summary: str | None = None
    customer_next_action: str | None = None
    assigned_user_name: str | None = None

    model_config = {"from_attributes": True}


class CallTargetListResponse(BaseModel):
    items: list[CallTargetOut]
    total: int
    page: int
    page_size: int


class CallAttemptCreate(BaseModel):
    target_id: int | None = None
    campaign_id: int | None = None
    customer_id: int | None = None
    phone: str | None = None
    call_mode: str = "manual"


class CallAttemptFinish(BaseModel):
    call_status: str
    duration_seconds: int | None = None
    remark: str | None = None
    next_followup_at: datetime | None = None


class CallTranscriptSubmit(BaseModel):
    transcript: str = Field(min_length=2, max_length=50000)


class CallAttemptOut(BaseModel):
    id: int
    campaign_id: int | None
    target_id: int | None
    customer_id: int | None
    sales_id: int | None
    phone: str | None
    call_mode: str
    call_status: str
    started_at: datetime | None
    ended_at: datetime | None
    duration_seconds: int | None
    call_recording_id: int | None
    upload_record_id: int | None
    transcript: str | None
    ai_analysis_id: int | None
    intent_level: str | None
    intent_score: int | None
    next_action: str | None
    remark: str | None
    created_at: datetime
    updated_at: datetime
    customer_name: str | None = None
    sales_name: str | None = None
    campaign_name: str | None = None

    model_config = {"from_attributes": True}


class CallAttemptListResponse(BaseModel):
    items: list[CallAttemptOut]
    total: int
    page: int
    page_size: int


class CallOverviewResponse(BaseModel):
    total_campaigns: int
    running_campaigns: int
    total_targets: int
    pending_targets: int
    called_targets: int
    connected_attempts: int
    total_attempts: int
    high_intent_attempts: int
    connect_rate: float
