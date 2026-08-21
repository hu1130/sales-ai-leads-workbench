from datetime import datetime, timedelta
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class AiRobotCampaignStart(BaseModel):
    provider: str | None = Field(default=None, max_length=40)
    max_calls: int = Field(default=20, ge=1, le=200)
    script: str | None = Field(default=None, max_length=5000)
    only_pending: bool = True


class AiRobotWebhook(BaseModel):
    provider_call_id: str
    event_type: str
    status: str | None = None
    duration_seconds: int | None = None
    recording_url: str | None = None
    transcript: str | None = None
    failure_reason: str | None = None
    raw_payload: dict[str, Any] | None = None


class AiRobotCallOut(BaseModel):
    id: int
    campaign_id: int | None
    target_id: int | None
    customer_id: int | None
    owner_id: int | None
    call_attempt_id: int | None
    provider: str
    provider_call_id: str
    phone: str | None
    status: str
    failure_reason: str | None
    recording_url: str | None
    transcript: str | None
    intent_level: str | None
    intent_score: int | None
    high_intent: bool
    started_at: datetime | None
    answered_at: datetime | None
    ended_at: datetime | None
    duration_seconds: int | None
    created_at: datetime
    updated_at: datetime
    customer_name: str | None = None
    campaign_name: str | None = None
    target_status: str | None = None
    call_status: str | None = None


class AiRobotCampaignStartResponse(BaseModel):
    campaign_id: int
    launched: int
    skipped: int
    items: list[AiRobotCallOut]


class AiRobotCallListResponse(BaseModel):
    items: list[AiRobotCallOut]
    total: int
    page: int
    page_size: int


class AiRobotSyncPendingResponse(BaseModel):
    synced: int
    failed: int
    items: list[AiRobotCallOut]
    errors: list[str] = Field(default_factory=list)


class AiRobotStopRequest(BaseModel):
    call_task_id: str = Field(pattern=r"^clt_[A-Za-z0-9][A-Za-z0-9_-]{1,126}$")
    provider_task_ref: str = Field(pattern=r"^ptk_[A-Za-z0-9][A-Za-z0-9_-]{1,126}$")
    provider_call_id: str = Field(min_length=1, max_length=120)
    reason_code: Literal[
        "USER_REQUESTED",
        "AUTO_POLICY",
        "CAMPAIGN_PAUSED",
        "SYSTEM_ROLLBACK",
        "TEST_TEARDOWN",
    ]
    requested_at: datetime
    trace_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{7,127}$")

    @field_validator("requested_at")
    @classmethod
    def requested_at_must_be_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != timedelta(0):
            raise ValueError("requested_at must be an ISO-8601 UTC timestamp")
        return value


class AiRobotStopResponse(BaseModel):
    accepted: bool
    status: Literal[
        "CANCEL_REQUESTED",
        "CANCELLED",
        "ALREADY_TERMINAL",
        "NOT_FOUND",
        "NOT_STOPPABLE",
        "UNKNOWN",
        "FAILED",
    ]
    robot_call_id: int
    provider: str
    provider_call_id: str
    receipt_id: str
    raw_status: str
    replayed: bool
