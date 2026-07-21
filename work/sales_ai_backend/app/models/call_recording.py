from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class CallRecording(Base):
    __tablename__ = "call_recordings"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    tenant_id: Mapped[int] = mapped_column(Integer, default=1, index=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"), nullable=True, index=True)
    sales_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    caller_phone: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    callee_phone: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    recording_path: Mapped[str] = mapped_column(String(500))
    upload_record_id: Mapped[int | None] = mapped_column(ForeignKey("upload_records.id"), nullable=True, index=True)
    transcript: Mapped[str | None] = mapped_column(Text, nullable=True)
    transcription_status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    transcription_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
