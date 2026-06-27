from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
LOCAL_ADB = BASE_DIR / "tools" / "platform-tools" / "adb.exe"


def _load_dotenv() -> None:
    env_file = BASE_DIR / ".env"
    if not env_file.exists():
        return
    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv()


def _csv_env(name: str, default: list[str]) -> list[str]:
    raw = os.getenv(name)
    if not raw:
        return default
    return [item.strip() for item in raw.split(",") if item.strip()]


def _bool_env(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    sync_mode: str = os.getenv("SYNC_MODE", "local").strip().lower()
    salesperson_id: str = os.getenv("SALESPERSON_ID", "sales_001")
    phone_recording_dirs: list[str] = None  # type: ignore[assignment]
    sync_lookback_days: int = int(os.getenv("SYNC_LOOKBACK_DAYS", "2"))
    inbox_stable_seconds: int = int(os.getenv("INBOX_STABLE_SECONDS", "10"))

    adb_path: str = os.getenv("ADB_PATH", str(LOCAL_ADB if LOCAL_ADB.exists() else "adb"))
    ffmpeg_path: str = os.getenv("FFMPEG_PATH", "ffmpeg")

    data_dir: Path = BASE_DIR / "data"
    local_inbox_dir: Path = Path(os.getenv("LOCAL_INBOX_DIR", str(BASE_DIR / "data" / "inbox")))
    recordings_dir: Path = BASE_DIR / "data" / "recordings"
    wav_dir: Path = BASE_DIR / "data" / "wav"
    transcripts_dir: Path = BASE_DIR / "data" / "transcripts"
    exports_dir: Path = BASE_DIR / "data" / "exports"
    db_path: Path = BASE_DIR / "db" / "sales_audio.db"
    logs_dir: Path = BASE_DIR / "logs"

    enable_transcribe: bool = _bool_env("ENABLE_TRANSCRIBE", False)
    enable_summary: bool = _bool_env("ENABLE_SUMMARY", False)
    enable_sales_ai_upload: bool = _bool_env("ENABLE_SALES_AI_UPLOAD", False)
    enable_wav_convert: bool = _bool_env("ENABLE_WAV_CONVERT", True)

    ollama_url: str = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")
    sales_ai_base_url: str = os.getenv("SALES_AI_BASE_URL", "http://127.0.0.1:8100")
    sales_ai_username: str = os.getenv("SALES_AI_USERNAME", "admin")
    sales_ai_password: str = os.getenv("SALES_AI_PASSWORD", "admin123")
    sales_ai_sales_username: str | None = os.getenv("SALES_AI_SALES_USERNAME") or None

    def __post_init__(self) -> None:
        if self.phone_recording_dirs is None:
            object.__setattr__(
                self,
                "phone_recording_dirs",
                _csv_env(
                    "PHONE_RECORDING_DIRS",
                    [
                        "/sdcard/Recordings/Call",
                        "/sdcard/MIUI/sound_recorder/call_rec",
                        "/sdcard/Sounds/CallRecord",
                        "/sdcard/Sounds/Call Record",
                        "/sdcard/Recordings/Call Recordings",
                        "/sdcard/Recorder/call",
                        "/sdcard/CallRecord",
                        "/sdcard/Huawei/Recorder/Call",
                    ],
                ),
            )


settings = Settings()


def ensure_directories() -> None:
    for path in [
        settings.recordings_dir,
        settings.local_inbox_dir,
        settings.wav_dir,
        settings.transcripts_dir,
        settings.exports_dir,
        settings.db_path.parent,
        settings.logs_dir,
    ]:
        path.mkdir(parents=True, exist_ok=True)
