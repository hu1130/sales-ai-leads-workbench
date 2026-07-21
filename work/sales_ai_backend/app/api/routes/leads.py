from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_current_user, tenant_id_for
from app.core.database import get_db
from app.models.customer import Customer
from app.models.user import User
from app.schemas.customer import CustomerListResponse

router = APIRouter()


@router.get("", response_model=CustomerListResponse)
@router.get("/", response_model=CustomerListResponse, include_in_schema=False)
def intent_leads(
    intent_level: str = Query(default="高意向"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CustomerListResponse:
    if intent_level not in {"高意向", "中意向", "低意向", "暂无意向", "无法判断"}:
        raise HTTPException(status_code=400, detail="意向等级不正确")

    query = db.query(Customer).options(joinedload(Customer.owner)).filter(Customer.tenant_id == tenant_id_for(current_user), Customer.intent_level == intent_level)
    if current_user.role != "admin":
        query = query.filter(Customer.owner_id == current_user.id)
    total = query.count()
    items = (
        query.order_by(Customer.intent_score.desc(), Customer.updated_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return CustomerListResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/high-intent", response_model=CustomerListResponse)
def high_intent_leads(
    min_score: int = Query(default=80, ge=0, le=100),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CustomerListResponse:
    query = (
        db.query(Customer)
        .options(joinedload(Customer.owner))
        .filter(Customer.tenant_id == tenant_id_for(current_user))
        .filter((Customer.intent_level == "高意向") | (Customer.intent_score >= min_score))
    )
    if current_user.role != "admin":
        query = query.filter(Customer.owner_id == current_user.id)
    total = query.count()
    items = (
        query.order_by(Customer.intent_score.desc(), Customer.updated_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return CustomerListResponse(items=items, total=total, page=page, page_size=page_size)
