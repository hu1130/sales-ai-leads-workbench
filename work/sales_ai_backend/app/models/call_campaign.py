from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class CallCampaign(Base):
    __tablename__ = "call_campaigns"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    tenant_id: Mapped[int] = mapped_column(Integer, default=1, index=True)
    name: Mapped[str] = mapped_column(String(160), index=True)
    scenario: Mapped[str] = mapped_column(String(40), default="lead_filter", index=True)
    script_id: Mapped[int | None] = mapped_column(ForeignKey("scripts.id"), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    total_count: Mapped[int] = mapped_column(Integer, default=0)
    called_count: Mapped[int] = mapped_column(Integer, default=0)
    connected_count: Mapped[int] = mapped_column(Integer, default=0)
    high_intent_count: Mapped[int] = mapped_column(Integer, default=0)
    planned_start_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    planned_end_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    targets = relationship("CallCampaignTarget", back_populates="campaign", cascade="all, delete-orphan")
