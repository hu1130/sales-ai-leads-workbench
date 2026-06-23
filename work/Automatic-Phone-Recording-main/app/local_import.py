from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.config import settings
from app.recording_metadata import RecordingMetadata, metadata_from_file


AUDIO_EXTENSIONS = {".m4a", ".amr", ".mp3", ".wav", ".aac", ".3gp", ".ogg", ".flac"}
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LocalRecording:
    source_file: str
    local_file: Path
    metadata: RecordingMetadata


def _safe_relative_name(path: Path) -> str:
    try:
        relative = path.relative_to(settings.local_inbox_dir)
    except ValueError:
        relative = path.name
    return str(relative).replace("\\", "__").replace("/", "__").replace(":", "_")


def _is_stable_file(path: Path) -> bool:
    try:
        stat = path.stat()
    except OSError:
        return False
    if stat.st_size <= 0:
        return False
    age_seconds = datetime.now(timezone.utc).timestamp() - stat.st_mtime
    return age_seconds >= settings.inbox_stable_seconds


def iter_inbox_recordings() -> list[Path]:
    if not settings.local_inbox_dir.exists():
        settings.local_inbox_dir.mkdir(parents=True, exist_ok=True)
        return []

    files = []
    cutoff = datetime.now(timezone.utc) - timedelta(days=settings.sync_lookback_days)
    for path in settings.local_inbox_dir.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in AUDIO_EXTENSIONS:
            continue
        if datetime.fromtimestamp(path.stat().st_mtime, timezone.utc) < cutoff:
            logger.debug("Skipping inbox file older than %s days: %s", settings.sync_lookback_days, path)
            continue
        if not _is_stable_file(path):
            logger.info("Skipping inbox file that is empty or still syncing: %s", path)
            continue
        files.append(path)
    return sorted(files, key=lambda path: path.stat().st_mtime)


def import_recordings() -> list[LocalRecording]:
    imported: list[LocalRecording] = []
    for source_path in iter_inbox_recordings():
        safe_name = _safe_relative_name(source_path)
        target_path = settings.recordings_dir / safe_name
        target_path.parent.mkdir(parents=True, exist_ok=True)

        if not target_path.exists() or target_path.stat().st_size != source_path.stat().st_size:
            shutil.copy2(source_path, target_path)

        imported.append(
            LocalRecording(
                source_file=str(source_path),
                local_file=target_path,
                metadata=metadata_from_file(source_path),
            )
        )
    return imported
