from sqlalchemy import inspect, text

from app.core.database import engine


def run_lightweight_migrations() -> None:
    """Small SQLite-friendly migrations for the local MVP.

    This keeps the current demo database usable without introducing Alembic yet.
    """
    inspector = inspect(engine)
    migrations = []
    tables = set(inspector.get_table_names())
    if "customers" in tables:
        columns = {column["name"] for column in inspector.get_columns("customers")}
        if "wechat_id" not in columns:
            migrations.append("ALTER TABLE customers ADD COLUMN wechat_id VARCHAR(80)")
        if "wechat_nickname" not in columns:
            migrations.append("ALTER TABLE customers ADD COLUMN wechat_nickname VARCHAR(120)")
        if "lead_source" not in columns:
            migrations.append("ALTER TABLE customers ADD COLUMN lead_source VARCHAR(80)")
        if "lead_status" not in columns:
            migrations.append("ALTER TABLE customers ADD COLUMN lead_status VARCHAR(20) DEFAULT 'assigned'")

    if "ai_analysis_results" in tables:
        columns = {column["name"] for column in inspector.get_columns("ai_analysis_results")}
        if "customer_wechat_id" not in columns:
            migrations.append("ALTER TABLE ai_analysis_results ADD COLUMN customer_wechat_id VARCHAR(80)")
        if "customer_wechat_nickname" not in columns:
            migrations.append("ALTER TABLE ai_analysis_results ADD COLUMN customer_wechat_nickname VARCHAR(120)")

    if "followups" in tables:
        columns = {column["name"] for column in inspector.get_columns("followups")}
        if "source" not in columns:
            migrations.append("ALTER TABLE followups ADD COLUMN source VARCHAR(20) DEFAULT 'manual'")
        if "call_recording_id" not in columns:
            migrations.append("ALTER TABLE followups ADD COLUMN call_recording_id INTEGER")
        if "upload_record_id" not in columns:
            migrations.append("ALTER TABLE followups ADD COLUMN upload_record_id INTEGER")
        if "done_at" not in columns:
            migrations.append("ALTER TABLE followups ADD COLUMN done_at DATETIME")
        if "status" not in columns:
            migrations.append("ALTER TABLE followups ADD COLUMN status VARCHAR(20) DEFAULT 'pending'")

    if "customers" in tables:
        columns = {column["name"] for column in inspector.get_columns("customers")}
        if "pipeline_stage" not in columns:
            migrations.append("ALTER TABLE customers ADD COLUMN pipeline_stage VARCHAR(20) DEFAULT 'lead'")

    if "customers" in tables:
        columns = {column["name"] for column in inspector.get_columns("customers")}
        if "assigned_at" not in columns:
            migrations.append("ALTER TABLE customers ADD COLUMN assigned_at DATETIME")

    if "scripts" not in tables:
        migrations.append("CREATE TABLE scripts (id INTEGER PRIMARY KEY AUTOINCREMENT, title VARCHAR(200) NOT NULL, category VARCHAR(50) DEFAULT 'general', content TEXT NOT NULL, created_at DATETIME DEFAULT CURRENT_TIMESTAMP, updated_at DATETIME DEFAULT CURRENT_TIMESTAMP)")

    if "quotations" not in tables:
        migrations.append("CREATE TABLE quotations (id INTEGER PRIMARY KEY AUTOINCREMENT, customer_id INTEGER NOT NULL, user_id INTEGER NOT NULL, title VARCHAR(200) DEFAULT '', items TEXT DEFAULT '[]', total_amount FLOAT DEFAULT 0, notes TEXT, status VARCHAR(20) DEFAULT 'draft', sent_at DATETIME, created_at DATETIME DEFAULT CURRENT_TIMESTAMP, updated_at DATETIME DEFAULT CURRENT_TIMESTAMP)")

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
        if "customers" in tables:
            connection.execute(text("UPDATE customers SET lead_status = 'assigned' WHERE lead_status IS NULL"))
            connection.execute(text("UPDATE customers SET lead_source = source WHERE lead_source IS NULL AND source IS NOT NULL"))
        # Migrate old done flag to new status field
        if "followups" in tables:
            cols = {c["name"] for c in inspector.get_columns("followups")}
            if "done" in cols and "status" in cols:
                connection.execute(text("UPDATE followups SET status = 'completed' WHERE done = 1"))
