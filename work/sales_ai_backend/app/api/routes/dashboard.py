from datetime import datetime, time

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_current_user, require_admin
from app.core.database import get_db
from app.core.security import now_local
from app.models.customer import Customer
from app.models.followup import Followup
from app.models.quotation import Quotation
from app.models.upload import UploadRecord
from app.models.user import User

router = APIRouter()


@router.get("/stats")
def dashboard_stats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    is_admin = current_user.role == "admin"
    customer_query = db.query(Customer)
    upload_query = db.query(UploadRecord)
    if not is_admin:
        customer_query = customer_query.filter(Customer.owner_id == current_user.id)
        upload_query = upload_query.filter(UploadRecord.uploader_id == current_user.id)
    total_customers = customer_query.count()
    total_uploads = upload_query.count()
    high_intent_customers = (
        customer_query
        .filter((Customer.intent_level == "高意向") | (Customer.intent_score >= 80))
        .count()
    )
    intent_query = db.query(Customer.intent_level, func.count(Customer.id))
    if not is_admin:
        intent_query = intent_query.filter(Customer.owner_id == current_user.id)
    intent_rows = intent_query.group_by(Customer.intent_level).all()

    sales_upload_rows = []
    if is_admin:
        sales_upload_rows = (
            db.query(UploadRecord.uploader_id, func.count(UploadRecord.id))
            .group_by(UploadRecord.uploader_id)
            .all()
        )
    return {
        "total_customers": total_customers,
        "total_uploads": total_uploads,
        "high_intent_customers": high_intent_customers,
        "unassigned_customers": customer_query.filter(Customer.lead_status == "unassigned").count() if is_admin else 0,
        "intent_distribution": {level: count for level, count in intent_rows},
        "sales_upload_distribution": {str(user_id): count for user_id, count in sales_upload_rows},
    }


