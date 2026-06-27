from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, or_, true
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_current_user, require_admin
from app.core.database import get_db
from app.core.security import now_local
from app.models.analysis import AIAnalysisResult
from app.models.call_recording import CallRecording
from app.models.customer import Customer
from app.models.followup import Followup
from app.models.upload import UploadRecord
from app.models.user import User
from app.schemas.customer import CustomerCreate, CustomerListResponse, CustomerOut, CustomerUpdate
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
    query = db.query(Customer).options(joinedload(Customer.owner))
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
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Customer:
    lead_status = payload.lead_status or ("assigned" if payload.owner_id else "unassigned")
    if lead_status not in {"unassigned", "assigned"}:
        raise HTTPException(status_code=400, detail="线索状态只能是 unassigned 或 assigned")
    if payload.owner_id:
        owner = db.get(User, payload.owner_id)
        if owner is None or owner.status != "active":
            raise HTTPException(status_code=404, detail="销售账号不存在或已停用")
    customer = Customer(
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
        owner = db.get(User, updates["owner_id"])
        if owner is None or owner.status != "active":
            raise HTTPException(status_code=404, detail="销售账号不存在或已停用")
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
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Customer:
    customer = db.get(Customer, customer_id)
    if customer is None:
        raise HTTPException(status_code=404, detail="客户不存在")
    if not payload.owner_id:
        raise HTTPException(status_code=400, detail="请选择要分配的销售")
    owner = db.get(User, payload.owner_id)
    if owner is None or owner.status != "active":
        raise HTTPException(status_code=404, detail="销售账号不存在或已停用")
    customer.owner_id = owner.id
    customer.lead_status = "assigned"
    customer.assigned_at = now_local()
    customer.updated_at = datetime.now()
    db.commit()
    db.refresh(customer)
    return customer


@router.delete("/{customer_id}")
def delete_customer(
    customer_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    customer = _get_customer_for_user(db, customer_id, current_user)
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


def _get_customer_for_user(db: Session, customer_id: int, current_user: User) -> Customer:
    customer = db.get(Customer, customer_id)
    if customer is None:
        raise HTTPException(status_code=404, detail="客户不存在")
    if current_user.role != "admin" and customer.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权查看该客户")
    return customer


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


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
