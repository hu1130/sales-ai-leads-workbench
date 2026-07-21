import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session, joinedload

from app.api.deps import assert_same_tenant, assert_user_same_tenant, get_current_user, tenant_id_for
from app.core.database import get_db
from app.models.analysis import AIAnalysisResult
from app.models.call_attempt import CallAttempt
from app.models.call_recording import CallRecording
from app.models.customer import Customer
from app.models.followup import Followup
from app.models.sales_callback import SalesCallback, SalesCallbackEvent
from app.models.upload import UploadRecord
from app.models.user import User
from app.schemas.sales_callback import (
    SalesCallbackListResponse,
    SalesCallbackOut,
    SalesCallbackStart,
    SalesCallbackWebhook,
)
from app.services.ai_service import AIService, build_analysis_result
from app.services.call_provider import CallProviderError, get_call_provider
from app.services.call_provider_settings import get_effective_call_provider_settings
from app.services.call_webhook_security import verify_call_provider_webhook
from app.services.customer_service import update_customer_from_analysis

router = APIRouter()

CALLBACK_STATUSES = {
    "initiated",
    "sales_ringing",
    "sales_answered",
    "customer_ringing",
    "bridged",
    "completed",
    "failed",
    "no_answer",
    "busy",
    "rejected",
}
FINAL_STATUSES = {"completed", "failed", "no_answer", "busy", "rejected"}


