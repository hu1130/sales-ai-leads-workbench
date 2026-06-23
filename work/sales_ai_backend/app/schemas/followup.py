from datetime import datetime

from pydantic import BaseModel


class FollowupCreate(BaseModel):
    content: str
    next_followup_at: datetime | None = None


class FollowupOut(BaseModel):
    id: int
    customer_id: int
    user_id: int
    content: str
    source: str
    call_recording_id: int | None
    upload_record_id: int | None
    next_followup_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}
