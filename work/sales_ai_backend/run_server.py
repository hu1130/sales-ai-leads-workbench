from __future__ import annotations

import traceback
from pathlib import Path

import uvicorn


LOG_PATH = Path(__file__).with_name("backend.err.log")


def main() -> None:
    try:
        uvicorn.run(
            "app.main:app",
            host="127.0.0.1",
            port=8100,
            log_level="warning",
            log_config=None,
            access_log=False,
        )
    except Exception:
        LOG_PATH.write_text(traceback.format_exc(), encoding="utf-8")
        raise


if __name__ == "__main__":
    main()
