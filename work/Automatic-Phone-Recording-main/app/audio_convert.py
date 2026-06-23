from __future__ import annotations

import subprocess
from pathlib import Path

from app.config import settings


def convert_to_wav(input_file: Path) -> Path:
    output_file = settings.wav_dir / f"{input_file.stem}.wav"
    if output_file.exists() and output_file.stat().st_size > 0:
        return output_file

    output_file.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            [
                settings.ffmpeg_path,
                "-y",
                "-i",
                str(input_file),
                "-ar",
                "16000",
                "-ac",
                "1",
                str(output_file),
            ],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            "FFmpeg was not found. Install FFmpeg or set FFMPEG_PATH to ffmpeg.exe."
        ) from exc
    except subprocess.CalledProcessError as exc:
        message = (exc.stderr or exc.stdout or "").strip()
        raise RuntimeError(f"FFmpeg failed to convert {input_file}: {message[:2000]}") from exc
    return output_file
