from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class SalesCallback(Base):
    __tablename__ = "sales_callbacks"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    tenant_id: Mapped[int] = mapped_column(Integer, default=1, index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    sales_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    call_attempt_id: Mapped[int | None] = mapped_column(ForeignKey("call_attempts.id"), nullable=True, index=True)
    provider: Mapped[str] = mapped_column(String(40), default="mock", index=True)
    provider_call_id: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    sales_phone: Mapped[str] = mapped_column(String(32), index=True)
    customer_phone: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(32), default="initiated", index=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    recording_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    bridged_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    customer = relationship("Customer")
    sales = relationship("User")
    call_attempt = relationship("CallAttempt")


class SalesCallbackEvent(Base):
    __tablename__ = "sales_callback_events"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    callback_id: Mapped[int | None] = mapped_column(ForeignKey("sales_callbacks.id"), nullable=True, index=True)
    provider: Mapped[str] = mapped_column(String(40), default="mock", index=True)
    provider_call_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(60), index=True)
    payload_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    callback = relationship("SalesCallback")
