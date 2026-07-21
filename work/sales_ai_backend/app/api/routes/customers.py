from datetime import datetime
from random import shuffle

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, or_, true
from sqlalchemy.orm import Session, joinedload

from app.api.deps import assert_same_tenant, assert_user_same_tenant, get_current_user, require_admin, tenant_id_for
from app.core.database import get_db
from app.core.security import now_local
from app.models.analysis import AIAnalysisResult
from app.models.call_attempt import CallAttempt
from app.models.call_campaign_target import CallCampaignTarget
from app.models.call_recording import CallRecording
from app.models.customer import Customer
from app.models.followup import Followup
from app.models.upload import UploadRecord
from app.models.user import User
from app.schemas.customer import (
    CustomerCreate,
    CustomerDuplicateGroup,
    CustomerDuplicateResponse,
    CustomerListResponse,
    CustomerMergeRequest,
    CustomerOut,
    CustomerRandomAssignItem,
    CustomerRandomAssignRequest,
    CustomerRandomAssignResponse,
    CustomerUpdate,
)
from app.schemas.followup import FollowupCreate, FollowupOut
from app.schemas.upload import UploadOut

router = APIRouter()


@router.get("", response_model=CustomerListResponse)
def list_customers(
    keyword: str | None = None,
    owner_id: int | None = None,
    intent_level: str | None = None,
    lead_status: str | None = None,
    lead_source: str | None = None,
    pipeline_stage: str | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CustomerListResponse:
    query = db.query(Customer).options(joinedload(Customer.owner)).filter(Customer.tenant_id == tenant_id_for(current_user))
    if current_user.role != "admin":
        query = query.filter(Customer.owner_id == current_user.id)
    elif owner_id:
        query = query.filter(Customer.owner_id == owner_id)
    if lead_status:
        query = query.filter(Customer.lead_status == lead_status)
    if lead_source:
        query = query.filter(Customer.lead_source == lead_source)
    if pipeline_stage:
        query = query.filter(Customer.pipeline_stage == pipeline_stage)
    if keyword:
        keyword_groups = _keyword_groups(keyword)
        searchable_columns = (
            Customer.name,
            Customer.phone,
            Customer.wechat_id,
            Customer.wechat_nickname,
            Customer.demand_summary,
            Customer.concerns,
            Customer.product_interest,
            Customer.next_action,
            UploadRecord.file_name,
            AIAnalysisResult.raw_text,
            AIAnalysisResult.summary,
            AIAnalysisResult.customer_name,
            AIAnalysisResult.customer_wechat_id,
            AIAnalysisResult.customer_wechat_nickname,
            AIAnalysisResult.customer_needs,
            AIAnalysisResult.evidence,
        )
        query = (
            query.outerjoin(UploadRecord, UploadRecord.customer_id == Customer.id)
            .outerjoin(AIAnalysisResult, AIAnalysisResult.customer_id == Customer.id)
            .filter(_search_filter(searchable_columns, keyword_groups))
            .distinct()
        )
    if intent_level:
        query = query.filter(Customer.intent_level == intent_level)
    if start_date:
        query = query.filter(Customer.created_at >= start_date)
    if end_date:
        query = query.filter(Customer.created_at <= end_date)
    total = query.count()
    items = (
        query.order_by(Customer.intent_score.desc(), Customer.updated_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return CustomerListResponse(items=items, total=total, page=page, page_size=page_size)


@router.post("", response_model=CustomerOut)
def create_customer(
    payload: CustomerCreate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Customer:
    lead_status = payload.lead_status or ("assigned" if payload.owner_id else "unassigned")
    if lead_status not in {"unassigned", "assigned"}:
        raise HTTPException(status_code=400, detail="线索状态只能是 unassigned 或 assigned")
    if payload.owner_id:
        assert_user_same_tenant(db.get(User, payload.owner_id), current_user, detail="销售账号不存在或已停用")
    customer = Customer(
        tenant_id=tenant_id_for(current_user),
        owner_id=payload.owner_id,
        name=_clean(payload.name),
        wechat_id=_clean(payload.wechat_id),
        wechat_nickname=_clean(payload.wechat_nickname),
        phone=_clean(payload.phone),
        address=_clean(payload.address),
        source=_clean(payload.source) or _clean(payload.lead_source) or "外部线索",
        lead_source=_clean(payload.lead_source) or _clean(payload.source) or "外部线索",
        lead_status=lead_status,
        demand_summary=_clean(payload.demand_summary),
        next_action=_clean(payload.next_action) or "等待管理员分配销售跟进",
    )
    db.add(customer)
    db.commit()
    db.refresh(customer)
    return customer


@router.get("/duplicates", response_model=CustomerDuplicateResponse)
def list_duplicate_customers(
    limit: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> CustomerDuplicateResponse:
    customers = db.query(Customer).options(joinedload(Customer.owner)).filter(Customer.tenant_id == tenant_id_for(current_user)).all()
    groups: list[CustomerDuplicateGroup] = []
    fields = (
        ("phone", "手机号相同"),
        ("wechat_id", "微信号相同"),
        ("wechat_nickname", "微信昵称相同"),
        ("name", "客户姓名相同"),
    )
    for field, reason in fields:
        buckets: dict[str, list[Customer]] = {}
        for customer in customers:
            value = _duplicate_key(getattr(customer, field))
            if value:
                buckets.setdefault(value, []).append(customer)
        for value, matched in buckets.items():
            if len(matched) > 1:
                groups.append(
                    CustomerDuplicateGroup(
                        reason=reason,
                        match_value=value,
                        customers=sorted(matched, key=lambda item: (item.intent_score or 0, item.updated_at), reverse=True),
                    )
                )
    groups.sort(key=lambda group: (len(group.customers), max(customer.intent_score or 0 for customer in group.customers)), reverse=True)
    return CustomerDuplicateResponse(items=groups[:limit], total=len(groups))


@router.post("/deduplicate")
def deduplicate_customers(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict[str, int | str]:
    merged_count = 0
    for field in ("phone", "wechat_id"):
        customers = db.query(Customer).options(joinedload(Customer.owner)).filter(Customer.tenant_id == tenant_id_for(current_user)).all()
        buckets: dict[str, list[Customer]] = {}
        for customer in customers:
            value = _duplicate_key(getattr(customer, field))
            if value:
                buckets.setdefault(value, []).append(customer)

        for matched in buckets.values():
            if len(matched) <= 1:
                continue
            target = sorted(matched, key=lambda item: (item.intent_score or 0, item.updated_at, item.id), reverse=True)[0]
            for source in matched:
                if source.id == target.id:
                    continue
                _merge_customer_profile(target, source)
                _move_customer_relations(db, target, source)
                db.delete(source)
                merged_count += 1
            target.updated_at = datetime.now()
            db.flush()

    db.commit()
    return {"message": "duplicate customers merged", "merged_count": merged_count}


@router.post("/assign-random", response_model=CustomerRandomAssignResponse)
def assign_unassigned_customers_randomly(
    payload: CustomerRandomAssignRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> CustomerRandomAssignResponse:
    current_tenant_id = tenant_id_for(current_user)
    sales_query = db.query(User).filter(User.tenant_id == current_tenant_id, User.role == "sales", User.status == "active")
    if payload.sales_user_ids:
        sales_query = sales_query.filter(User.id.in_(payload.sales_user_ids))
    sales_users = sales_query.order_by(User.id.asc()).all()
    if not sales_users:
        raise HTTPException(status_code=400, detail="没有可分配的启用销售账号")

    customer_query = (
        db.query(Customer)
        .filter(Customer.tenant_id == current_tenant_id)
        .filter(Customer.lead_status == "unassigned")
        .order_by(Customer.intent_score.desc(), Customer.updated_at.desc(), Customer.id.asc())
    )
    if payload.limit:
        customer_query = customer_query.limit(payload.limit)
    customers = customer_query.all()
    if not customers:
        return CustomerRandomAssignResponse(
            assigned_count=0,
            sales_count=len(sales_users),
            remaining_unassigned=_unassigned_customer_count(db, current_tenant_id),
            items=[
                CustomerRandomAssignItem(sales_id=user.id, sales_name=user.name, assigned_count=0)
                for user in sales_users
            ],
        )

    shuffled_sales = list(sales_users)
    shuffle(shuffled_sales)
    counts = {user.id: 0 for user in shuffled_sales}
    now = now_local()

    for index, customer in enumerate(customers):
        owner = shuffled_sales[index % len(shuffled_sales)]
        customer.owner_id = owner.id
        customer.lead_status = "assigned"
        customer.assigned_at = now
        customer.updated_at = now
        counts[owner.id] += 1

    db.commit()
    return CustomerRandomAssignResponse(
        assigned_count=len(customers),
        sales_count=len(sales_users),
        remaining_unassigned=_unassigned_customer_count(db, current_tenant_id),
        items=[
            CustomerRandomAssignItem(sales_id=user.id, sales_name=user.name, assigned_count=counts.get(user.id, 0))
            for user in sales_users
        ],
    )


@router.post("/{customer_id}/merge", response_model=CustomerOut)
def merge_customer(
    customer_id: int,
    payload: CustomerMergeRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Customer:
    target = db.get(Customer, customer_id)
    source = db.get(Customer, payload.source_customer_id)
    assert_same_tenant(target, current_user, not_found_detail="客户不存在")
    assert_same_tenant(source, current_user, not_found_detail="客户不存在")
    if target is None or source is None:
        raise HTTPException(status_code=404, detail="客户不存在")
    if target.id == source.id:
        raise HTTPException(status_code=400, detail="不能合并同一个客户")

    _merge_customer_profile(target, source)
    _move_customer_relations(db, target, source)
    db.delete(source)
    target.updated_at = datetime.now()
    db.commit()
    db.refresh(target)
    return target


@router.get("/{customer_id}", response_model=CustomerOut)
def get_customer(
    customer_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Customer:
    customer = _get_customer_for_user(db, customer_id, current_user)
    return customer


@router.patch("/{customer_id}", response_model=CustomerOut)
def update_customer(
    customer_id: int,
    payload: CustomerUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Customer:
    customer = _get_customer_for_user(db, customer_id, current_user)
    updates = payload.model_dump(exclude_unset=True)
    if current_user.role != "admin":
        updates.pop("owner_id", None)
        updates.pop("lead_status", None)
        updates.pop("lead_source", None)
        updates.pop("source", None)
    if "owner_id" in updates and updates["owner_id"]:
        assert_user_same_tenant(db.get(User, updates["owner_id"]), current_user, detail="销售账号不存在或已停用")
        updates["lead_status"] = "assigned"
        updates["assigned_at"] = now_local()
    if updates.get("lead_status") not in (None, "unassigned", "assigned"):
        raise HTTPException(status_code=400, detail="线索状态只能是 unassigned 或 assigned")
    if "pipeline_stage" in updates and updates["pipeline_stage"] not in (None, "lead", "followup", "negotiation", "closed_won", "closed_lost"):
        raise HTTPException(status_code=400, detail="阶段只能是 lead/followup/negotiation/closed_won/closed_lost")
    for field, value in updates.items():
        if isinstance(value, str):
            value = value.strip() or None
        setattr(customer, field, value)
    customer.updated_at = datetime.now()
    db.commit()
    db.refresh(customer)
    return customer


@router.post("/{customer_id}/assign", response_model=CustomerOut)
def assign_customer(
    customer_id: int,
    payload: CustomerUpdate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Customer:
    customer = db.get(Customer, customer_id)
    previous_owner_id = customer.owner_id if customer is not None else None
    assert_same_tenant(customer, current_user, not_found_detail="客户不存在")
    if customer is None:
        raise HTTPException(status_code=404, detail="客户不存在")
    if not payload.owner_id:
        raise HTTPException(status_code=400, detail="请选择要分配的销售")
    owner = assert_user_same_tenant(db.get(User, payload.owner_id), current_user, detail="销售账号不存在或已停用")
    assigned_at = now_local()
    customer.owner_id = owner.id
    customer.lead_status = "assigned"
    customer.assigned_at = assigned_at
    customer.last_followup_at = assigned_at
    customer.updated_at = datetime.now()
    db.add(
        Followup(
            tenant_id=tenant_id_for(current_user),
            customer_id=customer.id,
            user_id=current_user.id,
            content=f"{'调整销售' if previous_owner_id else '分配销售'}：{owner.name or owner.username}",
            source="assignment",
            status="completed",
            done_at=assigned_at,
        )
    )
    db.commit()
    db.refresh(customer)
    return customer


@router.delete("/{customer_id}")
def delete_customer(
    customer_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    customer = db.get(Customer, customer_id)
    assert_same_tenant(customer, current_user, not_found_detail="客户不存在")
    if customer is None:
        raise HTTPException(status_code=404, detail="客户不存在")
    upload_ids = [
        row[0]
        for row in db.query(UploadRecord.id).filter(UploadRecord.customer_id == customer.id).all()
    ]
    recording_ids = [
        row[0]
        for row in db.query(CallRecording.id).filter(CallRecording.customer_id == customer.id).all()
    ]

    db.query(Followup).filter(Followup.customer_id == customer.id).delete(synchronize_session=False)
    if upload_ids:
        db.query(Followup).filter(Followup.upload_record_id.in_(upload_ids)).delete(synchronize_session=False)
        db.query(AIAnalysisResult).filter(AIAnalysisResult.upload_record_id.in_(upload_ids)).delete(synchronize_session=False)
    if recording_ids:
        db.query(Followup).filter(Followup.call_recording_id.in_(recording_ids)).delete(synchronize_session=False)
    db.query(CallRecording).filter(CallRecording.customer_id == customer.id).delete(synchronize_session=False)
    db.query(UploadRecord).filter(UploadRecord.customer_id == customer.id).delete(synchronize_session=False)
    db.delete(customer)
    db.commit()
    return {"message": "客户已删除"}


@router.get("/{customer_id}/records", response_model=list[UploadOut])
def get_customer_records(
    customer_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[UploadRecord]:
    _get_customer_for_user(db, customer_id, current_user)
    return (
        db.query(UploadRecord)
        .options(joinedload(UploadRecord.analysis), joinedload(UploadRecord.uploader))
        .filter(UploadRecord.tenant_id == tenant_id_for(current_user))
        .filter(UploadRecord.customer_id == customer_id)
        .order_by(UploadRecord.created_at.desc())
        .all()
    )


@router.post("/{customer_id}/followups", response_model=FollowupOut)
def create_followup(
    customer_id: int,
    payload: FollowupCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Followup:
    customer = _get_customer_for_user(db, customer_id, current_user)
    followup = Followup(
        tenant_id=tenant_id_for(current_user),
        customer_id=customer_id,
        user_id=current_user.id,
        content=payload.content,
        source="manual_note",
        next_followup_at=payload.next_followup_at,
    )
    customer.last_followup_at = datetime.now()
    db.add(followup)
    db.commit()
    db.refresh(followup)
    return followup


@router.get("/{customer_id}/followups", response_model=list[FollowupOut])
def list_followups(
    customer_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[Followup]:
    _get_customer_for_user(db, customer_id, current_user)
    return (
        db.query(Followup)
        .filter(Followup.tenant_id == tenant_id_for(current_user))
        .filter(Followup.customer_id == customer_id)
        .order_by(Followup.created_at.desc(), Followup.id.desc())
        .all()
    )


@router.patch("/followups/{followup_id}/status")
def update_followup_status(
    followup_id: int,
    payload: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    followup = db.get(Followup, followup_id)
    if followup is None:
        raise HTTPException(status_code=404, detail="跟进记录不存在")
    assert_same_tenant(followup, current_user, not_found_detail="跟进记录不存在")
    if current_user.role != "admin" and followup.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权操作该跟进记录")
    new_status = payload.get("status")
    allowed = {"pending", "contacted", "meeting", "completed"}
    if new_status not in allowed:
        raise HTTPException(status_code=400, detail=f"状态必须是 {allowed}")
    followup.status = new_status
    if new_status == "completed":
        followup.done_at = now_local()
    else:
        followup.done_at = None
    db.commit()
    return {"message": f"跟进状态已更新", "status": followup.status}


def _unassigned_customer_count(db: Session, tenant_id: int) -> int:
    return db.query(Customer).filter(Customer.tenant_id == tenant_id, Customer.lead_status == "unassigned").count()


def _get_customer_for_user(db: Session, customer_id: int, current_user: User) -> Customer:
    customer = db.get(Customer, customer_id)
    if customer is None:
        raise HTTPException(status_code=404, detail="客户不存在")
    assert_same_tenant(customer, current_user, not_found_detail="客户不存在")
    if current_user.role != "admin" and customer.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权查看该客户")
    return customer


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def _duplicate_key(value: str | None) -> str | None:
    cleaned = _clean(value)
    if cleaned in (None, "未提及", "无法判断", "未知"):
        return None
    return cleaned.lower().replace(" ", "")


def _merge_customer_profile(target: Customer, source: Customer) -> None:
    copy_if_missing_fields = (
        "owner_id",
        "name",
        "wechat_id",
        "wechat_nickname",
        "phone",
        "address",
        "source",
        "lead_source",
        "lead_status",
        "pipeline_stage",
        "demand_summary",
        "concerns",
        "product_interest",
        "budget",
        "purchase_time",
        "next_action",
    )
    for field in copy_if_missing_fields:
        if _has_meaningful_value(getattr(target, field)):
            continue
        value = getattr(source, field)
        if _has_meaningful_value(value):
            setattr(target, field, value)

    if (source.intent_score or 0) > (target.intent_score or 0):
        target.intent_level = source.intent_level
        target.intent_score = source.intent_score
        for field in ("demand_summary", "concerns", "product_interest", "budget", "purchase_time", "next_action"):
            value = getattr(source, field)
            if _clean(value):
                setattr(target, field, value)

    if source.last_followup_at and (not target.last_followup_at or source.last_followup_at > target.last_followup_at):
        target.last_followup_at = source.last_followup_at
    if source.assigned_at and (not target.assigned_at or source.assigned_at > target.assigned_at):
        target.assigned_at = source.assigned_at


def _move_customer_relations(db: Session, target: Customer, source: Customer) -> None:
    db.query(UploadRecord).filter(UploadRecord.customer_id == source.id).update(
        {"customer_id": target.id}, synchronize_session=False
    )
    db.query(AIAnalysisResult).filter(AIAnalysisResult.customer_id == source.id).update(
        {"customer_id": target.id}, synchronize_session=False
    )
    db.query(Followup).filter(Followup.customer_id == source.id).update(
        {"customer_id": target.id}, synchronize_session=False
    )
    db.query(CallRecording).filter(CallRecording.customer_id == source.id).update(
        {"customer_id": target.id}, synchronize_session=False
    )
    db.query(CallAttempt).filter(CallAttempt.customer_id == source.id).update(
        {"customer_id": target.id}, synchronize_session=False
    )

    source_targets = db.query(CallCampaignTarget).filter(CallCampaignTarget.customer_id == source.id).all()
    for source_target in source_targets:
        existing = (
            db.query(CallCampaignTarget)
            .filter(CallCampaignTarget.campaign_id == source_target.campaign_id)
            .filter(CallCampaignTarget.customer_id == target.id)
            .first()
        )
        if existing:
            db.query(CallAttempt).filter(CallAttempt.target_id == source_target.id).update(
                {"target_id": existing.id}, synchronize_session=False
            )
            _merge_call_target(existing, source_target)
            db.delete(source_target)
        else:
            source_target.customer_id = target.id
            if not _clean(source_target.phone):
                source_target.phone = target.phone
            if not _clean(source_target.contact_name):
                source_target.contact_name = target.name or target.wechat_nickname


def _merge_call_target(target: CallCampaignTarget, source: CallCampaignTarget) -> None:
    target.call_count = max(target.call_count or 0, source.call_count or 0)
    if source.status != "pending" and target.status == "pending":
        target.status = source.status
    if source.last_called_at and (not target.last_called_at or source.last_called_at > target.last_called_at):
        target.last_called_at = source.last_called_at
        target.last_attempt_id = source.last_attempt_id
    if source.next_followup_at and (not target.next_followup_at or source.next_followup_at < target.next_followup_at):
        target.next_followup_at = source.next_followup_at
    if not target.assigned_user_id and source.assigned_user_id:
        target.assigned_user_id = source.assigned_user_id
    target.updated_at = datetime.now()


def _has_meaningful_value(value) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return _clean(value) not in (None, "未提及", "无法判断", "未知")
    return True


def _keyword_groups(keyword: str) -> list[list[str]]:
    groups: list[list[str]] = []
    for group in keyword.split():
        alternatives = [
            item.strip()
            for separator_group in group.split("|")
            for item in separator_group.split(",")
            if item.strip()
        ]
        if alternatives:
            groups.append(alternatives)
    return groups


def _search_filter(columns, groups: list[list[str]]):
    filters = []
    for alternatives in groups:
        filters.append(
            or_(
                *(
                    column.like(f"%{item}%")
                    for item in alternatives
                    for column in columns
                )
            )
        )
    return and_(*filters) if filters else true()
