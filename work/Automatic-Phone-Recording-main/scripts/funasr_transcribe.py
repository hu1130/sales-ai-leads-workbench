from __future__ import annotations

import sys
import subprocess
import tempfile
from pathlib import Path

import imageio_ffmpeg
from funasr import AutoModel


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: funasr_transcribe.py INPUT_AUDIO OUTPUT_TEXT", file=sys.stderr)
        return 2

    input_audio = Path(sys.argv[1])
    output_text = Path(sys.argv[2])
    converted_audio: Path | None = None
    if input_audio.suffix.lower() != ".wav":
        converted_audio = Path(tempfile.gettempdir()) / "funasr-input.wav"
        subprocess.run(
            [
                imageio_ffmpeg.get_ffmpeg_exe(),
                "-y",
                "-i",
                str(input_audio),
                "-ar",
                "16000",
                "-ac",
                "1",
                str(converted_audio),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        input_audio = converted_audio

    model = AutoModel(model="paraformer-zh", vad_model="fsmn-vad", punc_model="ct-punc")
    result = model.generate(input=str(input_audio))

    transcript = ""
    if result:
        first = result[0]
        transcript = str(first.get("text", "") if isinstance(first, dict) else first).strip()

    output_text.write_text(transcript, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
