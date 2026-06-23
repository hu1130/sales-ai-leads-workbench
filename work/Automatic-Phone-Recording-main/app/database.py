from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from app.config import settings


SCHEMA = """
CREATE TABLE IF NOT EXISTS call_records (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  salesperson_id TEXT NOT NULL,
  phone_number TEXT,
  call_time TEXT,
  source_file TEXT NOT NULL UNIQUE,
  local_file TEXT,
  wav_file TEXT,
  transcript TEXT,
  summary TEXT,
  sales_ai_upload_id INTEGER,
  sales_ai_recording_id INTEGER,
  sales_ai_uploaded_at TEXT,
  upload_status TEXT NOT NULL DEFAULT 'pending',
  upload_error TEXT,
  transcript_synced_at TEXT,
  transcript_sync_error TEXT,
  status TEXT NOT NULL,
  error_message TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_call_records_status
ON call_records(status);

CREATE INDEX IF NOT EXISTS idx_call_records_call_time
ON call_records(call_time);

CREATE TABLE IF NOT EXISTS material_uploads (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source_file TEXT NOT NULL UNIQUE,
  local_file TEXT NOT NULL,
  sales_ai_upload_id INTEGER,
  upload_status TEXT NOT NULL DEFAULT 'pending',
  upload_error TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_material_uploads_status
ON material_uploads(upload_status);
"""


@dataclass(frozen=True)
class CallRecord:
    id: int
    salesperson_id: str
    phone_number: str | None
    call_time: str | None
    source_file: str
    local_file: str | None
    wav_file: str | None
    transcript: str | None
    summary: str | None
    sales_ai_upload_id: int | None
    sales_ai_recording_id: int | None
    sales_ai_uploaded_at: str | None
    upload_status: str
    upload_error: str | None
    transcript_synced_at: str | None
    transcript_sync_error: str | None
    status: str
    error_message: str | None


@dataclass(frozen=True)
class MaterialUpload:
    id: int
    source_file: str
    local_file: str
    sales_ai_upload_id: int | None
    upload_status: str
    upload_error: str | None


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(settings.db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)
        _ensure_column(conn, "call_records", "sales_ai_upload_id", "INTEGER")
        _ensure_column(conn, "call_records", "sales_ai_recording_id", "INTEGER")
        _ensure_column(conn, "call_records", "sales_ai_uploaded_at", "TEXT")
        _ensure_column(conn, "call_records", "upload_status", "TEXT NOT NULL DEFAULT 'pending'")
        _ensure_column(conn, "call_records", "upload_error", "TEXT")
        _ensure_column(conn, "call_records", "transcript_synced_at", "TEXT")
        _ensure_column(conn, "call_records", "transcript_sync_error", "TEXT")
        conn.execute(
            """
            UPDATE call_records
            SET upload_status = 'uploaded'
            WHERE sales_ai_uploaded_at IS NOT NULL
            """
        )
        conn.execute(
            """
            UPDATE call_records
            SET status = CASE
              WHEN transcript IS NOT NULL AND summary IS NOT NULL THEN 'summarized'
              WHEN transcript IS NOT NULL THEN 'transcribed'
              WHEN wav_file IS NOT NULL THEN 'converted'
              ELSE 'pulled'
            END
            WHERE status = 'uploaded'
            """
        )


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, column_type: str) -> None:
    columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}")


