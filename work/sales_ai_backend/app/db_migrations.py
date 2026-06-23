from sqlalchemy import inspect, text

from app.core.database import engine


def run_lightweight_migrations() -> None:
    """Small SQLite-friendly migrations for the local MVP.

    This keeps the current demo database usable without introducing Alembic yet.
    """
    inspector = inspect(engine)
    migrations = []
    tables = set(inspector.get_table_names())
    if "followups" in tables:
        columns = {column["name"] for column in inspector.get_columns("followups")}
        if "source" not in columns:
            migrations.append("ALTER TABLE followups ADD COLUMN source VARCHAR(20) DEFAULT 'manual'")
        if "call_recording_id" not in columns:
            migrations.append("ALTER TABLE followups ADD COLUMN call_recording_id INTEGER")
        if "upload_record_id" not in columns:
            migrations.append("ALTER TABLE followups ADD COLUMN upload_record_id INTEGER")

    if "call_recordings" in tables:
        columns = {column["name"] for column in inspector.get_columns("call_recordings")}
        if "transcript" not in columns:
            migrations.append("ALTER TABLE call_recordings ADD COLUMN transcript TEXT")
        if "transcription_status" not in columns:
            migrations.append("ALTER TABLE call_recordings ADD COLUMN transcription_status VARCHAR(20) DEFAULT 'pending'")
        if "transcription_error" not in columns:
            migrations.append("ALTER TABLE call_recordings ADD COLUMN transcription_error TEXT")

    if not migrations:
        return

    with engine.begin() as connection:
        for statement in migrations:
            connection.execute(text(statement))
