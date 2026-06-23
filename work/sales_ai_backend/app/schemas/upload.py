from datetime import datetime

from pydantic import BaseModel

from app.schemas.analysis import AIAnalysisOut


class UploadCreateResponse(BaseModel):
    id: int
    status: str
    message: str


class UploadOut(BaseModel):
    id: int
    customer_id: int | None
    uploader_id: int | None
    file_type: str
    file_name: str
    status: str
    error_message: str | None
    created_at: datetime
    updated_at: datetime
    analysis: AIAnalysisOut | None = None

    model_config = {"from_attributes": True}


class UploadListResponse(BaseModel):
    items: list[UploadOut]
    total: int
    page: int
    page_size: int