def upsert_pulled_record(
    *,
    source_file: str,
    local_file: Path,
    salesperson_id: str,
    call_time: str | None = None,
    phone_number: str | None = None,
) -> None:
    now = utc_now()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO call_records (
              salesperson_id, phone_number, call_time, source_file, local_file,
              status, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, 'pulled', ?, ?)
            ON CONFLICT(source_file) DO UPDATE SET
              local_file = excluded.local_file,
              phone_number = COALESCE(excluded.phone_number, call_records.phone_number),
              call_time = COALESCE(excluded.call_time, call_records.call_time),
              updated_at = excluded.updated_at
            """,
            (
                salesperson_id,
                phone_number,
                call_time,
                source_file,
                str(local_file),
                now,
                now,
            ),
        )


def mark_wav(source_file: str, wav_file: Path) -> None:
    with connect() as conn:
        conn.execute(
            """
            UPDATE call_records
            SET wav_file = ?, status = 'converted', updated_at = ?
            WHERE source_file = ?
            """,
            (str(wav_file), utc_now(), source_file),
        )


def mark_transcript(source_file: str, transcript: str) -> None:
    with connect() as conn:
        conn.execute(
            """
            UPDATE call_records
            SET transcript = ?, status = 'transcribed', updated_at = ?
            WHERE source_file = ?
            """,
            (transcript, utc_now(), source_file),
        )


def mark_summary(source_file: str, summary: str) -> None:
    with connect() as conn:
        conn.execute(
            """
            UPDATE call_records
            SET summary = ?, status = 'summarized', updated_at = ?
            WHERE source_file = ?
            """,
            (summary, utc_now(), source_file),
        )


def mark_sales_ai_uploaded(source_file: str, upload_record_id: int, recording_id: int | None) -> None:
    with connect() as conn:
        conn.execute(
            """
            UPDATE call_records
            SET sales_ai_upload_id = ?,
                sales_ai_recording_id = ?,
                sales_ai_uploaded_at = ?,
                upload_status = 'uploaded',
                upload_error = NULL,
                updated_at = ?
            WHERE source_file = ?
            """,
            (upload_record_id, recording_id, utc_now(), utc_now(), source_file),
        )


def mark_sales_ai_upload_error(source_file: str, error_message: str) -> None:
    with connect() as conn:
        conn.execute(
            """
            UPDATE call_records
            SET upload_status = 'failed', upload_error = ?, updated_at = ?
            WHERE source_file = ?
            """,
            (error_message[:2000], utc_now(), source_file),
        )


def mark_transcript_synced(source_file: str) -> None:
    with connect() as conn:
        conn.execute(
            """
            UPDATE call_records
            SET transcript_synced_at = ?, transcript_sync_error = NULL, updated_at = ?
            WHERE source_file = ?
            """,
            (utc_now(), utc_now(), source_file),
        )


def mark_transcript_sync_error(source_file: str, error_message: str) -> None:
    with connect() as conn:
        conn.execute(
            """
            UPDATE call_records
            SET transcript_sync_error = ?, updated_at = ?
            WHERE source_file = ?
            """,
            (error_message[:2000], utc_now(), source_file),
        )


def mark_done(source_file: str) -> None:
    with connect() as conn:
        conn.execute(
            """
            UPDATE call_records
            SET status = 'done', error_message = NULL, updated_at = ?
            WHERE source_file = ?
            """,
            (utc_now(), source_file),
        )


def mark_error(source_file: str, error_message: str) -> None:
    with connect() as conn:
        conn.execute(
            """
            UPDATE call_records
            SET status = 'error', error_message = ?, updated_at = ?
            WHERE source_file = ?
            """,
            (error_message[:2000], utc_now(), source_file),
        )


def register_material(source_file: str, local_file: Path) -> None:
    now = utc_now()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO material_uploads (
              source_file, local_file, upload_status, created_at, updated_at
            )
            VALUES (?, ?, 'pending', ?, ?)
            ON CONFLICT(source_file) DO UPDATE SET
              local_file = excluded.local_file,
              updated_at = excluded.updated_at
            """,
            (source_file, str(local_file), now, now),
        )


def iter_materials_to_upload() -> Iterable[MaterialUpload]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM material_uploads
            WHERE upload_status IN ('pending', 'failed')
            ORDER BY created_at ASC
            """
        ).fetchall()
    for row in rows:
        yield MaterialUpload(
            id=row["id"],
            source_file=row["source_file"],
            local_file=row["local_file"],
            sales_ai_upload_id=row["sales_ai_upload_id"],
            upload_status=row["upload_status"],
            upload_error=row["upload_error"],
        )


def mark_material_uploaded(source_file: str, upload_record_id: int) -> None:
    with connect() as conn:
        conn.execute(
            """
            UPDATE material_uploads
            SET sales_ai_upload_id = ?, upload_status = 'uploaded',
                upload_error = NULL, updated_at = ?
            WHERE source_file = ?
            """,
            (upload_record_id, utc_now(), source_file),
        )


def mark_material_upload_error(source_file: str, error_message: str) -> None:
    with connect() as conn:
        conn.execute(
            """
            UPDATE material_uploads
            SET upload_status = 'failed', upload_error = ?, updated_at = ?
            WHERE source_file = ?
            """,
            (error_message[:2000], utc_now(), source_file),
        )


def iter_records_to_process() -> Iterable[CallRecord]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM call_records
            WHERE (? = 1 AND wav_file IS NULL)
               OR (? = 1 AND transcript IS NULL)
               OR (? = 1 AND transcript IS NOT NULL AND summary IS NULL)
               OR (? = 1 AND upload_status IN ('pending', 'failed'))
               OR (
                    transcript IS NOT NULL
                    AND transcript_synced_at IS NULL
                    AND sales_ai_recording_id IS NOT NULL
                  )
            ORDER BY created_at ASC
            """,
            (
                int(settings.enable_wav_convert),
                int(settings.enable_transcribe),
                int(settings.enable_summary),
                int(settings.enable_sales_ai_upload),
            ),
        ).fetchall()

    for row in rows:
        yield CallRecord(
            id=row["id"],
            salesperson_id=row["salesperson_id"],
            phone_number=row["phone_number"],
            call_time=row["call_time"],
            source_file=row["source_file"],
            local_file=row["local_file"],
            wav_file=row["wav_file"],
            transcript=row["transcript"],
            summary=row["summary"],
            sales_ai_upload_id=row["sales_ai_upload_id"],
            sales_ai_recording_id=row["sales_ai_recording_id"],
            sales_ai_uploaded_at=row["sales_ai_uploaded_at"],
            upload_status=row["upload_status"],
            upload_error=row["upload_error"],
            transcript_synced_at=row["transcript_synced_at"],
            transcript_sync_error=row["transcript_sync_error"],
            status=row["status"],
            error_message=row["error_message"],
        )
