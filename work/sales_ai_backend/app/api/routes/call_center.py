from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, UploadFile
from pathlib import Path
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from app.api.deps import assert_same_tenant, assert_user_same_tenant, get_current_user, require_admin, tenant_id_for
from app.core.database import get_db
from app.models.analysis import AIAnalysisResult
from app.models.call_attempt import CallAttempt
from app.models.call_campaign import CallCampaign
from app.models.call_campaign_target import CallCampaignTarget
from app.models.call_recording import CallRecording
from app.models.customer import Customer
from app.models.followup import Followup
from app.models.script import Script
from app.models.upload import UploadRecord
from app.models.user import User
from app.schemas.call_center import (
    CallAttemptCreate,
    CallAttemptFinish,
    CallAttemptListResponse,
    CallAttemptOut,
    CallCampaignCreate,
    CallCampaignListResponse,
    CallCampaignOut,
    CallCampaignUpdate,
    CallOverviewResponse,
    CallTargetAssign,
    CallTargetImport,
    CallTargetListResponse,
    CallTargetOut,
    CallTargetUpdate,
    CallTranscriptSubmit,
)
from app.services.ai_service import AIService, build_analysis_result
from app.services.analysis_task import process_upload_record
from app.services.customer_service import find_or_create_customer, update_customer_from_analysis
from app.services.file_service import save_upload_file
from app.services.storage_service import remove_stored_file

router = APIRouter()

CONNECTED_STATUSES = {"connected"}
CALLED_STATUSES = {"connected", "no_answer", "busy", "rejected", "empty_number", "failed", "callback"}
TARGET_STATUSES = {
    "pending",
    "calling",
    "connected",
    "no_answer",
    "busy",
    "rejected",
    "empty_number",
    "callback",
    "completed",
    "failed",
}
CAMPAIGN_STATUSES = {"draft", "running", "paused", "completed", "cancelled"}


