from __future__ import annotations

import logging
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from app.pipeline import run_once, setup_logging


TIMEZONE = ZoneInfo("Asia/Shanghai")
RUN_HOUR = 23
RUN_MINUTE = 30


def main() -> None:
    setup_logging()
    last_run_date: str | None = None
    logging.info("Scheduler started. Nightly sync runs at 23:30 Asia/Shanghai.")

    while True:
        now = datetime.now(TIMEZONE)
        today = now.date().isoformat()
        if now.hour == RUN_HOUR and now.minute == RUN_MINUTE and last_run_date != today:
            run_once()
            last_run_date = today
        time.sleep(20)


if __name__ == "__main__":
    main()
