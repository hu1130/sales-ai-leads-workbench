from datetime import datetime, timedelta
import json
import re

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session, joinedload

from app.api.deps import assert_same_tenant, get_current_user_or_platform_service, require_admin_or_platform_service, tenant_id_for
from app.core.database import get_db
from app.models.ai_robot_call import AiRobotCall, AiRobotCallEvent
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
from app.schemas.ai_robot_call import (
    AiRobotCallListResponse,
    AiRobotCallOut,
    AiRobotCampaignStart,
    AiRobotCampaignStartResponse,
    AiRobotSyncPendingResponse,
    AiRobotWebhook,
)
from app.services.ai_service import AIService, build_analysis_result
from app.services.call_provider import CallProviderError, get_call_provider
from app.services.call_provider_settings import get_effective_call_provider_settings
from app.services.call_webhook_security import verify_call_provider_webhook
from app.services.customer_service import find_or_create_customer, update_customer_from_analysis

router = APIRouter()

ROBOT_STATUSES = {
    "initiated",
    "dialing",
    "answered",
    "completed",
    "no_answer",
    "busy",
    "rejected",
    "empty_number",
    "failed",
}
ROBOT_TERMINAL_STATUSES = {"completed", "no_answer", "busy", "rejected", "empty_number", "failed"}
SYNC_INCOMPLETE_TERMINAL_WINDOW_MINUTES = 30


@router.post("/call-campaigns/{campaign_id}/ai-robot/start", response_model=AiRobotCampaignStartResponse)
def start_ai_robot_campaign(
    campaign_id: int,
    payload: AiRobotCampaignStart,
    current_user: User = Depends(require_admin_or_platform_service),
    db: Session = Depends(get_db),
) -> AiRobotCampaignStartResponse:
    campaign = _get_campaign_or_404(db, campaign_id)
    assert_same_tenant(campaign, current_user, not_found_detail="campaign not found")
    current_tenant_id = tenant_id_for(current_user)
    effective = get_effective_call_provider_settings(db, current_tenant_id)
    provider = _provider_or_400(payload.provider or effective.provider, effective)
    script_text = _resolve_script_text(db, campaign, payload.script)

    query = (
        db.query(CallCampaignTarget)
        .options(joinedload(CallCampaignTarget.customer), joinedload(CallCampaignTarget.assigned_user))
        .filter(CallCampaignTarget.campaign_id == campaign_id)
        .filter(CallCampaignTarget.tenant_id == current_tenant_id)
    )
    if payload.only_pending:
        query = query.filter(CallCampaignTarget.status == "pending")
    else:
        query = query.filter(CallCampaignTarget.status.in_(["pending", "no_answer", "busy", "failed", "callback"]))

    targets = query.order_by(CallCampaignTarget.created_at.asc(), CallCampaignTarget.id.asc()).limit(payload.max_calls).all()
    launched: list[AiRobotCall] = []
    skipped = 0
    now = datetime.now()

    for target in targets:
        customer = target.customer
        phone = _normalize_phone(target.phone or (customer.phone if customer else None))
        if not phone or customer is None:
            skipped += 1
            continue

        owner_id = target.assigned_user_id or campaign.owner_id or current_user.id
        try:
            launch = provider.start_ai_robot_call(
                customer_phone=phone,
                script_text=script_text,
                campaign_id=campaign.id,
                target_id=target.id,
                customer_id=customer.id,
            )
        except CallProviderError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        attempt = CallAttempt(
            tenant_id=current_tenant_id,
            campaign_id=campaign.id,
            target_id=target.id,
            customer_id=customer.id,
            sales_id=owner_id,
            phone=phone,
            call_mode="ai_robot",
            call_status="dialing",
            started_at=now,
        )
        db.add(attempt)
        db.flush()

        robot_call = AiRobotCall(
            tenant_id=current_tenant_id,
            campaign_id=campaign.id,
            target_id=target.id,
            customer_id=customer.id,
            owner_id=owner_id,
            call_attempt_id=attempt.id,
            provider=provider.name,
            provider_call_id=launch.provider_call_id,
            phone=phone,
            script_text=script_text,
            status=launch.initial_status,
            started_at=now,
            raw_payload_json=_json_dump(launch.raw_payload),
        )
        db.add(robot_call)
        db.flush()
        db.add(
            AiRobotCallEvent(
                tenant_id=current_tenant_id,
                robot_call_id=robot_call.id,
                provider=robot_call.provider,
                provider_call_id=robot_call.provider_call_id,
                event_type="robot_call_requested",
                payload_json=_json_dump(launch.raw_payload),
            )
        )

        target.status = "calling"
        target.last_called_at = now
        target.last_attempt_id = attempt.id
        target.updated_at = now
        launched.append(robot_call)

    if launched:
        campaign.status = "running"
        campaign.started_at = campaign.started_at or now
        campaign.updated_at = now
    _refresh_campaign_stats(db, campaign.id)
    db.commit()
    for item in launched:
        db.refresh(item)
    return AiRobotCampaignStartResponse(
        campaign_id=campaign.id,
        launched=len(launched),
        skipped=skipped,
        items=[_robot_call_out(item) for item in launched],
    )


