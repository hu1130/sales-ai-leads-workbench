from __future__ import annotations

import logging
import os
import time
from pathlib import Path

from app.config import settings
from app.pipeline import run_once, setup_logging


def _poll_seconds() -> int:
    try:
        return max(5, int(os.getenv("PIPELINE_POLL_SECONDS", "15")))
    except ValueError:
        return 15


def main() -> None:
    setup_logging()
    pid_file = settings.logs_dir / "watcher.pid"
    pid_file.write_text(str(os.getpid()), encoding="ascii")
    interval = _poll_seconds()
    logging.info("Realtime recording watcher started; poll interval=%ss", interval)

    try:
        while True:
            started = time.monotonic()
            try:
                run_once()
            except Exception:  # noqa: BLE001
                logging.exception("Realtime pipeline cycle failed")
            elapsed = time.monotonic() - started
            time.sleep(max(1, interval - elapsed))
    finally:
        try:
            if pid_file.read_text(encoding="ascii").strip() == str(os.getpid()):
                pid_file.unlink()
        except OSError:
            pass


if __name__ == "__main__":
    main()
