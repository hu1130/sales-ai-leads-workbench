from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TMP = ROOT / ".test_tmp"


def configure_env() -> Path:
    if TMP.exists():
        resolved = TMP.resolve()
        if resolved == ROOT.resolve() or ROOT.resolve() not in resolved.parents:
            raise RuntimeError(f"Refusing to remove unexpected path: {resolved}")
        shutil.rmtree(TMP)
    TMP.mkdir(parents=True, exist_ok=True)
    os.environ["SALES_AI_BASE_URL"] = "http://sales-ai.test"
    os.environ["SALES_AI_USERNAME"] = "admin"
    os.environ["SALES_AI_PASSWORD"] = "admin123"
    audio = TMP / "13800000000_20260617093000.mp3"
    audio.write_bytes(b"fake mp3 bytes")
    return audio


audio_path = configure_env()
sys.path.insert(0, str(ROOT))

from app.database import CallRecord, MaterialUpload  # noqa: E402
from app import sales_ai_upload  # noqa: E402


class FakeUrlopenResponse:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self) -> bytes:
        return self.payload


class FakeUrlopen:
    calls: list[object] = []

    @classmethod
    def __call__(cls, req, timeout=0):
        cls.calls.append(req)
        if req.full_url.endswith("/api/auth/login"):
            return FakeUrlopenResponse(b'{"access_token":"fake-token"}')
        if req.full_url.endswith("/api/call-recordings"):
            body = req.data or b""
            assert b'13800000000' in body
            assert b'2026-06-17T09:30:00' in body
            assert audio_path.name.encode("utf-8") in body
            assert req.headers["Authorization"] == "Bearer fake-token"
            return FakeUrlopenResponse(b'{"recording_id":9,"upload_record_id":18,"status":"pending"}')
        if req.full_url.endswith("/api/call-recordings/9/transcript"):
            assert "测试通话转写".encode("utf-8") in (req.data or b"")
            return FakeUrlopenResponse(
                b'{"recording_id":9,"upload_record_id":18,"transcription_status":"completed"}'
            )
        if req.full_url.endswith("/api/uploads"):
            body = req.data or b""
            assert b"wechat-long.png" in body
            assert b"Content-Type: image/png" in body
            assert req.headers["Authorization"] == "Bearer fake-token"
            return FakeUrlopenResponse(b'{"id":21,"status":"pending","message":"uploaded"}')
        raise AssertionError(f"Unexpected URL: {req.full_url}")


def main() -> None:
    sales_ai_upload.request.urlopen = FakeUrlopen()  # type: ignore[method-assign]
    record = CallRecord(
        id=1,
        salesperson_id="sales_001",
        phone_number="13800000000",
        call_time="2026-06-17T09:30:00",
        source_file=str(audio_path),
        local_file=str(audio_path),
        wav_file=None,
        transcript=None,
        summary=None,
        sales_ai_upload_id=None,
        sales_ai_recording_id=None,
        sales_ai_uploaded_at=None,
        upload_status="pending",
        upload_error=None,
        transcript_synced_at=None,
        transcript_sync_error=None,
        status="pulled",
        error_message=None,
    )

    result = sales_ai_upload.upload_recording_to_sales_ai(record)
    assert result["upload_record_id"] == 18
    transcript_result = sales_ai_upload.submit_transcript_to_sales_ai(9, "测试通话转写")
    assert transcript_result["transcription_status"] == "completed"
    image_path = TMP / "wechat-long.png"
    image_path.write_bytes(b"fake png bytes")
    material = MaterialUpload(
        id=2,
        source_file=str(image_path),
        local_file=str(image_path),
        sales_ai_upload_id=None,
        upload_status="pending",
        upload_error=None,
    )
    material_result = sales_ai_upload.upload_material_to_sales_ai(material)
    assert material_result["id"] == 21
    print("PASS: Sales AI upload client sends recordings, transcripts, and customer images")


if __name__ == "__main__":
    main()
