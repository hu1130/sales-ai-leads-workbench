from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    tenant_id: Mapped[int] = mapped_column(Integer, default=1, index=True)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    name: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    wechat_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    wechat_nickname: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source: Mapped[str | None] = mapped_column(String(80), nullable=True)
    lead_source: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    lead_status: Mapped[str] = mapped_column(String(20), default="assigned", index=True)
    pipeline_stage: Mapped[str] = mapped_column(String(20), default="lead", index=True)
    intent_level: Mapped[str] = mapped_column(String(20), default="无法判断", index=True)
    intent_score: Mapped[int] = mapped_column(Integer, default=0, index=True)
    demand_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    concerns: Mapped[str | None] = mapped_column(Text, nullable=True)
    product_interest: Mapped[str | None] = mapped_column(Text, nullable=True)
    budget: Mapped[str | None] = mapped_column(String(120), nullable=True)
    purchase_time: Mapped[str | None] = mapped_column(String(120), nullable=True)
    next_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_followup_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    owner = relationship("User", back_populates="customers")
    uploads = relationship("UploadRecord", back_populates="customer")
    analyses = relationship("AIAnalysisResult", back_populates="customer")
    followups = relationship("Followup", back_populates="customer")

    @property
    def owner_name(self) -> str | None:
        return self.owner.name if self.owner else None

    @property
    def owner_username(self) -> str | None:
        return self.owner.username if self.owner else None
