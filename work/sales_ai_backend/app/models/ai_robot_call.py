from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class AiRobotCall(Base):
    __tablename__ = "ai_robot_calls"
    __table_args__ = (UniqueConstraint("provider", "provider_call_id", name="uq_ai_robot_provider_call"),)

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    tenant_id: Mapped[int] = mapped_column(Integer, default=1, index=True)
    campaign_id: Mapped[int | None] = mapped_column(ForeignKey("call_campaigns.id"), nullable=True, index=True)
    target_id: Mapped[int | None] = mapped_column(ForeignKey("call_campaign_targets.id"), nullable=True, index=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"), nullable=True, index=True)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    call_attempt_id: Mapped[int | None] = mapped_column(ForeignKey("call_attempts.id"), nullable=True, index=True)
    provider: Mapped[str] = mapped_column(String(40), default="mock", index=True)
    provider_call_id: Mapped[str] = mapped_column(String(120), index=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    script_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="initiated", index=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    recording_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    transcript: Mapped[str | None] = mapped_column(Text, nullable=True)
    intent_level: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    intent_score: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    high_intent: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    raw_payload_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    campaign = relationship("CallCampaign")
    target = relationship("CallCampaignTarget")
    customer = relationship("Customer")
    owner = relationship("User")
    call_attempt = relationship("CallAttempt")


class AiRobotCallEvent(Base):
    __tablename__ = "ai_robot_call_events"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    robot_call_id: Mapped[int | None] = mapped_column(ForeignKey("ai_robot_calls.id"), nullable=True, index=True)
    provider: Mapped[str] = mapped_column(String(40), index=True)
    provider_call_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(40), index=True)
    payload_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    robot_call = relationship("AiRobotCall")


class AiRobotCallStopRequest(Base):
    __tablename__ = "ai_robot_call_stop_requests"
    __table_args__ = (
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_ai_robot_stop_tenant_idempotency"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    tenant_id: Mapped[int] = mapped_column(Integer, index=True)
    robot_call_id: Mapped[int] = mapped_column(ForeignKey("ai_robot_calls.id"), index=True)
    call_task_id: Mapped[str] = mapped_column(String(128), index=True)
    provider_task_ref: Mapped[str] = mapped_column(String(128))
    provider_call_id: Mapped[str] = mapped_column(String(120))
    reason_code: Mapped[str] = mapped_column(String(40))
    requested_at: Mapped[datetime] = mapped_column(DateTime)
    trace_id: Mapped[str] = mapped_column(String(128), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(200))
    payload_hash: Mapped[str] = mapped_column(String(64))
    receipt_id: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    provider: Mapped[str] = mapped_column(String(40))
    accepted: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(32), default="UNKNOWN")
    raw_status: Mapped[str | None] = mapped_column(String(160), nullable=True)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    http_status: Mapped[int] = mapped_column(Integer, default=202)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    robot_call = relationship("AiRobotCall")
