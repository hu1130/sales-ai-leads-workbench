from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_admin
from app.core.database import get_db
from app.models.customer import Customer
from app.models.followup import Followup
from app.models.upload import UploadRecord
from app.models.user import User

router = APIRouter()


@router.get("/stats")
def dashboard_stats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    customer_query = db.query(Customer)
    upload_query = db.query(UploadRecord)
    if current_user.role != "admin":
        customer_query = customer_query.filter(Customer.owner_id == current_user.id)
        upload_query = upload_query.filter(UploadRecord.uploader_id == current_user.id)
    total_customers = customer_query.count()
    total_uploads = upload_query.count()
    high_intent_customers = (
        customer_query
        .filter((Customer.intent_level == "高意向") | (Customer.intent_score >= 80))
        .count()
    )
    intent_rows = (
        db.query(Customer.intent_level, func.count(Customer.id))
        .filter(Customer.owner_id == current_user.id if current_user.role != "admin" else True)
        .group_by(Customer.intent_level)
        .all()
    )
    sales_upload_rows = []
    if current_user.role == "admin":
        sales_upload_rows = (
            db.query(UploadRecord.uploader_id, func.count(UploadRecord.id))
            .group_by(UploadRecord.uploader_id)
            .all()
        )
    return {
        "total_customers": total_customers,
        "total_uploads": total_uploads,
        "high_intent_customers": high_intent_customers,
        "intent_distribution": {level: count for level, count in intent_rows},
        "sales_upload_distribution": {str(user_id): count for user_id, count in sales_upload_rows},
    }


@router.get("/high-intent")
def high_intent_customers(
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[dict]:
    customers = (
        db.query(Customer)
        .filter((Customer.intent_level == "高意向") | (Customer.intent_score >= 80))
        .order_by(Customer.intent_score.desc(), Customer.updated_at.desc())
        .limit(100)
        .all()
    )
    return [
        {
            "id": customer.id,
            "name": customer.name,
            "phone": customer.phone,
            "intent_level": customer.intent_level,
            "intent_score": customer.intent_score,
            "demand_summary": customer.demand_summary,
            "next_action": customer.next_action,
        }
        for customer in customers
    ]


@router.get("/followup-priorities")
def followup_priorities(
    limit: int = Query(default=8, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    query = (
        db.query(Followup, Customer)
        .join(Customer, Followup.customer_id == Customer.id)
        .filter(Followup.source.in_(("material_auto", "call_auto", "manual_note", "manual")))
    )
    if current_user.role != "admin":
        query = query.filter(Followup.user_id == current_user.id)

    rows = (
        query
        .order_by(
            Followup.next_followup_at.is_(None),
            Followup.next_followup_at.asc(),
            Customer.intent_score.desc(),
            Followup.created_at.desc(),
        )
        .limit(limit * 3)
        .all()
    )

    seen_customer_ids: set[int] = set()
    items: list[dict] = []
    for followup, customer in rows:
        if customer.id in seen_customer_ids:
            continue
        seen_customer_ids.add(customer.id)
        items.append(
            {
                "id": customer.id,
                "customer_id": customer.id,
                "name": customer.name,
                "phone": customer.phone,
                "intent_level": customer.intent_level,
                "intent_score": customer.intent_score,
                "demand_summary": customer.demand_summary,
                "next_action": customer.next_action,
                "followup_id": followup.id,
                "followup_content": followup.content,
                "followup_source": followup.source,
                "next_followup_at": followup.next_followup_at,
            }
        )
        if len(items) >= limit:
            break
    return items
