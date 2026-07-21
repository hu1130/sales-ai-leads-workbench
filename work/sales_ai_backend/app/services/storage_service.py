from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import mimetypes
import tempfile
from typing import Iterator
from urllib.parse import quote

from fastapi import HTTPException
from fastapi.responses import FileResponse, RedirectResponse, Response

from app.core.config import get_settings


OSS_SCHEME = "oss://"


def oss_enabled() -> bool:
    settings = get_settings()
    return (
        settings.storage_backend.strip().lower() == "oss"
        and bool(settings.oss_endpoint)
        and bool(settings.oss_bucket)
        and bool(settings.oss_access_key_id)
        and bool(settings.oss_access_key_secret)
    )


def upload_local_file(local_path: Path, *, subdir: str, filename: str, content_type: str | None = None) -> str:
    settings = get_settings()
    key_parts = [settings.oss_prefix.strip("/")] if settings.oss_prefix else []
    if subdir:
        key_parts.append(subdir.strip("/"))
    key_parts.append(filename)
    key = "/".join(part for part in key_parts if part)
    bucket = _oss_bucket()
    bucket.put_object_from_file(key, str(local_path), headers={"Content-Type": content_type or _guess_content_type(filename)})
    return f"{OSS_SCHEME}{settings.oss_bucket}/{key}"


def remove_stored_file(stored_path: str) -> None:
    if is_oss_path(stored_path):
        try:
            _oss_bucket().delete_object(_parse_oss_path(stored_path)[1])
        except Exception:
            return
        return
    try:
        path = Path(stored_path)
        if path.is_file():
            path.unlink()
    except OSError:
        return


def is_oss_path(stored_path: str | None) -> bool:
    return bool(stored_path and stored_path.startswith(OSS_SCHEME))


@contextmanager
def local_file_for_read(stored_path: str) -> Iterator[Path]:
    if not is_oss_path(stored_path):
        yield Path(stored_path)
        return

    bucket_name, key = _parse_oss_path(stored_path)
    suffix = Path(key).suffix
    with tempfile.NamedTemporaryFile(prefix="sales-ai-oss-", suffix=suffix, delete=False) as handle:
        temp_path = Path(handle.name)
    try:
        _oss_bucket(bucket_name).get_object_to_file(key, str(temp_path))
        yield temp_path
    finally:
        try:
            temp_path.unlink()
        except OSError:
            pass


def stored_file_response(stored_path: str, *, filename: str, inline: bool = True) -> Response:
    if is_oss_path(stored_path):
        url = presigned_url(stored_path, filename=filename, inline=inline)
        return RedirectResponse(url)
    media_type = _guess_content_type(filename)
    return FileResponse(
        _resolve_local_upload_file(stored_path),
        media_type=media_type,
        filename=filename,
        content_disposition_type="inline" if inline else "attachment",
    )


def presigned_url(stored_path: str, *, filename: str | None = None, inline: bool = True) -> str:
    settings = get_settings()
    bucket_name, key = _parse_oss_path(stored_path)
    if settings.oss_public_base_url:
        return f"{settings.oss_public_base_url.rstrip('/')}/{quote(key, safe='/')}"
    return _oss_bucket(bucket_name).sign_url("GET", key, settings.oss_signed_url_expires)


def _resolve_local_upload_file(stored_path: str) -> Path:
    settings = get_settings()
    backend_root = Path(__file__).resolve().parents[2]
    upload_root = settings.upload_path
    if not upload_root.is_absolute():
        upload_root = backend_root / upload_root
    upload_root = upload_root.resolve(strict=False)
    path = Path(stored_path)
    if path.is_absolute():
        file_path = path.resolve(strict=False)
    elif path.parts and path.parts[0] == upload_root.name:
        file_path = (upload_root.parent / path).resolve(strict=False)
    else:
        file_path = (upload_root / path).resolve(strict=False)
    try:
        file_path.relative_to(upload_root)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="file not found") from exc
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="file not found")
    return file_path


def _guess_content_type(filename: str) -> str:
    return mimetypes.guess_type(filename)[0] or "application/octet-stream"


def _parse_oss_path(stored_path: str) -> tuple[str, str]:
    if not is_oss_path(stored_path):
        raise ValueError("not an oss path")
    rest = stored_path[len(OSS_SCHEME) :]
    bucket, _, key = rest.partition("/")
    if not bucket or not key:
        raise ValueError("invalid oss path")
    return bucket, key


def _oss_bucket(bucket_name: str | None = None):
    try:
        import oss2
    except ImportError as exc:
        raise RuntimeError("oss2 package is not installed") from exc

    settings = get_settings()
    auth = oss2.Auth(settings.oss_access_key_id, settings.oss_access_key_secret)
    return oss2.Bucket(auth, settings.oss_endpoint, bucket_name or settings.oss_bucket)
