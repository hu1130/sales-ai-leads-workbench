from datetime import datetime

from pydantic import BaseModel


class AIAnalysisOut(BaseModel):
    id: int
    upload_record_id: int
    customer_id: int | None
    raw_text: str | None
    summary: str | None
    customer_name: str | None
    customer_wechat_id: str | None = None
    customer_wechat_nickname: str | None = None
    customer_phone: str | None
    customer_address: str | None
    customer_needs: str | None
    customer_questions: str | None
    customer_objections: str | None
    product_interest: str | None
    budget: str | None
    purchase_time: str | None
    intent_level: str
    intent_score: int
    intent_reason: str | None
    evidence: str | None
    next_action: str | None
    sales_script: str | None
    model_name: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
