import mimetypes
from pathlib import Path
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.database import get_db
from app.models.followup import Followup
from app.models.upload import UploadRecord
from app.models.user import User
from app.schemas.upload import UploadCreateResponse, UploadListResponse, UploadOut
from app.services.analysis_task import process_upload_record
from app.services.customer_service import find_or_create_customer
from app.services.file_service import infer_file_type, save_upload_file

router = APIRouter()


@router.post("", response_model=UploadCreateResponse)
async def upload_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    customer_id: int | None = Form(default=None),
    customer_phone: str | None = Form(default=None),
    customer_name: str | None = Form(default=None),
    note: str | None = Form(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UploadCreateResponse:
    del note
    customer = None
    if customer_id or customer_phone or customer_name:
        customer = find_or_create_customer(
            db,
            owner_id=current_user.id,
            customer_id=customer_id,
            phone=customer_phone,
            name=customer_name,
        )
        if current_user.role != "admin" and customer.owner_id not in (None, current_user.id):
            raise HTTPException(status_code=403, detail="无权给该客户上传资料")
        if customer.owner_id is None:
            customer.owner_id = current_user.id

    original_name, file_path = await save_upload_file(file)
    file_type = infer_file_type(original_name)

    record = UploadRecord(
        customer_id=customer.id if customer else None,
        uploader_id=current_user.id,
        file_type=file_type,
        file_name=original_name,
        file_path=file_path,
        status="pending",
    )
    db.add(record)
    db.flush()
    if customer is not None:
        followup = Followup(
            customer_id=customer.id,
            user_id=current_user.id,
            content=_build_upload_followup_content(file_type, original_name),
            source="material_auto",
            upload_record_id=record.id,
        )
        customer.last_followup_at = datetime.now()
        db.add(followup)
    db.commit()
    db.refresh(record)
    background_tasks.add_task(process_upload_record, record.id)
    return UploadCreateResponse(id=record.id, status=record.status, message="上传成功，正在分析")


@router.get("", response_model=UploadListResponse)
def list_uploads(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status: str | None = None,
    file_type: str | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UploadListResponse:
    query = db.query(UploadRecord).options(joinedload(UploadRecord.analysis))
    if current_user.role != "admin":
        query = query.filter(UploadRecord.uploader_id == current_user.id)
    if status:
        query = query.filter(UploadRecord.status == status)
    if file_type:
        query = query.filter(UploadRecord.file_type == file_type)
    total = query.count()
    items = (
        query.order_by(UploadRecord.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return UploadListResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/{upload_id}", response_model=UploadOut)
def get_upload(
    upload_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UploadRecord:
    record = _get_upload_for_user(db, upload_id, current_user)
    return record


@router.get("/{upload_id}/file")
def get_upload_file(
    upload_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FileResponse:
    record = _get_upload_for_user(db, upload_id, current_user)
    upload_root = get_settings().upload_path.resolve()
    stored_path = Path(record.file_path)
    file_path = stored_path.resolve() if stored_path.is_absolute() else (Path.cwd() / stored_path).resolve()
    try:
        file_path.relative_to(upload_root)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="原始文件不存在") from exc
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="原始文件不存在")
    media_type = mimetypes.guess_type(record.file_name)[0] or "application/octet-stream"
    return FileResponse(
        file_path,
        media_type=media_type,
        filename=record.file_name,
        content_disposition_type="inline",
    )


@router.post("/{upload_id}/reanalyze", response_model=UploadCreateResponse)
def reanalyze_upload(
    upload_id: int,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UploadCreateResponse:
    record = _get_upload_for_user(db, upload_id, current_user)
    record.status = "pending"
    record.error_message = None
    db.commit()
    background_tasks.add_task(process_upload_record, record.id)
    return UploadCreateResponse(id=record.id, status=record.status, message="已提交重新分析")


def _get_upload_for_user(db: Session, upload_id: int, current_user: User) -> UploadRecord:
    query = db.query(UploadRecord).options(joinedload(UploadRecord.analysis)).filter(UploadRecord.id == upload_id)
    if current_user.role != "admin":
        query = query.filter(UploadRecord.uploader_id == current_user.id)
    record = query.first()
    if record is None:
        raise HTTPException(status_code=404, detail="上传记录不存在")
    return record


def _build_upload_followup_content(file_type: str, file_name: str) -> str:
    type_text = {
        "image": "微信图片/聊天截图",
        "audio": "录音资料",
        "document": "文档资料",
    }.get(file_type, "客户资料")
    return f"{type_text}《{file_name}》已上传，系统已自动创建资料跟进。AI分析完成后会回填摘要、客户意向和下一步建议。"