@router.get("/ai-robot-calls", response_model=AiRobotCallListResponse)
def list_ai_robot_calls(
    campaign_id: int | None = None,
    customer_id: int | None = None,
    status: str | None = None,
    high_intent: bool | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user_or_platform_service),
    db: Session = Depends(get_db),
) -> AiRobotCallListResponse:
    query = _robot_call_query(db).filter(AiRobotCall.tenant_id == tenant_id_for(current_user))
    if current_user.role != "admin":
        query = query.filter(AiRobotCall.owner_id == current_user.id)
    if campaign_id:
        query = query.filter(AiRobotCall.campaign_id == campaign_id)
    if customer_id:
        query = query.filter(AiRobotCall.customer_id == customer_id)
    if status:
        query = query.filter(AiRobotCall.status == status)
    if high_intent is not None:
        query = query.filter(AiRobotCall.high_intent == high_intent)
    total = query.count()
    items = query.order_by(AiRobotCall.created_at.desc(), AiRobotCall.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return AiRobotCallListResponse(items=[_robot_call_out(item) for item in items], total=total, page=page, page_size=page_size)


@router.post("/ai-robot-calls/sync-pending", response_model=AiRobotSyncPendingResponse)
def sync_pending_ai_robot_calls(
    limit: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(require_admin_or_platform_service),
    db: Session = Depends(get_db),
) -> AiRobotSyncPendingResponse:
    synced_items, errors = sync_pending_ai_robot_call_batch(db, limit=limit, tenant_id=tenant_id_for(current_user))
    return AiRobotSyncPendingResponse(
        synced=len(synced_items),
        failed=len(errors),
        items=[_robot_call_out(item) for item in synced_items],
        errors=errors[:20],
    )


def sync_pending_ai_robot_call_batch(
    db: Session,
    *,
    limit: int = 20,
    tenant_id: int | None = None,
) -> tuple[list[AiRobotCall], list[str]]:
    robot_call_ids = _sync_candidate_robot_call_ids(db, limit=limit, tenant_id=tenant_id)
    synced_items: list[AiRobotCall] = []
    errors: list[str] = []

    for robot_call_id in robot_call_ids:
        robot_call = _robot_call_query(db).filter(AiRobotCall.id == robot_call_id).first()
        if robot_call is None:
            continue
        try:
            _sync_robot_call_from_provider(db, robot_call)
            db.commit()
            db.refresh(robot_call)
            synced_items.append(robot_call)
        except Exception as exc:
            db.rollback()
            errors.append(f"ai robot call {robot_call_id}: {exc}")

    return synced_items, errors


def _sync_candidate_robot_call_ids(db: Session, *, limit: int, tenant_id: int | None = None) -> list[int]:
    incomplete_recent_cutoff = datetime.now() - timedelta(minutes=SYNC_INCOMPLETE_TERMINAL_WINDOW_MINUTES)
    query = db.query(AiRobotCall.id)
    if tenant_id is not None:
        query = query.filter(AiRobotCall.tenant_id == tenant_id)
    query = query.filter(
        or_(
            AiRobotCall.status.notin_(ROBOT_TERMINAL_STATUSES),
            and_(
                AiRobotCall.status.in_(ROBOT_TERMINAL_STATUSES),
                AiRobotCall.updated_at >= incomplete_recent_cutoff,
                or_(AiRobotCall.recording_url.is_(None), AiRobotCall.transcript.is_(None)),
            ),
        )
    )
    return [
        row[0]
        for row in query.order_by(AiRobotCall.created_at.asc(), AiRobotCall.id.asc()).limit(limit).all()
    ]


@router.get("/ai-robot-calls/{robot_call_id}", response_model=AiRobotCallOut)
def get_ai_robot_call(
    robot_call_id: int,
    current_user: User = Depends(get_current_user_or_platform_service),
    db: Session = Depends(get_db),
) -> AiRobotCallOut:
    robot_call = _get_robot_call_for_user(db, robot_call_id, current_user)
    return _robot_call_out(robot_call)


@router.post("/ai-robot-calls/{robot_call_id}/sync", response_model=AiRobotCallOut)
def sync_ai_robot_call(
    robot_call_id: int,
    current_user: User = Depends(require_admin_or_platform_service),
    db: Session = Depends(get_db),
) -> AiRobotCallOut:
    robot_call = _get_robot_call_for_user(db, robot_call_id, current_user)
    _sync_robot_call_from_provider(db, robot_call)
    db.commit()
    db.refresh(robot_call)
    return _robot_call_out(robot_call)


@router.post("/ai-robot-calls/webhook/{provider}", response_model=AiRobotCallOut)
def receive_ai_robot_webhook(
    provider: str,
    payload: AiRobotWebhook,
    request: Request,
    db: Session = Depends(get_db),
) -> AiRobotCallOut:
    robot_call = (
        _robot_call_query(db)
        .filter(AiRobotCall.provider == provider)
        .filter(AiRobotCall.provider_call_id == payload.provider_call_id)
        .first()
    )
    if robot_call is None:
        verify_call_provider_webhook(request, db)
        db.add(
            AiRobotCallEvent(
                robot_call_id=None,
                provider=provider,
                provider_call_id=payload.provider_call_id,
                event_type=payload.event_type,
                payload_json=_json_dump(payload.model_dump()),
            )
        )
        db.commit()
        raise HTTPException(status_code=404, detail="ai robot call not found")

    verify_call_provider_webhook(request, db, robot_call.tenant_id)
    _record_robot_event(db, robot_call, payload)
    _apply_robot_event(db, robot_call, payload)
    db.commit()
    db.refresh(robot_call)
    return _robot_call_out(robot_call)


def _apply_robot_event(db: Session, robot_call: AiRobotCall, payload: AiRobotWebhook) -> None:
    status = _normalize_robot_status(payload.status or payload.event_type)
    if status not in ROBOT_STATUSES:
        raise HTTPException(status_code=400, detail="invalid ai robot call status")

    now = datetime.now()
    was_terminal = robot_call.status in ROBOT_TERMINAL_STATUSES
    robot_call.status = status
    robot_call.failure_reason = payload.failure_reason or robot_call.failure_reason
    robot_call.recording_url = payload.recording_url or robot_call.recording_url
    robot_call.transcript = (payload.transcript or robot_call.transcript or None)
    robot_call.duration_seconds = payload.duration_seconds if payload.duration_seconds is not None else robot_call.duration_seconds
    robot_call.updated_at = now

    attempt = robot_call.call_attempt
    if attempt:
        attempt.call_status = _attempt_status(status)
        attempt.duration_seconds = robot_call.duration_seconds
        attempt.transcript = robot_call.transcript or attempt.transcript
        attempt.updated_at = now

    if status == "answered":
        robot_call.answered_at = robot_call.answered_at or now
    if status in ROBOT_TERMINAL_STATUSES:
        robot_call.ended_at = robot_call.ended_at or now
        if attempt:
            attempt.ended_at = robot_call.ended_at
        if not was_terminal:
            _finish_target_from_robot(db, robot_call)
        if robot_call.recording_url and attempt:
            _ensure_robot_recording(db, robot_call, attempt)
        if robot_call.transcript and attempt:
            _analyze_robot_transcript(db, robot_call, attempt)
        _add_robot_followup(db, robot_call)
        if robot_call.campaign_id:
            _refresh_campaign_stats(db, robot_call.campaign_id)


def _finish_target_from_robot(db: Session, robot_call: AiRobotCall) -> None:
    target = robot_call.target
    if target is None:
        return
    target.call_count += 1
    target.last_attempt_id = robot_call.call_attempt_id
    target.last_called_at = robot_call.ended_at or robot_call.updated_at
    if robot_call.status == "completed":
        target.status = "callback" if robot_call.high_intent else "completed"
    elif robot_call.status in {"no_answer", "busy", "rejected", "empty_number", "failed"}:
        target.status = robot_call.status
    target.updated_at = datetime.now()


def _ensure_robot_recording(db: Session, robot_call: AiRobotCall, attempt: CallAttempt) -> None:
    if attempt.call_recording_id:
        return
    recording = CallRecording(
        tenant_id=robot_call.tenant_id,
        customer_id=robot_call.customer_id,
        sales_id=robot_call.owner_id,
        caller_phone=None,
        callee_phone=robot_call.phone,
        started_at=robot_call.answered_at or robot_call.started_at,
        ended_at=robot_call.ended_at,
        duration_seconds=robot_call.duration_seconds,
        recording_path=robot_call.recording_url or "",
        transcript=robot_call.transcript,
        transcription_status="completed" if robot_call.transcript else "pending",
    )
    db.add(recording)
    db.flush()
    attempt.call_recording_id = recording.id


def _analyze_robot_transcript(db: Session, robot_call: AiRobotCall, attempt: CallAttempt) -> None:
    upload = _ensure_robot_upload(db, robot_call, attempt)
    attempt.transcript = robot_call.transcript or attempt.transcript
    payload = AIService().analyze_text(attempt.transcript or "", "audio")
    existing = db.query(AIAnalysisResult).filter(AIAnalysisResult.upload_record_id == upload.id).first()
    if existing is not None:
        db.delete(existing)
        db.flush()
    customer = find_or_create_customer(
        db,
        owner_id=robot_call.owner_id,
        tenant_id=robot_call.tenant_id,
        customer_id=robot_call.customer_id,
        phone=_usable_text(payload.customer_phone) or robot_call.phone,
        name=payload.customer_name,
        wechat_id=payload.customer_wechat_id,
        wechat_nickname=payload.customer_wechat_nickname,
    )
    upload.customer_id = customer.id
    upload.status = "completed"
    upload.error_message = None
    robot_call.customer_id = customer.id
    attempt.customer_id = customer.id

    analysis = build_analysis_result(upload, payload)
    analysis.tenant_id = robot_call.tenant_id
    analysis.customer_id = customer.id
    _boost_robot_analysis_from_transcript(analysis, attempt.transcript or "")
    db.add(analysis)
    db.flush()

    update_customer_from_analysis(customer, analysis)
    robot_call.intent_level = analysis.intent_level
    robot_call.intent_score = analysis.intent_score
    robot_call.high_intent = _is_high_intent(analysis)
    attempt.ai_analysis_id = analysis.id
    attempt.intent_level = analysis.intent_level
    attempt.intent_score = analysis.intent_score
    attempt.next_action = analysis.next_action
    if robot_call.high_intent:
        customer.pipeline_stage = "qualified"
        customer.next_action = analysis.next_action or customer.next_action
    if robot_call.target:
        robot_call.target.status = "callback" if robot_call.high_intent else robot_call.target.status


def _ensure_robot_upload(db: Session, robot_call: AiRobotCall, attempt: CallAttempt) -> UploadRecord:
    if attempt.upload_record_id:
        upload = db.get(UploadRecord, attempt.upload_record_id)
        if upload is not None:
            return upload
    upload = UploadRecord(
        tenant_id=robot_call.tenant_id,
        customer_id=robot_call.customer_id,
        uploader_id=robot_call.owner_id,
        file_type="document",
        file_name=f"ai-robot-call-{robot_call.id}-transcript.txt",
        file_path=f"ai-robot-calls/ai-robot-call-{robot_call.id}.txt",
        status="processing",
    )
    db.add(upload)
    db.flush()
    attempt.upload_record_id = upload.id
    return upload


def _add_robot_followup(db: Session, robot_call: AiRobotCall) -> None:
    if not robot_call.customer_id or not robot_call.owner_id:
        return
    exists = (
        db.query(Followup.id)
        .filter(Followup.tenant_id == robot_call.tenant_id)
        .filter(Followup.customer_id == robot_call.customer_id)
        .filter(Followup.source == "ai_robot")
        .filter(Followup.created_at >= robot_call.started_at)
        .first()
    )
    if exists:
        return
    pieces = [
        f"AI机器人外呼：{_status_text(robot_call.status)}",
        f"客户电话：{_mask_phone(robot_call.phone)}",
    ]
    if robot_call.intent_score is not None:
        pieces.append(f"AI意向：{robot_call.intent_level or '-'} / {robot_call.intent_score}")
    if robot_call.high_intent:
        pieces.append("系统建议：高意向客户，销售应尽快一键回拨。")
    elif robot_call.status == "completed":
        pieces.append("系统建议：通话已完成，按AI摘要继续培育。")
    if robot_call.failure_reason:
        pieces.append(f"失败原因：{robot_call.failure_reason}")
    followup = Followup(
        tenant_id=robot_call.tenant_id,
        customer_id=robot_call.customer_id,
        user_id=robot_call.owner_id,
        content="\n".join(pieces),
        source="ai_robot",
        upload_record_id=robot_call.call_attempt.upload_record_id if robot_call.call_attempt else None,
        call_recording_id=robot_call.call_attempt.call_recording_id if robot_call.call_attempt else None,
        status="pending" if robot_call.high_intent else "completed",
        done_at=None if robot_call.high_intent else datetime.now(),
    )
    db.add(followup)
    customer = db.get(Customer, robot_call.customer_id)
    if customer:
        customer.last_followup_at = datetime.now()


def _record_robot_event(db: Session, robot_call: AiRobotCall, payload: AiRobotWebhook) -> None:
    db.add(
        AiRobotCallEvent(
            tenant_id=robot_call.tenant_id,
            robot_call_id=robot_call.id,
            provider=robot_call.provider,
            provider_call_id=robot_call.provider_call_id,
            event_type=payload.event_type,
            payload_json=_json_dump(payload.model_dump()),
        )
    )


def _sync_robot_call_from_provider(db: Session, robot_call: AiRobotCall) -> None:
    effective = get_effective_call_provider_settings(db, robot_call.tenant_id)
    provider = _provider_or_400(robot_call.provider, effective)
    try:
        sync_result = provider.sync_ai_robot_call(
            provider_call_id=robot_call.provider_call_id,
            raw_payload=_robot_raw_payload(robot_call),
        )
    except NotImplementedError as exc:
        raise HTTPException(status_code=400, detail=f"provider {robot_call.provider} does not support sync") from exc
    except CallProviderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    payload = AiRobotWebhook(
        provider_call_id=sync_result.provider_call_id,
        event_type="provider_sync",
        status=sync_result.status,
        duration_seconds=sync_result.duration_seconds,
        recording_url=sync_result.recording_url,
        transcript=sync_result.transcript,
        failure_reason=sync_result.failure_reason,
        raw_payload=sync_result.raw_payload,
    )
    _merge_robot_raw_payload(robot_call, sync_result.raw_payload)
    _record_robot_event(db, robot_call, payload)
    _apply_robot_event(db, robot_call, payload)


def _robot_raw_payload(robot_call: AiRobotCall) -> dict:
    if not robot_call.raw_payload_json:
        return {}
    try:
        value = json.loads(robot_call.raw_payload_json)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _merge_robot_raw_payload(robot_call: AiRobotCall, sync_payload: dict | None) -> None:
    if not sync_payload:
        return
    raw = _robot_raw_payload(robot_call)
    history = raw.get("sync_history")
    if not isinstance(history, list):
        history = []
    snapshot = {"synced_at": datetime.now().isoformat(timespec="seconds"), "payload": sync_payload}
    history.append(snapshot)
    raw["last_sync"] = snapshot
    raw["sync_history"] = history[-5:]
    robot_call.raw_payload_json = _json_dump(raw)


def _normalize_robot_status(value: str | None) -> str:
    event = (value or "").strip().lower()
    return {
        "robot_call_requested": "initiated",
        "callback_requested": "initiated",
        "initiated": "initiated",
        "ringing": "dialing",
        "dialing": "dialing",
        "answered": "answered",
        "connected": "answered",
        "bridged": "answered",
        "completed": "completed",
        "hangup": "completed",
        "no_answer": "no_answer",
        "busy": "busy",
        "rejected": "rejected",
        "empty_number": "empty_number",
        "failed": "failed",
        "cancelled": "failed",
        "canceled": "failed",
    }.get(event, event)


def _attempt_status(robot_status: str) -> str:
    if robot_status in {"initiated", "dialing"}:
        return "dialing"
    if robot_status in {"answered", "completed"}:
        return "connected"
    return robot_status


def _resolve_script_text(db: Session, campaign: CallCampaign, override: str | None) -> str:
    if override and override.strip():
        return override.strip()
    if campaign.script_id:
        script = db.get(Script, campaign.script_id)
        if script and script.tenant_id == campaign.tenant_id and script.content:
            return script.content.strip()
    return (
        "你是销售线索初筛AI机器人。先确认客户是否方便沟通，再简短说明来电目的，"
        "重点确认客户需求、预算、时间计划和是否愿意由销售顾问继续跟进。"
    )


def _provider_or_400(provider_name: str | None, effective=None):
    try:
        return get_call_provider(provider_name, effective)
    except CallProviderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _get_campaign_or_404(db: Session, campaign_id: int) -> CallCampaign:
    campaign = db.get(CallCampaign, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="campaign not found")
    return campaign


def _get_robot_call_for_user(db: Session, robot_call_id: int, user: User) -> AiRobotCall:
    robot_call = _robot_call_query(db).filter(AiRobotCall.id == robot_call_id).first()
    if robot_call is None:
        raise HTTPException(status_code=404, detail="ai robot call not found")
    assert_same_tenant(robot_call, user, not_found_detail="ai robot call not found")
    if user.role != "admin" and robot_call.owner_id != user.id:
        raise HTTPException(status_code=403, detail="permission denied")
    return robot_call


def _robot_call_query(db: Session):
    return db.query(AiRobotCall).options(
        joinedload(AiRobotCall.customer),
        joinedload(AiRobotCall.campaign),
        joinedload(AiRobotCall.target),
        joinedload(AiRobotCall.call_attempt),
    )


def _robot_call_out(robot_call: AiRobotCall) -> AiRobotCallOut:
    return AiRobotCallOut(
        id=robot_call.id,
        campaign_id=robot_call.campaign_id,
        target_id=robot_call.target_id,
        customer_id=robot_call.customer_id,
        owner_id=robot_call.owner_id,
        call_attempt_id=robot_call.call_attempt_id,
        provider=robot_call.provider,
        provider_call_id=robot_call.provider_call_id,
        phone=robot_call.phone,
        status=robot_call.status,
        failure_reason=robot_call.failure_reason,
        recording_url=robot_call.recording_url,
        transcript=robot_call.transcript,
        intent_level=robot_call.intent_level,
        intent_score=robot_call.intent_score,
        high_intent=robot_call.high_intent,
        started_at=robot_call.started_at,
        answered_at=robot_call.answered_at,
        ended_at=robot_call.ended_at,
        duration_seconds=robot_call.duration_seconds,
        created_at=robot_call.created_at,
        updated_at=robot_call.updated_at,
        customer_name=robot_call.customer.name if robot_call.customer else None,
        campaign_name=robot_call.campaign.name if robot_call.campaign else None,
        target_status=robot_call.target.status if robot_call.target else None,
        call_status=robot_call.call_attempt.call_status if robot_call.call_attempt else None,
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


def _boost_robot_analysis_from_transcript(analysis: AIAnalysisResult, transcript: str) -> None:
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
    analysis.summary = analysis.summary or "\u5ba2\u6237\u5728AI\u673a\u5668\u4eba\u5916\u547c\u4e2d\u51fa\u73b0\u660e\u786e\u8d2d\u4e70\u4fe1\u53f7\u3002"
    analysis.customer_needs = analysis.customer_needs or "\u5ba2\u6237\u5173\u6ce8\u62a5\u4ef7\u3001\u5408\u540c\u3001\u4ed8\u6b3e\u6216\u90e8\u7f72\u5b89\u6392\u3002"
    analysis.intent_reason = "\u673a\u5668\u4eba\u901a\u8bdd\u547d\u4e2d\u9ad8\u610f\u5411\u5173\u952e\u8bcd\uff1a" + "\u3001".join(matched)
    analysis.evidence = "\u3001".join(matched)
    analysis.next_action = analysis.next_action or "\u5efa\u8bae\u9500\u552e\u5c3d\u5feb\u4e00\u952e\u56de\u62e8\uff0c\u786e\u8ba4\u62a5\u4ef7\u3001\u5408\u540c\u3001\u4ed8\u6b3e\u4e0e\u90e8\u7f72\u65f6\u95f4\u3002"
    analysis.sales_script = analysis.sales_script or "\u6211\u770b\u5230\u60a8\u5df2\u7ecf\u5173\u6ce8\u5230\u62a5\u4ef7\u548c\u90e8\u7f72\u5b89\u6392\uff0c\u6211\u5148\u5e2e\u60a8\u628a\u65b9\u6848\u548c\u5408\u540c\u8981\u70b9\u786e\u8ba4\u4e00\u4e0b\u3002"


def _is_high_intent(analysis: AIAnalysisResult) -> bool:
    return (analysis.intent_score or 0) >= 80 or analysis.intent_level == "\u9ad8\u610f\u5411"


def _usable_text(value: str | None) -> str | None:
    if not value:
        return None
    text = value.strip()
    if not text:
        return None
    if "?" in text or "\ufffd" in text:
        return None
    return text


def _normalize_phone(value: str | None) -> str | None:
    if not value:
        return None
    digits = re.sub(r"\D", "", value)
    if len(digits) == 13 and digits.startswith("86"):
        digits = digits[2:]
    return digits or None


def _mask_phone(phone: str | None) -> str:
    if not phone:
        return "-"
    if len(phone) < 7:
        return phone
    return f"{phone[:3]}****{phone[-4:]}"


def _status_text(status: str | None) -> str:
    return {
        "initiated": "已提交",
        "dialing": "拨打中",
        "answered": "已接通",
        "completed": "已完成",
        "no_answer": "未接通",
        "busy": "忙线",
        "rejected": "拒接",
        "empty_number": "空号",
        "failed": "失败",
    }.get(status or "", status or "-")


def _json_dump(value) -> str:
    return json.dumps(value or {}, ensure_ascii=False, default=str)
