from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class AIAnalysisResult(Base):
    __tablename__ = "ai_analysis_results"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    tenant_id: Mapped[int] = mapped_column(Integer, default=1, index=True)
    upload_record_id: Mapped[int] = mapped_column(ForeignKey("upload_records.id"), unique=True, index=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"), nullable=True, index=True)
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    customer_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    customer_wechat_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    customer_wechat_nickname: Mapped[str | None] = mapped_column(String(120), nullable=True)
    customer_phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    customer_address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    customer_needs: Mapped[str | None] = mapped_column(Text, nullable=True)
    customer_questions: Mapped[str | None] = mapped_column(Text, nullable=True)
    customer_objections: Mapped[str | None] = mapped_column(Text, nullable=True)
    product_interest: Mapped[str | None] = mapped_column(Text, nullable=True)
    budget: Mapped[str | None] = mapped_column(String(120), nullable=True)
    purchase_time: Mapped[str | None] = mapped_column(String(120), nullable=True)
    intent_level: Mapped[str] = mapped_column(String(20), default="无法判断", index=True)
    intent_score: Mapped[int] = mapped_column(Integer, default=0, index=True)
    intent_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    sales_script: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    upload_record = relationship("UploadRecord", back_populates="analysis")
    customer = relationship("Customer", back_populates="analyses")
