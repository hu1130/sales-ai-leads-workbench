from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from app.config import settings
from app.recording_metadata import RecordingMetadata, parse_recording_metadata


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RemoteRecording:
    source_file: str
    filename: str
    modified_at: str | None = None
    metadata: RecordingMetadata = RecordingMetadata()


def _run_adb(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [settings.adb_path, *args],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def ensure_device_connected() -> None:
    result = _run_adb(["devices"])
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    devices = [line for line in lines[1:] if line.endswith("\tdevice")]
    if not devices:
        raise RuntimeError("No authorized Android device found. Check USB debugging and run `adb devices`.")


def list_recordings() -> list[RemoteRecording]:
    recordings: list[RemoteRecording] = []
    cutoff = datetime.now() - timedelta(days=settings.sync_lookback_days)
    cutoff_text = cutoff.strftime("%Y-%m-%d")

    for remote_dir in settings.phone_recording_dirs:
        command = f"find {remote_dir} -type f -newermt {cutoff_text} 2>/dev/null"
        try:
            result = _run_adb(["shell", command])
        except subprocess.CalledProcessError as exc:
            logger.warning("Could not scan phone directory %s: %s", remote_dir, exc.stderr.strip())
            continue

        for line in result.stdout.splitlines():
            source_file = line.strip()
            if not source_file:
                continue
            recordings.append(
                RemoteRecording(
                    source_file=source_file,
                    filename=Path(source_file).name,
                    metadata=parse_recording_metadata(Path(source_file).name),
                )
            )

    unique = {item.source_file: item for item in recordings}
    return sorted(unique.values(), key=lambda item: item.source_file)


def pull_recording(recording: RemoteRecording) -> Path:
    safe_name = recording.source_file.strip("/").replace("/", "__").replace(":", "_")
    local_path = settings.recordings_dir / safe_name
    if local_path.exists() and local_path.stat().st_size > 0:
        return local_path

    local_path.parent.mkdir(parents=True, exist_ok=True)
    _run_adb(["pull", recording.source_file, str(local_path)])
    return local_path


def pull_new_recordings() -> list[tuple[RemoteRecording, Path]]:
    ensure_device_connected()
    pulled: list[tuple[RemoteRecording, Path]] = []
    for recording in list_recordings():
        local_path = pull_recording(recording)
        pulled.append((recording, local_path))
    return pulled