@router.post("/customers/{customer_id}/callback", response_model=SalesCallbackOut)
def start_customer_callback(
    customer_id: int,
    payload: SalesCallbackStart | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SalesCallbackOut:
    payload = payload or SalesCallbackStart()
    payload.customer_id = customer_id
    return _start_callback(payload, current_user, db)


@router.post("/sales-callbacks", response_model=SalesCallbackOut)
def start_sales_callback(
    payload: SalesCallbackStart,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SalesCallbackOut:
    return _start_callback(payload, current_user, db)


@router.get("/sales-callbacks", response_model=SalesCallbackListResponse)
def list_sales_callbacks(
    customer_id: int | None = None,
    status: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SalesCallbackListResponse:
    query = db.query(SalesCallback).options(
        joinedload(SalesCallback.customer),
        joinedload(SalesCallback.sales),
        joinedload(SalesCallback.call_attempt),
    ).filter(SalesCallback.tenant_id == tenant_id_for(current_user))
    if current_user.role != "admin":
        query = query.filter(SalesCallback.sales_id == current_user.id)
    if customer_id:
        query = query.filter(SalesCallback.customer_id == customer_id)
    if status:
        query = query.filter(SalesCallback.status == status)
    total = query.count()
    items = (
        query.order_by(SalesCallback.created_at.desc(), SalesCallback.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return SalesCallbackListResponse(
        items=[_callback_out(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/sales-callbacks/{callback_id}", response_model=SalesCallbackOut)
def get_sales_callback(
    callback_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SalesCallbackOut:
    callback = _get_callback_for_user(db, callback_id, current_user)
    return _callback_out(callback)


@router.post("/sales-callbacks/webhook/{provider}", response_model=SalesCallbackOut)
def receive_sales_callback_webhook(
    provider: str,
    payload: SalesCallbackWebhook,
    request: Request,
    db: Session = Depends(get_db),
) -> SalesCallbackOut:
    callback = (
        db.query(SalesCallback)
        .options(
            joinedload(SalesCallback.customer),
            joinedload(SalesCallback.sales),
            joinedload(SalesCallback.call_attempt),
        )
        .filter(SalesCallback.provider == provider)
        .filter(SalesCallback.provider_call_id == payload.provider_call_id)
        .first()
    )
    if callback is None:
        verify_call_provider_webhook(request, db)
        db.add(
            SalesCallbackEvent(
                provider=provider,
                provider_call_id=payload.provider_call_id,
                event_type=payload.event_type,
                payload_json=json.dumps(payload.model_dump(), ensure_ascii=False),
            )
        )
        db.commit()
        raise HTTPException(status_code=404, detail="callback not found")

    verify_call_provider_webhook(request, db, callback.tenant_id)
    _record_callback_event(db, callback, payload)
    _apply_callback_event(db, callback, payload)
    db.commit()
    db.refresh(callback)
    return _callback_out(callback)


def _start_callback(payload: SalesCallbackStart, current_user: User, db: Session) -> SalesCallbackOut:
    if not payload.customer_id:
        raise HTTPException(status_code=400, detail="customer_id is required")

    customer = db.get(Customer, payload.customer_id)
    assert_same_tenant(customer, current_user)
    if customer is None:
        raise HTTPException(status_code=404, detail="客户不存在")
    if current_user.role != "admin" and customer.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权回拨该客户")

    sales = current_user
    if current_user.role == "admin" and payload.sales_id:
        selected_sales = db.get(User, payload.sales_id)
        selected_sales = assert_user_same_tenant(selected_sales, current_user)
        if selected_sales is None or selected_sales.status != "active":
            raise HTTPException(status_code=404, detail="销售账号不存在或已停用")
        sales = selected_sales
    elif current_user.role == "admin" and customer.owner_id:
        selected_sales = db.get(User, customer.owner_id)
        if selected_sales and selected_sales.status == "active" and tenant_id_for(selected_sales) == tenant_id_for(current_user):
            sales = selected_sales

    sales_phone = _clean_phone(payload.sales_phone or sales.phone)
    customer_phone = _clean_phone(payload.customer_phone or customer.phone)
    if not sales_phone:
        raise HTTPException(status_code=400, detail="销售手机号缺失，无法发起服务商回拨")
    if not customer_phone:
        raise HTTPException(status_code=400, detail="客户手机号缺失，无法发起服务商回拨")

    current_tenant_id = tenant_id_for(current_user)
    effective = get_effective_call_provider_settings(db, current_tenant_id)
    provider_name = (payload.provider or effective.provider or "mock").strip().lower()
    try:
        provider = get_call_provider(provider_name, effective)
        launch = provider.start_callback(
            sales_phone=sales_phone,
            customer_phone=customer_phone,
            sales_id=sales.id,
            customer_id=customer.id,
        )
    except CallProviderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    now = datetime.now()
    attempt = CallAttempt(
        tenant_id=current_tenant_id,
        customer_id=customer.id,
        sales_id=sales.id,
        phone=customer_phone,
        call_mode="provider_callback",
        call_status="dialing",
        started_at=now,
        remark=payload.remark,
    )
    db.add(attempt)
    db.flush()

    callback = SalesCallback(
        tenant_id=current_tenant_id,
        customer_id=customer.id,
        sales_id=sales.id,
        call_attempt_id=attempt.id,
        provider=provider.name,
        provider_call_id=launch.provider_call_id,
        sales_phone=sales_phone,
        customer_phone=customer_phone,
        status=launch.initial_status,
        remark=payload.remark,
        started_at=now,
    )
    db.add(callback)
    db.flush()
    db.add(
        SalesCallbackEvent(
            tenant_id=current_tenant_id,
            callback_id=callback.id,
            provider=callback.provider,
            provider_call_id=callback.provider_call_id,
            event_type="callback_requested",
            payload_json=json.dumps(launch.raw_payload, ensure_ascii=False),
        )
    )
    db.commit()
    db.refresh(callback)
    return _callback_out(callback)


def _apply_callback_event(db: Session, callback: SalesCallback, payload: SalesCallbackWebhook) -> None:
    status = payload.status or _status_from_event(payload.event_type)
    if status not in CALLBACK_STATUSES:
        raise HTTPException(status_code=400, detail="invalid callback status")

    now = datetime.now()
    callback.status = status
    callback.failure_reason = payload.failure_reason or callback.failure_reason
    callback.recording_url = payload.recording_url or callback.recording_url
    callback.duration_seconds = payload.duration_seconds if payload.duration_seconds is not None else callback.duration_seconds
    callback.updated_at = now

    attempt = callback.call_attempt
    if attempt is None:
        raise HTTPException(status_code=404, detail="linked call attempt not found")

    if status == "bridged":
        callback.bridged_at = callback.bridged_at or now
        attempt.call_status = "connected"
    elif status in FINAL_STATUSES:
        callback.ended_at = callback.ended_at or now
        attempt.ended_at = callback.ended_at
        attempt.duration_seconds = callback.duration_seconds
        attempt.call_status = "connected" if status == "completed" else status
        if payload.transcript:
            attempt.transcript = payload.transcript.strip()[:50000]
            _analyze_sales_callback_transcript(db, callback, attempt)
        if callback.recording_url:
            _ensure_callback_recording(db, callback, attempt)
        _add_callback_finish_followup(db, callback, attempt)
    else:
        attempt.call_status = "dialing"


def _record_callback_event(db: Session, callback: SalesCallback, payload: SalesCallbackWebhook) -> None:
    db.add(
        SalesCallbackEvent(
            tenant_id=callback.tenant_id,
            callback_id=callback.id,
            provider=callback.provider,
            provider_call_id=callback.provider_call_id,
            event_type=payload.event_type,
            payload_json=json.dumps(payload.model_dump(), ensure_ascii=False),
        )
    )


def _status_from_event(event_type: str) -> str:
    mapping = {
        "callback_initiated": "initiated",
        "sales_ringing": "sales_ringing",
        "sales_answered": "sales_answered",
        "customer_ringing": "customer_ringing",
        "bridged": "bridged",
        "call_bridged": "bridged",
        "completed": "completed",
        "call_completed": "completed",
        "failed": "failed",
        "no_answer": "no_answer",
        "busy": "busy",
        "rejected": "rejected",
    }
    return mapping.get(event_type, event_type)


def _ensure_callback_recording(db: Session, callback: SalesCallback, attempt: CallAttempt) -> None:
    if attempt.call_recording_id:
        return
    recording = CallRecording(
        tenant_id=callback.tenant_id,
        customer_id=callback.customer_id,
        sales_id=callback.sales_id,
        caller_phone=callback.sales_phone,
        callee_phone=callback.customer_phone,
        started_at=callback.bridged_at or callback.started_at,
        ended_at=callback.ended_at,
        duration_seconds=callback.duration_seconds,
        recording_path=callback.recording_url or "",
        transcript=attempt.transcript,
        transcription_status="completed" if attempt.transcript else "pending",
    )
    db.add(recording)
    db.flush()
    attempt.call_recording_id = recording.id


def _analyze_sales_callback_transcript(db: Session, callback: SalesCallback, attempt: CallAttempt) -> None:
    upload = UploadRecord(
        tenant_id=callback.tenant_id,
        customer_id=callback.customer_id,
        uploader_id=callback.sales_id,
        file_type="document",
        file_name=f"sales-callback-{callback.id}-transcript.txt",
        file_path=f"sales-callbacks/sales-callback-{callback.id}.txt",
        status="completed",
    )
    db.add(upload)
    db.flush()
    payload = AIService().analyze_text(attempt.transcript or "", "audio")
    analysis = build_analysis_result(upload, payload)
    analysis.tenant_id = callback.tenant_id
    analysis.customer_id = callback.customer_id
    db.add(analysis)
    db.flush()
    customer = db.get(Customer, callback.customer_id)
    if customer is not None:
        update_customer_from_analysis(customer, analysis)
        customer.last_followup_at = datetime.now()
    attempt.upload_record_id = upload.id
    attempt.ai_analysis_id = analysis.id
    attempt.intent_level = analysis.intent_level
    attempt.intent_score = analysis.intent_score
    attempt.next_action = analysis.next_action


def _add_callback_finish_followup(db: Session, callback: SalesCallback, attempt: CallAttempt) -> None:
    existing = (
        db.query(Followup)
        .filter(Followup.tenant_id == callback.tenant_id)
        .filter(Followup.customer_id == callback.customer_id)
        .filter(Followup.source == "sales_callback")
        .filter(Followup.call_recording_id == attempt.call_recording_id)
        .filter(Followup.created_at >= callback.started_at)
        .first()
    )
    if existing is not None:
        return
    content = [
        f"销售一键回拨：{_status_text(callback.status)}",
        f"销售电话：{_mask_phone(callback.sales_phone)}",
        f"客户电话：{_mask_phone(callback.customer_phone)}",
    ]
    if callback.duration_seconds:
        content.append(f"通话时长：{callback.duration_seconds} 秒")
    if callback.failure_reason:
        content.append(f"失败原因：{callback.failure_reason}")
    if attempt.intent_level:
        content.append(f"AI 复盘：{attempt.intent_level} / {attempt.intent_score or 0}")
    if attempt.next_action:
        content.append(f"下一步：{attempt.next_action}")
    db.add(
        Followup(
            tenant_id=callback.tenant_id,
            customer_id=callback.customer_id,
            user_id=callback.sales_id,
            content="\n".join(content),
            source="sales_callback",
            call_recording_id=attempt.call_recording_id,
            upload_record_id=attempt.upload_record_id,
            status="completed" if callback.status == "completed" else "pending",
            done_at=datetime.now() if callback.status == "completed" else None,
        )
    )
    customer = db.get(Customer, callback.customer_id)
    if customer is not None:
        customer.last_followup_at = datetime.now()


def _get_callback_for_user(db: Session, callback_id: int, user: User) -> SalesCallback:
    callback = (
        db.query(SalesCallback)
        .options(
            joinedload(SalesCallback.customer),
            joinedload(SalesCallback.sales),
            joinedload(SalesCallback.call_attempt),
        )
        .filter(SalesCallback.id == callback_id)
        .first()
    )
    if callback is None:
        raise HTTPException(status_code=404, detail="callback not found")
    assert_same_tenant(callback, user, not_found_detail="callback not found")
    if user.role != "admin" and callback.sales_id != user.id:
        raise HTTPException(status_code=403, detail="permission denied")
    return callback


def _callback_out(callback: SalesCallback) -> SalesCallbackOut:
    return SalesCallbackOut(
        id=callback.id,
        customer_id=callback.customer_id,
        sales_id=callback.sales_id,
        call_attempt_id=callback.call_attempt_id,
        provider=callback.provider,
        provider_call_id=callback.provider_call_id,
        sales_phone=callback.sales_phone,
        customer_phone=callback.customer_phone,
        status=callback.status,
        failure_reason=callback.failure_reason,
        remark=callback.remark,
        recording_url=callback.recording_url,
        started_at=callback.started_at,
        bridged_at=callback.bridged_at,
        ended_at=callback.ended_at,
        duration_seconds=callback.duration_seconds,
        created_at=callback.created_at,
        updated_at=callback.updated_at,
        customer_name=callback.customer.name if callback.customer else None,
        sales_name=callback.sales.name if callback.sales else None,
        call_status=callback.call_attempt.call_status if callback.call_attempt else None,
    )


def _clean_phone(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = "".join(ch for ch in value if ch.isdigit() or ch == "+")
    return cleaned or None


def _mask_phone(phone: str) -> str:
    if len(phone) < 7:
        return phone
    return f"{phone[:3]}****{phone[-4:]}"


def _status_text(status: str) -> str:
    return {
        "initiated": "已发起",
        "sales_ringing": "销售振铃",
        "sales_answered": "销售已接听",
        "customer_ringing": "客户振铃",
        "bridged": "双方已接通",
        "completed": "已完成",
        "failed": "失败",
        "no_answer": "未接通",
        "busy": "忙线",
        "rejected": "拒接",
    }.get(status, status)
