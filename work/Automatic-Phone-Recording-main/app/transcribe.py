from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path


def transcribe_audio(wav_file: Path) -> str:
    runtime = os.getenv("FUNASR_RUNTIME", "auto").strip().lower()
    if runtime == "docker":
        return _transcribe_with_docker(wav_file)

    try:
        from funasr import AutoModel  # type: ignore
    except ImportError as exc:
        if runtime == "auto":
            return _transcribe_with_docker(wav_file)
        raise RuntimeError("FunASR could not be imported in the native Python environment.") from exc

    model = AutoModel(
        model="paraformer-zh",
        vad_model="fsmn-vad",
        punc_model="ct-punc",
    )
    result = model.generate(input=str(wav_file))
    if not result:
        return ""
    first = result[0]
    if isinstance(first, dict):
        return str(first.get("text", "")).strip()
    return str(first).strip()


def _transcribe_with_docker(wav_file: Path) -> str:
    image = os.getenv("FUNASR_DOCKER_IMAGE", "sales-ai-funasr:local")
    timeout = int(os.getenv("FUNASR_DOCKER_TIMEOUT", "1800"))
    audio = wav_file.resolve()

    with tempfile.TemporaryDirectory(prefix="funasr-") as output_dir:
        output_path = Path(output_dir) / "transcript.txt"
        command = [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{audio.parent}:/audio:ro",
            "-v",
            f"{output_dir}:/output",
            "-v",
            "sales_ai_funasr_cache:/root/.cache",
            image,
            f"/audio/{audio.name}",
            "/output/transcript.txt",
        ]
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        if completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip()
            raise RuntimeError(f"Docker FunASR transcription failed: {detail}")
        if not output_path.exists():
            raise RuntimeError("Docker FunASR did not create a transcript file.")
        return output_path.read_text(encoding="utf-8").strip()
