from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


PHONE_RE = re.compile(r"(?<!\d)(?:\+?86[-_ ]?)?(1[3-9](?:[-_ ]?\d){9})(?!\d)")
DATETIME_PATTERNS = [
    re.compile(
        r"(?P<year>20\d{2})[-_\.年]?(?P<month>\d{2})[-_\.月]?(?P<day>\d{2})"
        r"(?:[ T_\-日]?(?P<hour>\d{2})[-_\.时:]?(?P<minute>\d{2})[-_\.分:]?(?P<second>\d{2})?)?"
    ),
    re.compile(
        r"(?P<year>20\d{2})[-_\.](?P<month>\d{1,2})[-_\.](?P<day>\d{1,2})"
        r"(?:[ T_\-](?P<hour>\d{1,2})[-_\.时:]?(?P<minute>\d{1,2})[-_\.分:]?(?P<second>\d{1,2})?)?"
    ),
]


@dataclass(frozen=True)
class RecordingMetadata:
    phone_number: str | None = None
    call_time: str | None = None


def parse_recording_metadata(path_or_name: str | Path) -> RecordingMetadata:
    text = str(path_or_name)
    name = Path(text).stem
    phone_number = _parse_phone_number(name)
    call_time = _parse_call_time(name)
    return RecordingMetadata(phone_number=phone_number, call_time=call_time)


def metadata_from_file(path: Path) -> RecordingMetadata:
    parsed = parse_recording_metadata(path.name)
    if parsed.call_time:
        return parsed

    try:
        mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()
    except OSError:
        mtime = None
    return RecordingMetadata(phone_number=parsed.phone_number, call_time=mtime)


def _parse_phone_number(text: str) -> str | None:
    match = PHONE_RE.search(text)
    if not match:
        return None
    return re.sub(r"\D", "", match.group(1))


def _parse_call_time(text: str) -> str | None:
    for pattern in DATETIME_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        parts = match.groupdict()
        try:
            dt = datetime(
                year=int(parts["year"]),
                month=int(parts["month"]),
                day=int(parts["day"]),
                hour=int(parts.get("hour") or 0),
                minute=int(parts.get("minute") or 0),
                second=int(parts.get("second") or 0),
            )
        except ValueError:
            continue
        return dt.isoformat()
    return None
