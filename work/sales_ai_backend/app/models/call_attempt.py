from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class CallAttempt(Base):
    __tablename__ = "call_attempts"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    tenant_id: Mapped[int] = mapped_column(Integer, default=1, index=True)
    campaign_id: Mapped[int | None] = mapped_column(ForeignKey("call_campaigns.id"), nullable=True, index=True)
    target_id: Mapped[int | None] = mapped_column(ForeignKey("call_campaign_targets.id"), nullable=True, index=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"), nullable=True, index=True)
    sales_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    call_mode: Mapped[str] = mapped_column(String(20), default="manual")
    call_status: Mapped[str] = mapped_column(String(24), default="dialing", index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    call_recording_id: Mapped[int | None] = mapped_column(ForeignKey("call_recordings.id"), nullable=True, index=True)
    upload_record_id: Mapped[int | None] = mapped_column(ForeignKey("upload_records.id"), nullable=True, index=True)
    transcript: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_analysis_id: Mapped[int | None] = mapped_column(ForeignKey("ai_analysis_results.id"), nullable=True, index=True)
    intent_level: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    intent_score: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    next_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    campaign = relationship("CallCampaign")
    target = relationship("CallCampaignTarget")
    customer = relationship("Customer")
    sales = relationship("User")
    analysis = relationship("AIAnalysisResult")
