import hashlib
from pathlib import Path

from sqlalchemy import inspect, text

from app.core.config import get_settings
from app.core.database import engine

DEFAULT_TENANT_NAME = "深度觉醒（上海）人工智能科技有限公司"
LEGACY_DEFAULT_TENANT_NAMES = ("默认公司", "é»˜è®¤å…¬å�¸", "榛樿鍏徃")


def run_lightweight_migrations() -> None:
    """Small SQLite-friendly migrations for the local MVP.

    This keeps the current demo database usable without introducing Alembic yet.
    """
    inspector = inspect(engine)
    migrations = []
    tables = set(inspector.get_table_names())

    tenant_tables = (
        "users",
        "customers",
        "upload_records",
        "ai_analysis_results",
        "followups",
        "quotations",
        "scripts",
        "call_campaigns",
        "call_campaign_targets",
        "call_attempts",
        "ai_robot_calls",
        "ai_robot_call_events",
        "sales_callbacks",
        "sales_callback_events",
        "call_recordings",
        "call_provider_configs",
    )
    for table_name in tenant_tables:
        if table_name in tables:
            columns = {column["name"] for column in inspector.get_columns(table_name)}
            if "tenant_id" not in columns:
                migrations.append(f"ALTER TABLE {table_name} ADD COLUMN tenant_id INTEGER DEFAULT 1")

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

    if "upload_records" in tables:
        columns = {column["name"] for column in inspector.get_columns("upload_records")}
        if "file_sha256" not in columns:
            migrations.append("ALTER TABLE upload_records ADD COLUMN file_sha256 VARCHAR(64)")
        if "file_size" not in columns:
            migrations.append("ALTER TABLE upload_records ADD COLUMN file_size INTEGER")

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

    if migrations:
        with engine.begin() as connection:
            for statement in migrations:
                connection.execute(text(statement))
            _ensure_default_tenant(connection)
            for table_name in tenant_tables:
                if table_name in tables:
                    connection.execute(text(f"UPDATE {table_name} SET tenant_id = 1 WHERE tenant_id IS NULL"))
            if "customers" in tables:
                connection.execute(text("UPDATE customers SET lead_status = 'assigned' WHERE lead_status IS NULL"))
                connection.execute(text("UPDATE customers SET lead_source = source WHERE lead_source IS NULL AND source IS NOT NULL"))
            # Migrate old done flag to new status field
            if "followups" in tables:
                cols = {c["name"] for c in inspector.get_columns("followups")}
                if "done" in cols and "status" in cols:
                    connection.execute(text("UPDATE followups SET status = 'completed' WHERE done = 1"))
    else:
        with engine.begin() as connection:
            _ensure_default_tenant(connection)

    inspector = inspect(engine)
    current_tables = set(inspector.get_table_names())
    if "upload_records" in current_tables:
        columns = {column["name"] for column in inspector.get_columns("upload_records")}
        indexes = {index["name"] for index in inspector.get_indexes("upload_records")}
        with engine.begin() as connection:
            if "file_sha256" in columns and "ix_upload_records_file_sha256" not in indexes:
                connection.execute(text("CREATE INDEX ix_upload_records_file_sha256 ON upload_records(file_sha256)"))
            for table_name in tenant_tables:
                if table_name in current_tables:
                    columns = {column["name"] for column in inspector.get_columns(table_name)}
                    indexes = {index["name"] for index in inspector.get_indexes(table_name)}
                    index_name = f"ix_{table_name}_tenant_id"
                    if "tenant_id" in columns and index_name not in indexes:
                        connection.execute(text(f"CREATE INDEX {index_name} ON {table_name}(tenant_id)"))

    _backfill_upload_file_hashes()


def _ensure_default_tenant(connection) -> None:
    existing = connection.execute(text("SELECT id, name FROM tenants WHERE id = 1")).fetchone()
    if existing is None:
        connection.execute(
            text("INSERT INTO tenants (id, name, status) VALUES (1, :name, 'active')"),
            {"name": DEFAULT_TENANT_NAME},
        )
        return
    if existing.name in LEGACY_DEFAULT_TENANT_NAMES:
        connection.execute(
            text("UPDATE tenants SET name = :name, status = 'active' WHERE id = 1"),
            {"name": DEFAULT_TENANT_NAME},
        )


def _backfill_upload_file_hashes() -> None:
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    if "upload_records" not in tables:
        return
    columns = {column["name"] for column in inspector.get_columns("upload_records")}
    if "file_sha256" not in columns or "file_size" not in columns:
        return

    backend_root = Path(__file__).resolve().parents[1]
    upload_root = get_settings().upload_path
    if not upload_root.is_absolute():
        upload_root = backend_root / upload_root
    upload_root = upload_root.resolve(strict=False)

    with engine.begin() as connection:
        rows = connection.execute(
            text("SELECT id, file_path FROM upload_records WHERE file_sha256 IS NULL OR file_size IS NULL")
        ).fetchall()
        for row in rows:
            file_path = _resolve_upload_path(str(row.file_path), upload_root)
            if not file_path.is_file():
                continue
            file_sha256, file_size = _hash_file(file_path)
            connection.execute(
                text("UPDATE upload_records SET file_sha256 = :file_sha256, file_size = :file_size WHERE id = :id"),
                {"file_sha256": file_sha256, "file_size": file_size, "id": row.id},
            )


def _resolve_upload_path(stored_path: str, upload_root: Path) -> Path:
    path = Path(stored_path)
    if path.is_absolute():
        return path.resolve(strict=False)
    if path.parts and path.parts[0] == upload_root.name:
        return (upload_root.parent / path).resolve(strict=False)
    return (upload_root / path).resolve(strict=False)


def _hash_file(file_path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    total = 0
    with file_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            total += len(chunk)
            digest.update(chunk)
    return digest.hexdigest(), total