@router.get("/team-today")
def team_today(
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    today_start = now_local().replace(hour=0, minute=0, second=0, microsecond=0)
    users = db.query(User).filter(User.role == "sales", User.status == "active").order_by(User.id.desc()).all()
    if not users:
        return {"date": today_start.date().isoformat(), "unassigned_customers": 0, "items": []}

    user_ids = [user.id for user in users]
    user_map = {user.id: user for user in users}

    # Batch all aggregate queries
    customer_counts = dict(
        db.query(Customer.owner_id, func.count(Customer.id))
        .filter(Customer.owner_id.in_(user_ids))
        .group_by(Customer.owner_id)
        .all()
    )
    today_customer_counts = dict(
        db.query(Customer.owner_id, func.count(Customer.id))
        .filter(Customer.owner_id.in_(user_ids), Customer.created_at >= today_start)
        .group_by(Customer.owner_id)
        .all()
    )
    today_followup_counts = dict(
        db.query(Followup.user_id, func.count(Followup.id))
        .filter(Followup.user_id.in_(user_ids), Followup.created_at >= today_start)
        .group_by(Followup.user_id)
        .all()
    )
    today_upload_counts = dict(
        db.query(UploadRecord.uploader_id, func.count(UploadRecord.id))
        .filter(UploadRecord.uploader_id.in_(user_ids), UploadRecord.created_at >= today_start)
        .group_by(UploadRecord.uploader_id)
        .all()
    )
    high_intent_counts = dict(
        db.query(Customer.owner_id, func.count(Customer.id))
        .filter(
            Customer.owner_id.in_(user_ids),
            (Customer.intent_level == "高意向") | (Customer.intent_score >= 80),
        )
        .group_by(Customer.owner_id)
        .all()
    )
    pending_followup_counts = dict(
        db.query(Customer.owner_id, func.count(Customer.id))
        .filter(Customer.owner_id.in_(user_ids), Customer.last_followup_at.is_(None))
        .group_by(Customer.owner_id)
        .all()
    )

    rows = []
    for user_id in user_ids:
        user = user_map[user_id]
        rows.append(
            {
                "user_id": user.id,
                "username": user.username,
                "name": user.name,
                "phone": user.phone,
                "today_customers": today_customer_counts.get(user_id, 0),
                "today_followups": today_followup_counts.get(user_id, 0),
                "today_uploads": today_upload_counts.get(user_id, 0),
                "high_intent_customers": high_intent_counts.get(user_id, 0),
                "pending_followup_customers": pending_followup_counts.get(user_id, 0),
                "total_customers": customer_counts.get(user_id, 0),
            }
        )
    unassigned = db.query(Customer).filter(Customer.lead_status == "unassigned").count()
    return {
        "date": today_start.date().isoformat(),
        "unassigned_customers": unassigned,
        "items": rows,
    }


@router.get("/funnel")
def sales_funnel(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Return conversion funnel stats for the current user/team."""
    is_admin = current_user.role == "admin"
    base_query = db.query(Customer)
    followup_query = db.query(Followup)

    if not is_admin:
        base_query = base_query.filter(Customer.owner_id == current_user.id)
        followup_query = followup_query.filter(Followup.user_id == current_user.id)
        user_filter = Customer.owner_id == current_user.id
        quotation_query = db.query(Quotation).filter(Quotation.user_id == current_user.id)
    else:
        user_filter = True
        quotation_query = db.query(Quotation)

    total_leads = base_query.count()

    # Monthly closed won count & revenue
    month_start = now_local().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    won = db.query(Quotation).filter(Quotation.status == "accepted", Quotation.sent_at >= month_start)
    if not is_admin:
        won = won.filter(Quotation.user_id == current_user.id)
    monthly_closed = won.count()
    revenue_row = db.query(func.coalesce(func.sum(Quotation.total_amount), 0)).select_from(Quotation).filter(
        Quotation.status == "accepted", Quotation.sent_at >= month_start
    )
    if not is_admin:
        revenue_row = revenue_row.filter(Quotation.user_id == current_user.id)
    monthly_revenue = revenue_row.scalar() or 0

    # Newly assigned (today)
    today_start = now_local().replace(hour=0, minute=0, second=0, microsecond=0)
    new_assignments = base_query.filter(Customer.assigned_at >= today_start).count()

    # Pipeline stage counts
    stage_counts = dict(
        base_query.with_entities(Customer.pipeline_stage, func.count(Customer.id))
        .group_by(Customer.pipeline_stage)
        .all()
    )

    # Followup status counts
    status_counts = dict(
        followup_query.with_entities(Followup.status, func.count(Followup.id))
        .group_by(Followup.status)
        .all()
    )

    return {
        "total_leads": total_leads,
        "new_assignments_today": new_assignments,
        "monthly_closed": monthly_closed,
        "monthly_revenue": round(float(monthly_revenue), 2),
        "stage_counts": {
            "lead": stage_counts.get("lead", 0),
            "followup": stage_counts.get("followup", 0),
            "negotiation": stage_counts.get("negotiation", 0),
            "closed_won": stage_counts.get("closed_won", 0),
            "closed_lost": stage_counts.get("closed_lost", 0),
        },
        "followup_status": {
            "pending": status_counts.get("pending", 0),
            "contacted": status_counts.get("contacted", 0),
            "meeting": status_counts.get("meeting", 0),
            "completed": status_counts.get("completed", 0),
        },
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
        .options(joinedload(Customer.owner))
        .filter(Followup.source.in_(("material_auto", "call_auto", "manual_note", "manual")))
        .filter(Followup.status == "pending")
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
                "wechat_id": customer.wechat_id,
                "wechat_nickname": customer.wechat_nickname,
                "phone": customer.phone,
                "owner_id": customer.owner_id,
                "owner_name": customer.owner_name,
                "owner_username": customer.owner_username,
                "intent_level": customer.intent_level,
                "intent_score": customer.intent_score,
                "demand_summary": customer.demand_summary,
                "next_action": customer.next_action,
                "followup_id": followup.id,
                "followup_content": followup.content,
                "followup_source": followup.source,
                "followup_status": followup.status,
                "next_followup_at": followup.next_followup_at,
            }
        )
        if len(items) >= limit:
            break
    return items
