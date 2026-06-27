from __future__ import annotations

from pathlib import Path
from typing import Any
import json
import mimetypes
from urllib import request
from urllib.error import HTTPError
from uuid import uuid4

from app.config import settings
from app.database import CallRecord, MaterialUpload


def upload_recording_to_sales_ai(record: CallRecord) -> dict[str, Any]:
    if not record.local_file:
        raise RuntimeError("Missing local recording path")

    audio_path = Path(record.local_file)
    if not audio_path.exists():
        raise RuntimeError(f"Recording file does not exist: {audio_path}")

    token = _login()
    url = f"{settings.sales_ai_base_url.rstrip('/')}/api/call-recordings"
    data: dict[str, str] = {}
    if record.phone_number:
        data["callee_phone"] = record.phone_number
    if record.call_time:
        data["started_at"] = record.call_time
    if settings.sales_ai_sales_username:
        data["sales_username"] = settings.sales_ai_sales_username

    return _post_multipart(
        url,
        token=token,
        data=data,
        file_field="file",
        file_path=audio_path,
        timeout=120,
    )


def submit_transcript_to_sales_ai(recording_id: int, transcript: str) -> dict[str, Any]:
    token = _login()
    payload = json.dumps({"transcript": transcript}, ensure_ascii=False).encode("utf-8")
    req = request.Request(
        f"{settings.sales_ai_base_url.rstrip('/')}/api/call-recordings/{recording_id}/transcript",
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    return _urlopen_json(req, timeout=120)


def upload_material_to_sales_ai(material: MaterialUpload) -> dict[str, Any]:
    image_path = Path(material.local_file)
    if not image_path.is_file():
        raise RuntimeError(f"Material file does not exist: {image_path}")

    token = _login()
    data: dict[str, str] = {}
    if settings.sales_ai_sales_username:
        data["sales_username"] = settings.sales_ai_sales_username
    return _post_multipart(
        f"{settings.sales_ai_base_url.rstrip('/')}/api/uploads",
        token=token,
        data=data,
        file_field="file",
        file_path=image_path,
        timeout=120,
    )


def _login() -> str:
    payload = json.dumps(
        {
            "username": settings.sales_ai_username,
            "password": settings.sales_ai_password,
        }
    ).encode("utf-8")
    req = request.Request(
        f"{settings.sales_ai_base_url.rstrip('/')}/api/auth/login",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    data = _urlopen_json(req, timeout=30)
    return str(data["access_token"])


def _post_multipart(
    url: str,
    *,
    token: str,
    data: dict[str, str],
    file_field: str,
    file_path: Path,
    timeout: int,
) -> dict[str, Any]:
    boundary = f"----sales-ai-{uuid4().hex}"
    body_parts: list[bytes] = []

    for name, value in data.items():
        body_parts.extend(
            [
                f"--{boundary}\r\n".encode("utf-8"),
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"),
                str(value).encode("utf-8"),
                b"\r\n",
            ]
        )

    body_parts.extend(
        [
            f"--{boundary}\r\n".encode("utf-8"),
            (
                f'Content-Disposition: form-data; name="{file_field}"; '
                f'filename="{file_path.name}"\r\n'
            ).encode("utf-8"),
            f"Content-Type: {_guess_mime(file_path)}\r\n\r\n".encode("utf-8"),
            file_path.read_bytes(),
            b"\r\n",
            f"--{boundary}--\r\n".encode("utf-8"),
        ]
    )

    req = request.Request(
        url,
        data=b"".join(body_parts),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        method="POST",
    )
    return _urlopen_json(req, timeout=timeout)


def _urlopen_json(req: request.Request, timeout: int) -> dict[str, Any]:
    try:
        with request.urlopen(req, timeout=timeout) as response:
            payload = response.read().decode("utf-8")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Sales AI request failed: {exc.code} {detail}") from exc
    data = json.loads(payload)
    if not isinstance(data, dict):
        raise RuntimeError("Sales AI response is not a JSON object")
    return data


def _guess_mime(path: Path) -> str:
    suffix = path.suffix.lower()
    known_types = {
        ".mp3": "audio/mpeg",
        ".wav": "audio/wav",
        ".m4a": "audio/mp4",
        ".aac": "audio/aac",
        ".amr": "audio/amr",
        ".ogg": "audio/ogg",
        ".flac": "audio/flac",
        ".3gp": "audio/3gpp",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".bmp": "image/bmp",
    }
    return known_types.get(suffix, mimetypes.guess_type(path.name)[0] or "application/octet-stream")
