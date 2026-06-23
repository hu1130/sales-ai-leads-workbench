from __future__ import annotations

import csv
from datetime import datetime

from app.config import ensure_directories, settings
from app.database import connect, init_db


FIELDS = [
    "id",
    "salesperson_id",
    "phone_number",
    "call_time",
    "status",
    "source_file",
    "local_file",
    "wav_file",
    "transcript",
    "summary",
    "error_message",
]


def export_csv() -> str:
    ensure_directories()
    init_db()
    output_file = settings.exports_dir / f"call_records_{datetime.now():%Y%m%d_%H%M%S}.csv"

    with connect() as conn, output_file.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        rows = conn.execute(
            """
            SELECT id, salesperson_id, phone_number, call_time, status, source_file,
                   local_file, wav_file, transcript, summary, error_message
            FROM call_records
            ORDER BY call_time DESC, id DESC
            """
        )
        for row in rows:
            writer.writerow({field: row[field] for field in FIELDS})

    return str(output_file)


def main() -> None:
    print(export_csv())


if __name__ == "__main__":
    main()
