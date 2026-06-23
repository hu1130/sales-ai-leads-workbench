from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.config import settings


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
logger = logging.getLogger(__name__)


def iter_inbox_materials() -> list[Path]:
    if not settings.local_inbox_dir.exists():
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=settings.sync_lookback_days)
    files: list[Path] = []
    for path in settings.local_inbox_dir.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        stat = path.stat()
        if datetime.fromtimestamp(stat.st_mtime, timezone.utc) < cutoff:
            continue
        age_seconds = datetime.now(timezone.utc).timestamp() - stat.st_mtime
        if stat.st_size <= 0 or age_seconds < settings.inbox_stable_seconds:
            logger.info("Skipping image that is empty or still syncing: %s", path)
            continue
        files.append(path)
    return sorted(files, key=lambda item: item.stat().st_mtime)
