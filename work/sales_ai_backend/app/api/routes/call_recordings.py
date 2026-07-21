from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import assert_same_tenant, assert_user_same_tenant, get_current_user, tenant_id_for
from app.core.database import get_db
from app.models.call_recording import CallRecording
from app.models.followup import Followup
from app.models.upload import UploadRecord
from app.models.user import User
from app.schemas.call_recording import CallRecordingUploadResponse, CallTranscriptResponse, CallTranscriptUpdate
from app.services.analysis_task import process_upload_record, process_upload_transcript
from app.services.customer_service import find_or_create_customer
from app.services.file_service import save_upload_file
from app.services.storage_service import remove_stored_file

router = APIRouter()


@router.post("", response_model=CallRecordingUploadResponse)
async def upload_call_recording(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    customer_id: int | None = Form(default=None),
    sales_id: int | None = Form(default=None),
    sales_username: str | None = Form(default=None),
    caller_phone: str | None = Form(default=None),
    callee_phone: str | None = Form(default=None),
    started_at: datetime | None = Form(default=None),
    ended_at: datetime | None = Form(default=None),
    duration_seconds: int | None = Form(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CallRecordingUploadResponse:
    current_tenant_id = tenant_id_for(current_user)
    owner_id = current_user.id
    if current_user.role == "admin" and sales_username:
        sales_user = db.query(User).filter(User.tenant_id == current_tenant_id, User.username == sales_username, User.status == "active").first()
        if sales_user is None:
            raise HTTPException(status_code=400, detail="指定销售账号不存在或已停用")
        owner_id = sales_user.id
    elif current_user.role == "admin" and sales_id:
        owner_id = assert_user_same_tenant(db.get(User, sales_id), current_user).id
    original_name, file_path, file_sha256, file_size = await save_upload_file(file, subdir="call_recordings")
    duplicate = _find_duplicate_recording(db, current_tenant_id, owner_id, file_sha256)
    if duplicate is not None and duplicate.upload_record_id is not None:
        _remove_saved_file(file_path)
        upload = db.get(UploadRecord, duplicate.upload_record_id)
        return CallRecordingUploadResponse(
            recording_id=duplicate.id,
            upload_record_id=duplicate.upload_record_id,
            status=upload.status if upload else "completed",
            duplicate=True,
            duplicate_of_id=duplicate.upload_record_id,
        )

    phone = callee_phone or caller_phone
    customer = find_or_create_customer(db, owner_id=owner_id, tenant_id=current_tenant_id, customer_id=customer_id, phone=phone, name=None)
    if current_user.role != "admin" and customer.owner_id not in (None, current_user.id):
        _remove_saved_file(file_path)
        raise HTTPException(status_code=403, detail="无权给该客户上传通话录音")

    if customer.owner_id is None:
        customer.owner_id = owner_id

    upload_record = UploadRecord(
        tenant_id=current_tenant_id,
        customer_id=customer.id,
        uploader_id=owner_id,
        file_type="audio",
        file_name=original_name,
        file_path=file_path,
        file_sha256=file_sha256,
        file_size=file_size,
        status="pending",
    )
    db.add(upload_record)
    db.flush()

    recording = CallRecording(
        tenant_id=current_tenant_id,
        customer_id=customer.id,
        sales_id=owner_id,
        caller_phone=caller_phone,
        callee_phone=callee_phone,
        started_at=started_at,
        ended_at=ended_at,
        duration_seconds=duration_seconds,
        recording_path=file_path,
        upload_record_id=upload_record.id,
    )
    db.add(recording)
    db.flush()
    followup = Followup(
        tenant_id=current_tenant_id,
        customer_id=customer.id,
        user_id=owner_id,
        content="通话录音已上传，系统已自动创建通话跟进。语音识别接入后会自动生成通话摘要、客户异议和下一步建议。",
        source="call_auto",
        call_recording_id=recording.id,
        upload_record_id=upload_record.id,
    )
    customer.last_followup_at = datetime.now()
    db.add(followup)
    db.commit()
    db.refresh(recording)
    db.refresh(upload_record)
    background_tasks.add_task(process_upload_record, upload_record.id)
    return CallRecordingUploadResponse(
        recording_id=recording.id,
        upload_record_id=upload_record.id,
        status=upload_record.status,
    )


@router.post("/{recording_id}/transcript", response_model=CallTranscriptResponse)
def submit_call_transcript(
    recording_id: int,
    payload: CallTranscriptUpdate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CallTranscriptResponse:
    recording = db.get(CallRecording, recording_id)
    assert_same_tenant(recording, current_user)
    if recording is None:
        raise HTTPException(status_code=404, detail="通话录音不存在")
    if current_user.role != "admin" and recording.sales_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权更新该通话录音")
    transcript = payload.transcript.strip()
    if len(transcript) < 2:
        raise HTTPException(status_code=400, detail="转写文本不能为空")
    if recording.upload_record_id is None:
        raise HTTPException(status_code=409, detail="该录音没有关联上传记录")

    recording.transcript = transcript[:50000]
    recording.transcription_status = "completed"
    recording.transcription_error = None
    upload = db.get(UploadRecord, recording.upload_record_id)
    if upload is not None:
        upload.status = "pending"
        upload.error_message = None
    db.commit()
    background_tasks.add_task(process_upload_transcript, recording.upload_record_id, recording.transcript)
    return CallTranscriptResponse(
        recording_id=recording.id,
        upload_record_id=recording.upload_record_id,
        transcription_status=recording.transcription_status,
    )


def _find_duplicate_recording(db: Session, tenant_id: int, owner_id: int | None, file_sha256: str) -> CallRecording | None:
    if not file_sha256:
        return None
    return (
        db.query(CallRecording)
        .join(UploadRecord, UploadRecord.id == CallRecording.upload_record_id)
        .filter(CallRecording.tenant_id == tenant_id)
        .filter(UploadRecord.file_sha256 == file_sha256)
        .filter(UploadRecord.uploader_id == owner_id)
        .order_by(CallRecording.created_at.desc(), CallRecording.id.desc())
        .first()
    )


def _remove_saved_file(file_path: str) -> None:
    remove_stored_file(file_path)
