from __future__ import annotations

import importlib.util
import shutil
import sqlite3
import sys

from app.config import ensure_directories, settings


def _status(name: str, ok: bool, detail: str) -> None:
    marker = "OK" if ok else "MISSING"
    print(f"[{marker}] {name}: {detail}")


def _has_module(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def main() -> None:
    ensure_directories()

    py_version = ".".join(str(part) for part in sys.version_info[:3])
    _status("Python", sys.version_info >= (3, 10), py_version)

    try:
        sqlite3.connect(settings.db_path).close()
        _status("SQLite", True, str(settings.db_path))
    except Exception as exc:  # noqa: BLE001
        _status("SQLite", False, str(exc))

    ffmpeg_path = shutil.which(settings.ffmpeg_path) or settings.ffmpeg_path
    _status("FFmpeg", shutil.which(settings.ffmpeg_path) is not None, ffmpeg_path)

    _status("funasr", _has_module("funasr"), "optional; required when ENABLE_TRANSCRIBE=1")

    adb_path = shutil.which(settings.adb_path)
    _status("ADB", adb_path is not None, adb_path or "optional when SYNC_MODE=local")

    _status("SYNC_MODE", settings.sync_mode in {"local", "adb"}, settings.sync_mode)
    _status("LOCAL_INBOX_DIR", settings.local_inbox_dir.exists(), str(settings.local_inbox_dir))
    _status("recordings_dir", settings.recordings_dir.exists(), str(settings.recordings_dir))
    _status("wav_dir", settings.wav_dir.exists(), str(settings.wav_dir))
    _status("db_path", settings.db_path.parent.exists(), str(settings.db_path))


if __name__ == "__main__":
    main()
