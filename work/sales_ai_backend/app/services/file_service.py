from pathlib import Path
from uuid import uuid4
import hashlib

from fastapi import HTTPException, UploadFile

from app.core.config import get_settings
from app.services.storage_service import oss_enabled, upload_local_file

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".flac", ".ogg", ".opus"}
DOCUMENT_EXTENSIONS = {".pdf", ".doc", ".docx", ".txt", ".md", ".csv"}
ALLOWED_EXTENSIONS = IMAGE_EXTENSIONS | AUDIO_EXTENSIONS | DOCUMENT_EXTENSIONS
MAX_IMAGE_BYTES = 15 * 1024 * 1024
MAX_AUDIO_BYTES = 200 * 1024 * 1024
MAX_DOCUMENT_BYTES = 30 * 1024 * 1024
CHUNK_SIZE = 1024 * 1024


def infer_file_type(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix in IMAGE_EXTENSIONS:
        return "image"
    if suffix in AUDIO_EXTENSIONS:
        return "audio"
    if suffix in DOCUMENT_EXTENSIONS:
        return "document"
    return "unknown"


async def save_upload_file(file: UploadFile, subdir: str = "") -> tuple[str, str, str, int]:
    settings = get_settings()
    upload_dir = settings.upload_path / subdir if subdir else settings.upload_path
    upload_dir.mkdir(parents=True, exist_ok=True)
    original_name = file.filename or "file"
    suffix = Path(original_name).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"不支持的文件格式：{suffix or '无扩展名'}")
    saved_name = f"{uuid4().hex}{suffix}"
    target = upload_dir / saved_name
    max_bytes = _max_size_for_suffix(suffix)
    total = 0
    digest = hashlib.sha256()
    try:
        with target.open("wb") as handle:
            while chunk := await file.read(CHUNK_SIZE):
                total += len(chunk)
                if total > max_bytes:
                    raise HTTPException(status_code=413, detail=f"文件过大，最大允许 {max_bytes // 1024 // 1024} MB")
                digest.update(chunk)
                handle.write(chunk)
    except Exception:
        if target.exists():
            target.unlink()
        raise
    finally:
        await file.close()

    stored_path = str(target)
    if oss_enabled():
        stored_path = upload_local_file(target, subdir=subdir, filename=saved_name, content_type=file.content_type)
        target.unlink(missing_ok=True)
    return original_name, stored_path, digest.hexdigest(), total


def _max_size_for_suffix(suffix: str) -> int:
    if suffix in IMAGE_EXTENSIONS:
        return MAX_IMAGE_BYTES
    if suffix in AUDIO_EXTENSIONS:
        return MAX_AUDIO_BYTES
    return MAX_DOCUMENT_BYTES