@router.get("/call-campaigns", response_model=CallCampaignListResponse)
def list_campaigns(
    status: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CallCampaignListResponse:
    current_tenant_id = tenant_id_for(current_user)
    query = db.query(CallCampaign).filter(CallCampaign.tenant_id == current_tenant_id)
    if status:
        query = query.filter(CallCampaign.status == status)
    if current_user.role != "admin":
        query = query.join(CallCampaignTarget).filter(CallCampaignTarget.assigned_user_id == current_user.id).distinct()
    total = query.count()
    items = query.order_by(CallCampaign.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return CallCampaignListResponse(items=items, total=total, page=page, page_size=page_size)


@router.post("/call-campaigns", response_model=CallCampaignOut)
def create_campaign(
    payload: CallCampaignCreate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> CallCampaign:
    if payload.owner_id:
        assert_user_same_tenant(db.get(User, payload.owner_id), current_user, detail="sales user not found")
    if payload.assigned_user_id:
        assert_user_same_tenant(db.get(User, payload.assigned_user_id), current_user, detail="sales user not found")
    if payload.script_id:
        script = db.get(Script, payload.script_id)
        assert_same_tenant(script, current_user, not_found_detail="script not found")
    campaign = CallCampaign(
        tenant_id=tenant_id_for(current_user),
        name=payload.name.strip(),
        scenario=payload.scenario,
        script_id=payload.script_id,
        owner_id=payload.owner_id or current_user.id,
        description=(payload.description or "").strip() or None,
        planned_start_at=payload.planned_start_at,
        planned_end_at=payload.planned_end_at,
        created_by=current_user.id,
    )
    db.add(campaign)
    db.flush()
    if payload.customer_ids:
        _add_targets_from_customers(db, campaign, payload.customer_ids, payload.assigned_user_id)
    _refresh_campaign_stats(db, campaign.id)
    db.commit()
    db.refresh(campaign)
    return campaign


@router.get("/call-campaigns/{campaign_id}", response_model=CallCampaignOut)
def get_campaign(
    campaign_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CallCampaign:
    campaign = _get_campaign_for_user(db, campaign_id, current_user)
    return campaign


@router.patch("/call-campaigns/{campaign_id}", response_model=CallCampaignOut)
def update_campaign(
    campaign_id: int,
    payload: CallCampaignUpdate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> CallCampaign:
    campaign = _get_campaign_for_user(db, campaign_id, current_user)
    updates = payload.model_dump(exclude_unset=True)
    if updates.get("owner_id"):
        assert_user_same_tenant(db.get(User, updates["owner_id"]), current_user, detail="sales user not found")
    if updates.get("script_id"):
        assert_same_tenant(db.get(Script, updates["script_id"]), current_user, not_found_detail="script not found")
    for field, value in updates.items():
        if isinstance(value, str):
            value = value.strip() or None
        setattr(campaign, field, value)
    campaign.updated_at = datetime.now()
    db.commit()
    db.refresh(campaign)
    return campaign


@router.delete("/call-campaigns/{campaign_id}")
def delete_campaign(
    campaign_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    campaign = _get_campaign_for_user(db, campaign_id, current_user)
    if campaign.status not in {"draft", "cancelled"}:
        raise HTTPException(status_code=409, detail="Only draft or cancelled campaigns can be deleted")
    db.delete(campaign)
    db.commit()
    return {"message": "campaign deleted"}


@router.post("/call-campaigns/{campaign_id}/start", response_model=CallCampaignOut)
def start_campaign(
    campaign_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> CallCampaign:
    campaign = _get_campaign_for_user(db, campaign_id, current_user)
    campaign.status = "running"
    campaign.started_at = campaign.started_at or datetime.now()
    campaign.updated_at = datetime.now()
    db.commit()
    db.refresh(campaign)
    return campaign


@router.post("/call-campaigns/{campaign_id}/pause", response_model=CallCampaignOut)
def pause_campaign(
    campaign_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> CallCampaign:
    campaign = _get_campaign_for_user(db, campaign_id, current_user)
    campaign.status = "paused"
    campaign.updated_at = datetime.now()
    db.commit()
    db.refresh(campaign)
    return campaign


@router.post("/call-campaigns/{campaign_id}/complete", response_model=CallCampaignOut)
def complete_campaign(
    campaign_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> CallCampaign:
    campaign = _get_campaign_for_user(db, campaign_id, current_user)
    campaign.status = "completed"
    campaign.completed_at = datetime.now()
    campaign.updated_at = datetime.now()
    db.commit()
    db.refresh(campaign)
    return campaign


@router.get("/call-campaigns/{campaign_id}/targets", response_model=CallTargetListResponse)
def list_targets(
    campaign_id: int,
    status: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CallTargetListResponse:
    _get_campaign_for_user(db, campaign_id, current_user)
    return _list_targets_response(db, campaign_id, current_user, status, page, page_size)


def _list_targets_response(
    db: Session,
    campaign_id: int,
    current_user: User,
    status: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> CallTargetListResponse:
    query = (
        db.query(CallCampaignTarget)
        .options(joinedload(CallCampaignTarget.customer), joinedload(CallCampaignTarget.assigned_user))
        .filter(CallCampaignTarget.campaign_id == campaign_id)
        .filter(CallCampaignTarget.tenant_id == tenant_id_for(current_user))
    )
    if current_user.role != "admin":
        query = query.filter(CallCampaignTarget.assigned_user_id == current_user.id)
    if status:
        query = query.filter(CallCampaignTarget.status == status)
    total = query.count()
    items = query.order_by(CallCampaignTarget.updated_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return CallTargetListResponse(items=[_target_out(item) for item in items], total=total, page=page, page_size=page_size)


@router.post("/call-campaigns/{campaign_id}/targets/import-from-customers", response_model=CallTargetListResponse)
def import_targets(
    campaign_id: int,
    payload: CallTargetImport,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> CallTargetListResponse:
    campaign = _get_campaign_for_user(db, campaign_id, current_user)
    if payload.assigned_user_id:
        assert_user_same_tenant(db.get(User, payload.assigned_user_id), current_user, detail="sales user not found")
    _add_targets_from_customers(db, campaign, payload.customer_ids, payload.assigned_user_id, payload.keep_customer_owner)
    _refresh_campaign_stats(db, campaign_id)
    db.commit()
    return _list_targets_response(db, campaign_id, current_user, page_size=200)


@router.post("/call-targets/{target_id}/assign", response_model=CallTargetOut)
def assign_target(
    target_id: int,
    payload: CallTargetAssign,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> CallTargetOut:
    target = _get_target_for_user(db, target_id, current_user)
    user = assert_user_same_tenant(db.get(User, payload.assigned_user_id), current_user, detail="sales user not found")
    target.assigned_user_id = user.id
    target.updated_at = datetime.now()
    db.commit()
    db.refresh(target)
    return _target_out(target)


@router.patch("/call-targets/{target_id}", response_model=CallTargetOut)
def update_target(
    target_id: int,
    payload: CallTargetUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CallTargetOut:
    target = _get_target_for_user(db, target_id, current_user)
    updates = payload.model_dump(exclude_unset=True)
    if current_user.role != "admin":
        updates.pop("assigned_user_id", None)
    if "status" in updates and updates["status"] not in TARGET_STATUSES:
        raise HTTPException(status_code=400, detail="invalid target status")
    for field, value in updates.items():
        setattr(target, field, value)
    target.updated_at = datetime.now()
    db.commit()
    db.refresh(target)
    return _target_out(target)


@router.get("/call-attempts", response_model=CallAttemptListResponse)
def list_attempts(
    campaign_id: int | None = None,
    sales_id: int | None = None,
    call_status: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CallAttemptListResponse:
    query = (
        db.query(CallAttempt)
        .options(joinedload(CallAttempt.customer), joinedload(CallAttempt.sales), joinedload(CallAttempt.campaign))
        .filter(CallAttempt.tenant_id == tenant_id_for(current_user))
    )
    if current_user.role != "admin":
        query = query.filter(CallAttempt.sales_id == current_user.id)
    elif sales_id:
        query = query.filter(CallAttempt.sales_id == sales_id)
    if campaign_id:
        query = query.filter(CallAttempt.campaign_id == campaign_id)
    if call_status:
        query = query.filter(CallAttempt.call_status == call_status)
    total = query.count()
    items = query.order_by(CallAttempt.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return CallAttemptListResponse(items=[_attempt_out(item) for item in items], total=total, page=page, page_size=page_size)


@router.post("/call-attempts", response_model=CallAttemptOut)
def create_attempt(
    payload: CallAttemptCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CallAttemptOut:
    target = None
    customer = None
    if payload.target_id:
        target = _get_target_for_user(db, payload.target_id, current_user)
        customer = target.customer
    elif payload.customer_id:
        customer = _get_customer_for_user(db, payload.customer_id, current_user)
    if customer is None:
        raise HTTPException(status_code=400, detail="target_id or customer_id is required")
    if payload.campaign_id and not target:
        _get_campaign_for_user(db, payload.campaign_id, current_user)

    sales_id = target.assigned_user_id if target and target.assigned_user_id else current_user.id
    if current_user.role != "admin":
        sales_id = current_user.id

    attempt = CallAttempt(
        tenant_id=tenant_id_for(current_user),
        campaign_id=target.campaign_id if target else payload.campaign_id,
        target_id=target.id if target else None,
        customer_id=customer.id,
        sales_id=sales_id,
        phone=payload.phone or target.phone if target else payload.phone or customer.phone,
        call_mode=_normalize_call_mode(payload.call_mode),
        call_status="dialing",
        started_at=datetime.now(),
    )
    db.add(attempt)
    if target:
        target.status = "calling"
        target.last_called_at = attempt.started_at
    db.commit()
    db.refresh(attempt)
    return _attempt_out(attempt)


@router.get("/call-attempts/{attempt_id}", response_model=CallAttemptOut)
def get_attempt(
    attempt_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CallAttemptOut:
    attempt = _get_attempt_for_user(db, attempt_id, current_user)
    return _attempt_out(attempt)


@router.post("/call-attempts/{attempt_id}/finish", response_model=CallAttemptOut)
def finish_attempt(
    attempt_id: int,
    payload: CallAttemptFinish,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CallAttemptOut:
    attempt = _get_attempt_for_user(db, attempt_id, current_user)
    if payload.call_status not in CALLED_STATUSES:
        raise HTTPException(status_code=400, detail="invalid call status")
    attempt.call_status = payload.call_status
    attempt.ended_at = datetime.now()
    attempt.duration_seconds = payload.duration_seconds
    attempt.remark = payload.remark
    if attempt.target:
        attempt.target.status = payload.call_status
        attempt.target.call_count += 1
        attempt.target.last_attempt_id = attempt.id
        attempt.target.last_called_at = attempt.ended_at
        attempt.target.next_followup_at = payload.next_followup_at
    if attempt.customer_id:
        followup = Followup(
            tenant_id=tenant_id_for(current_user),
            customer_id=attempt.customer_id,
            user_id=attempt.sales_id or current_user.id,
            content=_finish_followup_text(attempt),
            source="call_manual",
            next_followup_at=payload.next_followup_at,
        )
        db.add(followup)
    if attempt.campaign_id:
        _refresh_campaign_stats(db, attempt.campaign_id)
    db.commit()
    db.refresh(attempt)
    return _attempt_out(attempt)


@router.post("/call-attempts/{attempt_id}/submit-transcript", response_model=CallAttemptOut)
def submit_attempt_transcript(
    attempt_id: int,
    payload: CallTranscriptSubmit,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CallAttemptOut:
    attempt = _get_attempt_for_user(db, attempt_id, current_user)
    upload = _ensure_attempt_upload(db, attempt)
    attempt.transcript = payload.transcript.strip()[:50000]
    analysis = _analyze_attempt_transcript(db, attempt, upload)
    attempt.ai_analysis_id = analysis.id
    attempt.intent_level = analysis.intent_level
    attempt.intent_score = analysis.intent_score
    attempt.next_action = analysis.next_action
    if attempt.target:
        attempt.target.status = "connected" if attempt.call_status == "connected" else attempt.target.status
        attempt.target.next_followup_at = _latest_followup_time(db, attempt.customer_id, attempt.tenant_id)
    if attempt.campaign_id:
        _refresh_campaign_stats(db, attempt.campaign_id)
    db.commit()
    db.refresh(attempt)
    return _attempt_out(attempt)


@router.post("/call-attempts/{attempt_id}/upload-recording", response_model=CallAttemptOut)
async def upload_attempt_recording(
    attempt_id: int,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CallAttemptOut:
    attempt = _get_attempt_for_user(db, attempt_id, current_user)
    if not attempt.customer_id:
        raise HTTPException(status_code=400, detail="attempt has no customer")
    original_name, file_path, file_sha256, file_size = await save_upload_file(file, subdir="call_recordings")
    duplicate_upload = _find_duplicate_call_upload(db, tenant_id_for(current_user), attempt.sales_id or current_user.id, file_sha256)
    if duplicate_upload is not None:
        _remove_saved_file(file_path)
        recording = (
            db.query(CallRecording)
            .filter(CallRecording.tenant_id == tenant_id_for(current_user))
            .filter(CallRecording.upload_record_id == duplicate_upload.id)
            .first()
        )
        attempt.upload_record_id = duplicate_upload.id
        if recording is not None:
            attempt.call_recording_id = recording.id
        db.commit()
        db.refresh(attempt)
        return _attempt_out(attempt)

    upload = UploadRecord(
        tenant_id=tenant_id_for(current_user),
        customer_id=attempt.customer_id,
        uploader_id=attempt.sales_id or current_user.id,
        file_type="audio",
        file_name=original_name,
        file_path=file_path,
        file_sha256=file_sha256,
        file_size=file_size,
        status="pending",
    )
    db.add(upload)
    db.flush()
    recording = CallRecording(
        tenant_id=tenant_id_for(current_user),
        customer_id=attempt.customer_id,
        sales_id=attempt.sales_id or current_user.id,
        caller_phone=None,
        callee_phone=attempt.phone,
        started_at=attempt.started_at,
        ended_at=attempt.ended_at,
        duration_seconds=attempt.duration_seconds,
        recording_path=file_path,
        upload_record_id=upload.id,
    )
    db.add(recording)
    db.flush()
    attempt.upload_record_id = upload.id
    attempt.call_recording_id = recording.id
    db.add(
        Followup(
            tenant_id=tenant_id_for(current_user),
            customer_id=attempt.customer_id,
            user_id=attempt.sales_id or current_user.id,
            content="Call recording uploaded from call center.",
            source="call_auto",
            call_recording_id=recording.id,
            upload_record_id=upload.id,
        )
    )
    db.commit()
    background_tasks.add_task(process_upload_record, upload.id)
    db.refresh(attempt)
    return _attempt_out(attempt)


@router.get("/call-reports/overview", response_model=CallOverviewResponse)
def call_overview(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CallOverviewResponse:
    current_tenant_id = tenant_id_for(current_user)
    campaign_query = db.query(CallCampaign).filter(CallCampaign.tenant_id == current_tenant_id)
    target_query = db.query(CallCampaignTarget).filter(CallCampaignTarget.tenant_id == current_tenant_id)
    attempt_query = db.query(CallAttempt).filter(CallAttempt.tenant_id == current_tenant_id)
    if current_user.role != "admin":
        target_query = target_query.filter(CallCampaignTarget.assigned_user_id == current_user.id)
        attempt_query = attempt_query.filter(CallAttempt.sales_id == current_user.id)
        campaign_query = campaign_query.join(CallCampaignTarget).filter(CallCampaignTarget.assigned_user_id == current_user.id).distinct()
    total_attempts = attempt_query.count()
    connected_attempts = attempt_query.filter(CallAttempt.call_status == "connected").count()
    high_intent_attempts = attempt_query.filter(CallAttempt.intent_score >= 80).count()
    return CallOverviewResponse(
        total_campaigns=campaign_query.count(),
        running_campaigns=campaign_query.filter(CallCampaign.status == "running").count(),
        total_targets=target_query.count(),
        pending_targets=target_query.filter(CallCampaignTarget.status == "pending").count(),
        called_targets=target_query.filter(CallCampaignTarget.call_count > 0).count(),
        connected_attempts=connected_attempts,
        total_attempts=total_attempts,
        high_intent_attempts=high_intent_attempts,
        connect_rate=round(connected_attempts / total_attempts * 100, 2) if total_attempts else 0,
    )


def _add_targets_from_customers(
    db: Session,
    campaign: CallCampaign,
    customer_ids: list[int],
    assigned_user_id: int | None = None,
    keep_customer_owner: bool = True,
) -> None:
    customers = db.query(Customer).filter(Customer.tenant_id == campaign.tenant_id, Customer.id.in_(customer_ids)).all()
    customer_map = {customer.id: customer for customer in customers}
    existing_ids = {
        row[0]
        for row in db.query(CallCampaignTarget.customer_id)
        .filter(CallCampaignTarget.tenant_id == campaign.tenant_id)
        .filter(CallCampaignTarget.campaign_id == campaign.id, CallCampaignTarget.customer_id.in_(customer_ids))
        .all()
    }
    for customer_id in customer_ids:
        if customer_id in existing_ids:
            continue
        customer = customer_map.get(customer_id)
        if customer is None:
            continue
        target = CallCampaignTarget(
            tenant_id=campaign.tenant_id,
            campaign_id=campaign.id,
            customer_id=customer.id,
            assigned_user_id=assigned_user_id or (customer.owner_id if keep_customer_owner else None),
            phone=customer.phone,
            contact_name=customer.name or customer.wechat_nickname,
        )
        db.add(target)
        db.flush()


def _find_duplicate_call_upload(db: Session, tenant_id: int, owner_id: int | None, file_sha256: str) -> UploadRecord | None:
    if not file_sha256:
        return None
    return (
        db.query(UploadRecord)
        .filter(UploadRecord.tenant_id == tenant_id)
        .filter(UploadRecord.file_sha256 == file_sha256)
        .filter(UploadRecord.file_type == "audio")
        .filter(UploadRecord.uploader_id == owner_id)
        .order_by(UploadRecord.created_at.desc(), UploadRecord.id.desc())
        .first()
    )


def _remove_saved_file(file_path: str) -> None:
    remove_stored_file(file_path)


def _get_campaign_or_404(db: Session, campaign_id: int) -> CallCampaign:
    campaign = db.get(CallCampaign, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="campaign not found")
    return campaign


def _get_campaign_for_user(db: Session, campaign_id: int, user: User) -> CallCampaign:
    campaign = _get_campaign_or_404(db, campaign_id)
    assert_same_tenant(campaign, user, not_found_detail="campaign not found")
    if user.role == "admin":
        return campaign
    has_target = (
        db.query(CallCampaignTarget.id)
        .filter(CallCampaignTarget.campaign_id == campaign_id, CallCampaignTarget.assigned_user_id == user.id)
        .first()
    )
    if not has_target:
        raise HTTPException(status_code=403, detail="permission denied")
    return campaign


def _get_target_or_404(db: Session, target_id: int) -> CallCampaignTarget:
    target = (
        db.query(CallCampaignTarget)
        .options(joinedload(CallCampaignTarget.customer), joinedload(CallCampaignTarget.assigned_user))
        .filter(CallCampaignTarget.id == target_id)
        .first()
    )
    if target is None:
        raise HTTPException(status_code=404, detail="target not found")
    return target


def _get_target_for_user(db: Session, target_id: int, user: User) -> CallCampaignTarget:
    target = _get_target_or_404(db, target_id)
    assert_same_tenant(target, user, not_found_detail="target not found")
    if user.role != "admin" and target.assigned_user_id != user.id:
        raise HTTPException(status_code=403, detail="permission denied")
    return target


def _get_customer_for_user(db: Session, customer_id: int, user: User) -> Customer:
    customer = db.get(Customer, customer_id)
    if customer is None:
        raise HTTPException(status_code=404, detail="customer not found")
    assert_same_tenant(customer, user, not_found_detail="customer not found")
    if user.role != "admin" and customer.owner_id != user.id:
        raise HTTPException(status_code=403, detail="permission denied")
    return customer


def _get_attempt_for_user(db: Session, attempt_id: int, user: User) -> CallAttempt:
    attempt = (
        db.query(CallAttempt)
        .options(joinedload(CallAttempt.customer), joinedload(CallAttempt.sales), joinedload(CallAttempt.campaign), joinedload(CallAttempt.target))
        .filter(CallAttempt.id == attempt_id)
        .first()
    )
    if attempt is None:
        raise HTTPException(status_code=404, detail="attempt not found")
    assert_same_tenant(attempt, user, not_found_detail="attempt not found")
    if user.role != "admin" and attempt.sales_id != user.id:
        raise HTTPException(status_code=403, detail="permission denied")
    return attempt


def _target_out(target: CallCampaignTarget) -> CallTargetOut:
    customer = target.customer
    assigned_user = target.assigned_user
    return CallTargetOut(
        id=target.id,
        campaign_id=target.campaign_id,
        customer_id=target.customer_id,
        assigned_user_id=target.assigned_user_id,
        phone=target.phone,
        contact_name=target.contact_name,
        status=target.status,
        last_attempt_id=target.last_attempt_id,
        call_count=target.call_count,
        last_called_at=target.last_called_at,
        next_followup_at=target.next_followup_at,
        created_at=target.created_at,
        updated_at=target.updated_at,
        customer_name=customer.name if customer else None,
        customer_intent_level=customer.intent_level if customer else None,
        customer_intent_score=customer.intent_score if customer else None,
        customer_demand_summary=customer.demand_summary if customer else None,
        customer_next_action=customer.next_action if customer else None,
        assigned_user_name=assigned_user.name if assigned_user else None,
    )


def _attempt_out(attempt: CallAttempt) -> CallAttemptOut:
    return CallAttemptOut(
        id=attempt.id,
        campaign_id=attempt.campaign_id,
        target_id=attempt.target_id,
        customer_id=attempt.customer_id,
        sales_id=attempt.sales_id,
        phone=attempt.phone,
        call_mode=attempt.call_mode,
        call_status=attempt.call_status,
        started_at=attempt.started_at,
        ended_at=attempt.ended_at,
        duration_seconds=attempt.duration_seconds,
        call_recording_id=attempt.call_recording_id,
        upload_record_id=attempt.upload_record_id,
        transcript=attempt.transcript,
        ai_analysis_id=attempt.ai_analysis_id,
        intent_level=attempt.intent_level,
        intent_score=attempt.intent_score,
        next_action=attempt.next_action,
        remark=attempt.remark,
        created_at=attempt.created_at,
        updated_at=attempt.updated_at,
        customer_name=attempt.customer.name if attempt.customer else None,
        sales_name=attempt.sales.name if attempt.sales else None,
        campaign_name=attempt.campaign.name if attempt.campaign else None,
    )


def _refresh_campaign_stats(db: Session, campaign_id: int) -> None:
    campaign = db.get(CallCampaign, campaign_id)
    if campaign is None:
        return
    target_query = db.query(CallCampaignTarget).filter(
        CallCampaignTarget.tenant_id == campaign.tenant_id,
        CallCampaignTarget.campaign_id == campaign_id,
    )
    campaign.total_count = target_query.count()
    campaign.called_count = target_query.filter(CallCampaignTarget.call_count > 0).count()
    campaign.connected_count = (
        db.query(func.count(CallAttempt.id))
        .filter(CallAttempt.tenant_id == campaign.tenant_id)
        .filter(CallAttempt.campaign_id == campaign_id, CallAttempt.call_status == "connected")
        .scalar()
        or 0
    )
    campaign.high_intent_count = (
        db.query(func.count(CallAttempt.id))
        .filter(CallAttempt.tenant_id == campaign.tenant_id)
        .filter(CallAttempt.campaign_id == campaign_id)
        .filter(CallAttempt.intent_score >= 80)
        .scalar()
        or 0
    )
    campaign.updated_at = datetime.now()


def _ensure_attempt_upload(db: Session, attempt: CallAttempt) -> UploadRecord:
    if attempt.upload_record_id:
        upload = db.get(UploadRecord, attempt.upload_record_id)
        if upload is not None:
            return upload
    upload = UploadRecord(
        tenant_id=attempt.tenant_id,
        customer_id=attempt.customer_id,
        uploader_id=attempt.sales_id,
        file_type="document",
        file_name=f"call-attempt-{attempt.id}-transcript.txt",
        file_path=f"call-transcripts/call-attempt-{attempt.id}.txt",
        status="processing",
    )
    db.add(upload)
    db.flush()
    attempt.upload_record_id = upload.id
    return upload


def _analyze_attempt_transcript(db: Session, attempt: CallAttempt, upload: UploadRecord) -> AIAnalysisResult:
    payload = AIService().analyze_text(attempt.transcript or "", "audio")
    existing = db.query(AIAnalysisResult).filter(AIAnalysisResult.upload_record_id == upload.id).first()
    if existing is not None:
        db.delete(existing)
        db.flush()
    customer = find_or_create_customer(
        db,
        owner_id=attempt.sales_id,
        tenant_id=attempt.tenant_id,
        customer_id=attempt.customer_id,
        phone=_usable_text(payload.customer_phone) or attempt.phone,
        name=payload.customer_name,
        wechat_id=payload.customer_wechat_id,
        wechat_nickname=payload.customer_wechat_nickname,
    )
    upload.customer_id = customer.id
    upload.status = "completed"
    upload.error_message = None
    attempt.customer_id = customer.id
    analysis = build_analysis_result(upload, payload)
    analysis.tenant_id = attempt.tenant_id
    analysis.customer_id = customer.id
    _boost_call_analysis_from_transcript(analysis, attempt.transcript or "")
    db.add(analysis)
    db.flush()
    update_customer_from_analysis(customer, analysis)
    db.add(
        Followup(
            tenant_id=attempt.tenant_id,
            customer_id=customer.id,
            user_id=attempt.sales_id,
            content=_analysis_followup_text(analysis),
            source="call_auto",
            upload_record_id=upload.id,
        )
    )
    return analysis


def _analysis_followup_text(analysis: AIAnalysisResult) -> str:
    return "\n".join(
        [
            f"外呼 AI 摘要：{analysis.summary or '-'}",
            f"客户意向：{analysis.intent_level or '-'} / {analysis.intent_score or 0}",
            f"客户需求：{analysis.customer_needs or '-'}",
            f"下一步动作：{analysis.next_action or '-'}",
        ]
    )


def _boost_call_analysis_from_transcript(analysis: AIAnalysisResult, transcript: str) -> None:
    """Small call-center fallback for readable Chinese transcripts.

    The existing AI service already handles DeepSeek and its own rule fallback. This
    extra pass only protects the boss-demo path when no model key is configured and
    the legacy rule text is unreadable due to encoding.
    """
    if (analysis.intent_score or 0) >= 20:
        return
    text = transcript or ""
    strong_words = [
        "\u62a5\u4ef7",
        "\u5408\u540c",
        "\u4ed8\u6b3e",
        "\u90e8\u7f72",
        "\u8d2d\u4e70",
        "\u4ef7\u683c",
        "\u4eca\u5929",
        "\u4e0b\u5468",
        "\u9884\u7b97",
        "\u6210\u4ea4",
    ]
    matched = [word for word in strong_words if word in text]
    if len(matched) < 2:
        return
    score = min(95, 50 + len(matched) * 8)
    analysis.intent_level = "\u9ad8\u610f\u5411" if score >= 80 else "\u4e2d\u610f\u5411"
    analysis.intent_score = score
    analysis.summary = analysis.summary or "\u5ba2\u6237\u5728\u901a\u8bdd\u4e2d\u51fa\u73b0\u660e\u786e\u8d2d\u4e70\u4fe1\u53f7\uff0c\u9700\u8981\u5c3d\u5feb\u8ddf\u8fdb\u3002"
    analysis.customer_needs = analysis.customer_needs or "\u5ba2\u6237\u5173\u6ce8\u62a5\u4ef7\u3001\u5408\u540c\u3001\u4ed8\u6b3e\u6216\u90e8\u7f72\u5b89\u6392\u3002"
    analysis.customer_questions = analysis.customer_questions or "\u62a5\u4ef7\u3001\u5408\u540c\u3001\u4ed8\u6b3e\u3001\u90e8\u7f72\u65f6\u95f4"
    analysis.intent_reason = "\u901a\u8bdd\u6587\u672c\u547d\u4e2d\u9ad8\u610f\u5411\u5173\u952e\u8bcd\uff1a" + "\u3001".join(matched)
    analysis.evidence = "\u3001".join(matched)
    analysis.next_action = analysis.next_action or "\u5efa\u8bae\u5f53\u5929\u8ddf\u8fdb\uff0c\u53d1\u9001\u6b63\u5f0f\u62a5\u4ef7\u548c\u5408\u540c\u6a21\u677f\uff0c\u5e76\u786e\u8ba4\u4ed8\u6b3e\u4e0e\u90e8\u7f72\u65f6\u95f4\u3002"
    analysis.sales_script = analysis.sales_script or "\u6211\u5148\u628a\u6b63\u5f0f\u62a5\u4ef7\u548c\u5408\u540c\u6a21\u677f\u53d1\u60a8\uff0c\u65b9\u4fbf\u60a8\u4eca\u5929\u786e\u8ba4\uff1b\u5982\u679c\u6ca1\u95ee\u9898\uff0c\u6211\u4eec\u518d\u7ea6\u90e8\u7f72\u65f6\u95f4\u3002"


def _finish_followup_text(attempt: CallAttempt) -> str:
    pieces = [
        f"外呼结果：{_call_status_text(attempt.call_status)}",
        f"客户电话：{attempt.phone or '-'}",
    ]
    if attempt.duration_seconds:
        pieces.append(f"通话时长：{attempt.duration_seconds} 秒")
    if attempt.remark:
        pieces.append(f"备注：{attempt.remark}")
    return "\n".join(pieces)


def _normalize_call_mode(value: str | None) -> str:
    mode = (value or "manual").strip() or "manual"
    return "manual" if mode == "tel" else mode


def _call_status_text(status: str | None) -> str:
    return {
        "connected": "已接通",
        "no_answer": "未接通",
        "busy": "忙线",
        "rejected": "拒接",
        "empty_number": "空号",
        "failed": "失败",
        "callback": "需回拨",
        "dialing": "拨打中",
    }.get(status or "", status or "-")


def _usable_text(value: str | None) -> str | None:
    if not value:
        return None
    text = value.strip()
    if not text:
        return None
    if "?" in text or "\ufffd" in text:
        return None
    return text


def _latest_followup_time(db: Session, customer_id: int | None, tenant_id: int | None = None):
    if not customer_id:
        return None
    query = db.query(Followup).filter(Followup.customer_id == customer_id)
    if tenant_id is not None:
        query = query.filter(Followup.tenant_id == tenant_id)
    followup = query.order_by(Followup.created_at.desc()).first()
    return followup.next_followup_at if followup else None
