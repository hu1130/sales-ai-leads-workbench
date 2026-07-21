import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import assert_same_tenant, get_current_user, tenant_id_for
from app.core.database import get_db
from app.core.security import now_local
from app.models.customer import Customer
from app.models.quotation import Quotation
from app.models.user import User
from app.schemas.quotation import QuotationCreate, QuotationStatusUpdate

router = APIRouter()

VALID_STATUSES = {"draft", "sent", "accepted", "rejected"}


@router.get("/{customer_id}")
def list_quotations(
    customer_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    customer = db.get(Customer, customer_id)
    assert_same_tenant(customer, current_user, not_found_detail="customer not found")
    if current_user.role != "admin" and customer.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="permission denied")
    quotations = (
        db.query(Quotation)
        .filter(Quotation.tenant_id == tenant_id_for(current_user))
        .filter(Quotation.customer_id == customer_id)
        .order_by(Quotation.created_at.desc())
        .all()
    )
    return [_q_to_dict(q) for q in quotations]


@router.post("/{customer_id}")
def create_quotation(
    customer_id: int,
    payload: QuotationCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    customer = db.get(Customer, customer_id)
    assert_same_tenant(customer, current_user, not_found_detail="customer not found")
    if current_user.role != "admin" and customer.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="permission denied")

    items = [item.model_dump() for item in payload.items]
    total = sum(item["qty"] * item["unit_price"] for item in items)

    q = Quotation(
        tenant_id=tenant_id_for(current_user),
        customer_id=customer_id,
        user_id=current_user.id,
        title=payload.title,
        items=json.dumps(items, ensure_ascii=False),
        total_amount=round(total, 2),
        notes=payload.notes,
        status="draft",
    )
    db.add(q)
    db.commit()
    db.refresh(q)
    return _q_to_dict(q)


@router.patch("/{quotation_id}/status")
def update_quotation_status(
    quotation_id: int,
    payload: QuotationStatusUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    q = db.get(Quotation, quotation_id)
    assert_same_tenant(q, current_user, not_found_detail="quotation not found")
    if current_user.role != "admin" and q.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="permission denied")

    new_status = payload.status
    if new_status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"status must be one of {sorted(VALID_STATUSES)}")
    q.status = new_status
    if new_status == "sent":
        q.sent_at = now_local()
    db.commit()
    db.refresh(q)
    return _q_to_dict(q)


def _q_to_dict(q: Quotation) -> dict:
    return {
        "id": q.id,
        "customer_id": q.customer_id,
        "user_id": q.user_id,
        "title": q.title,
        "items": json.loads(q.items) if isinstance(q.items, str) else q.items,
        "total_amount": q.total_amount,
        "notes": q.notes,
        "status": q.status,
        "sent_at": q.sent_at.isoformat() if q.sent_at else None,
        "created_at": q.created_at.isoformat() if q.created_at else None,
        "updated_at": q.updated_at.isoformat() if q.updated_at else None,
    }
