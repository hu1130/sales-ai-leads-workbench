from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.customer import Customer
from app.models.followup import Followup
from app.models.upload import UploadRecord
from app.models.user import User
from app.schemas.customer import CustomerListResponse, CustomerOut
from app.schemas.followup import FollowupCreate, FollowupOut
from app.schemas.upload import UploadOut

router = APIRouter()


@router.get("", response_model=CustomerListResponse)
def list_customers(
    keyword: str | None = None,
    owner_id: int | None = None,
    intent_level: str | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CustomerListResponse:
    query = db.query(Customer)
    if current_user.role != "admin":
        query = query.filter(Customer.owner_id == current_user.id)
    elif owner_id:
        query = query.filter(Customer.owner_id == owner_id)
    if keyword:
        like = f"%{keyword}%"
        query = query.filter(or_(Customer.name.like(like), Customer.phone.like(like)))
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


@router.get("/{customer_id}", response_model=CustomerOut)
def get_customer(
    customer_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Customer:
    customer = _get_customer_for_user(db, customer_id, current_user)
    return customer


@router.get("/{customer_id}/records", response_model=list[UploadOut])
def get_customer_records(
    customer_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[UploadRecord]:
    _get_customer_for_user(db, customer_id, current_user)
    return (
        db.query(UploadRecord)
        .options(joinedload(UploadRecord.analysis))
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
        .order_by(Followup.created_at.desc())
        .all()
    )


def _get_customer_for_user(db: Session, customer_id: int, current_user: User) -> Customer:
    customer = db.get(Customer, customer_id)
    if customer is None:
        raise HTTPException(status_code=404, detail="客户不存在")
    if current_user.role != "admin" and customer.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权查看该客户")
    return customer
