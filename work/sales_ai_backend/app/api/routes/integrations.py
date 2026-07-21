from hmac import compare_digest

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.api.deps import require_admin
from app.api.routes import call_provider_config as call_provider_routes
from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import now_local
from app.models.ai_robot_call import AiRobotCall
from app.models.call_attempt import CallAttempt
from app.models.customer import Customer
from app.models.followup import Followup
from app.models.user import User
from app.schemas.call_provider_config import (
    CallProviderConfigOut,
    CallProviderConfigUpdate,
    CallProviderStatusOut,
    CallProviderTestOut,
    CallProviderTestRequest,
)
from app.schemas.integration import (
    IntegrationAiRobotCallSummary,
    IntegrationCallSummary,
    IntegrationCustomerOut,
    IntegrationFollowupOut,
    IntegrationLeadListResponse,
    WebsiteLeadCreate,
    WebsiteLeadResponse,
)

router = APIRouter(prefix="/integrations", tags=["integrations"])


def require_integration_tenant(
    x_integration_key: str | None = Header(default=None, alias="X-Integration-Key"),
) -> int:
    settings = get_settings()
    expected = _clean(settings.integration_api_key)
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="integration api key is not configured",
        )
    if not x_integration_key or not compare_digest(x_integration_key, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid integration key")
    return int(settings.integration_tenant_id or 1)


@router.post("/website/leads", response_model=WebsiteLeadResponse)
def create_website_lead(
    payload: WebsiteLeadCreate,
    tenant_id: int = Depends(require_integration_tenant),
    db: Session = Depends(get_db),
) -> WebsiteLeadResponse:
    phone = _clean_phone(payload.phone)
    wechat_id = _clean(payload.wechat_id)
    if not phone and not wechat_id:
        raise HTTPException(status_code=422, detail="phone or wechat_id is required")

    customer = _find_customer_by_contact(db, tenant_id, phone, wechat_id)
    created = customer is None
    lead_source = _clean(payload.source) or "website"
    now = now_local()

    if customer is None:
        customer = Customer(
            tenant_id=tenant_id,
            owner_id=None,
            name=_clean(payload.name),
            phone=phone,
            wechat_id=wechat_id,
            wechat_nickname=_clean(payload.wechat_nickname),
            address=_clean(payload.address),
            source=lead_source,
            lead_source=lead_source,
            lead_status="unassigned",
            pipeline_stage="lead",
            demand_summary=_clean(payload.message),
            next_action="Assign sales owner and follow up website lead.",
        )
        db.add(customer)
        db.flush()
    else:
        _fill_missing_customer_fields(customer, payload, phone, wechat_id, lead_source)

    system_user = _get_system_user(db, tenant_id)
    followup = Followup(
        tenant_id=tenant_id,
        customer_id=customer.id,
        user_id=system_user.id,
        content=_website_followup_content(payload, lead_source),
        source="website",
        status="pending",
    )
    customer.last_followup_at = now
    customer.updated_at = now
    db.add(followup)
    db.commit()

    return WebsiteLeadResponse(
        accepted=True,
        created=created,
        customer_id=customer.id,
        duplicate_of_id=None if created else customer.id,
        message="website lead accepted",
    )


@router.get("/sales-ai/leads", response_model=IntegrationLeadListResponse)
def list_sales_ai_leads(
    keyword: str | None = None,
    intent_level: str | None = None,
    min_score: int | None = Query(default=None, ge=0, le=100),
    lead_status: str | None = None,
    pipeline_stage: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    tenant_id: int = Depends(require_integration_tenant),
    db: Session = Depends(get_db),
) -> IntegrationLeadListResponse:
    query = db.query(Customer).options(joinedload(Customer.owner)).filter(Customer.tenant_id == tenant_id)
    if keyword:
        pattern = f"%{keyword.strip()}%"
        query = query.filter(
            or_(
                Customer.name.ilike(pattern),
                Customer.phone.ilike(pattern),
                Customer.wechat_id.ilike(pattern),
                Customer.wechat_nickname.ilike(pattern),
                Customer.demand_summary.ilike(pattern),
                Customer.next_action.ilike(pattern),
            )
        )
    if intent_level:
        query = query.filter(Customer.intent_level == intent_level)
    if min_score is not None:
        query = query.filter(Customer.intent_score >= min_score)
    if lead_status:
        query = query.filter(Customer.lead_status == lead_status)
    if pipeline_stage:
        query = query.filter(Customer.pipeline_stage == pipeline_stage)

    total = query.count()
    customers = (
        query.order_by(Customer.intent_score.desc(), Customer.updated_at.desc(), Customer.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return IntegrationLeadListResponse(
        items=[_customer_out(db, customer) for customer in customers],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/sales-ai/customers/{customer_id}", response_model=IntegrationCustomerOut)
def get_sales_ai_customer(
    customer_id: int,
    tenant_id: int = Depends(require_integration_tenant),
    db: Session = Depends(get_db),
) -> IntegrationCustomerOut:
    customer = (
        db.query(Customer)
        .options(joinedload(Customer.owner))
        .filter(Customer.tenant_id == tenant_id, Customer.id == customer_id)
        .first()
    )
    if customer is None:
        raise HTTPException(status_code=404, detail="customer not found")
    return _customer_out(db, customer)


@router.get("/sales-ai/customers/{customer_id}/followups", response_model=list[IntegrationFollowupOut])
def list_sales_ai_customer_followups(
    customer_id: int,
    tenant_id: int = Depends(require_integration_tenant),
    db: Session = Depends(get_db),
) -> list[Followup]:
    exists = db.query(Customer.id).filter(Customer.tenant_id == tenant_id, Customer.id == customer_id).first()
    if exists is None:
        raise HTTPException(status_code=404, detail="customer not found")
    return (
        db.query(Followup)
        .filter(Followup.tenant_id == tenant_id, Followup.customer_id == customer_id)
        .order_by(Followup.created_at.desc(), Followup.id.desc())
        .all()
    )


@router.get("/call-provider/config", response_model=CallProviderConfigOut)
def get_integration_call_provider_config(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> CallProviderConfigOut:
    return call_provider_routes.get_call_provider_config(current_user, db)


@router.put("/call-provider/config", response_model=CallProviderConfigOut)
def put_integration_call_provider_config(
    payload: CallProviderConfigUpdate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> CallProviderConfigOut:
    return call_provider_routes.put_call_provider_config(payload, current_user, db)


@router.patch("/call-provider/config", response_model=CallProviderConfigOut)
def patch_integration_call_provider_config(
    payload: CallProviderConfigUpdate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> CallProviderConfigOut:
    return call_provider_routes.patch_call_provider_config(payload, current_user, db)


@router.get("/call-provider/status", response_model=CallProviderStatusOut)
def get_integration_call_provider_status(
    request: Request,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> CallProviderStatusOut:
    return call_provider_routes.get_call_provider_status(request, current_user, db)


@router.post("/call-provider/test-callback", response_model=CallProviderTestOut)
def test_integration_sales_callback_provider(
    payload: CallProviderTestRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> CallProviderTestOut:
    return call_provider_routes.test_sales_callback_provider(payload, current_user, db)


@router.post("/call-provider/test-ai-robot", response_model=CallProviderTestOut)
def test_integration_ai_robot_provider(
    payload: CallProviderTestRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> CallProviderTestOut:
    return call_provider_routes.test_ai_robot_provider(payload, current_user, db)


def _find_customer_by_contact(db: Session, tenant_id: int, phone: str | None, wechat_id: str | None) -> Customer | None:
    filters = []
    if phone:
        filters.append(Customer.phone == phone)
    if wechat_id:
        filters.append(Customer.wechat_id == wechat_id)
    if not filters:
        return None
    return (
        db.query(Customer)
        .options(joinedload(Customer.owner))
        .filter(Customer.tenant_id == tenant_id)
        .filter(or_(*filters))
        .order_by(Customer.updated_at.desc(), Customer.id.desc())
        .first()
    )


def _fill_missing_customer_fields(
    customer: Customer,
    payload: WebsiteLeadCreate,
    phone: str | None,
    wechat_id: str | None,
    lead_source: str,
) -> None:
    fill_fields = {
        "name": _clean(payload.name),
        "phone": phone,
        "wechat_id": wechat_id,
        "wechat_nickname": _clean(payload.wechat_nickname),
        "address": _clean(payload.address),
        "source": lead_source,
        "lead_source": lead_source,
        "demand_summary": _clean(payload.message),
    }
    for field, value in fill_fields.items():
        if value and not getattr(customer, field):
            setattr(customer, field, value)
    if customer.lead_status not in {"assigned", "unassigned"}:
        customer.lead_status = "unassigned"


def _get_system_user(db: Session, tenant_id: int) -> User:
    user = (
        db.query(User)
        .filter(User.tenant_id == tenant_id, User.role == "admin", User.status == "active")
        .order_by(User.id.asc())
        .first()
    )
    if user is None:
        user = db.query(User).filter(User.tenant_id == tenant_id, User.status == "active").order_by(User.id.asc()).first()
    if user is None:
        raise HTTPException(status_code=500, detail="no active user available for integration followup")
    return user


def _website_followup_content(payload: WebsiteLeadCreate, lead_source: str) -> str:
    parts = [f"Website lead submitted from {lead_source}."]
    mapping = (
        ("external_id", payload.external_id),
        ("campaign", payload.campaign),
        ("page_url", payload.page_url),
        ("referrer", payload.referrer),
        ("utm_source", payload.utm_source),
        ("utm_medium", payload.utm_medium),
        ("utm_campaign", payload.utm_campaign),
        ("utm_term", payload.utm_term),
        ("utm_content", payload.utm_content),
        ("message", payload.message),
    )
    for key, value in mapping:
        cleaned = _clean(value)
        if cleaned:
            parts.append(f"{key}: {cleaned}")
    return "\n".join(parts)


def _customer_out(db: Session, customer: Customer) -> IntegrationCustomerOut:
    latest_followup = _latest_followup(db, customer.tenant_id, customer.id)
    latest_call = _latest_call(db, customer.tenant_id, customer.id)
    latest_ai_robot_call = _latest_ai_robot_call(db, customer.tenant_id, customer.id)
    return IntegrationCustomerOut(
        id=customer.id,
        name=customer.name,
        phone=customer.phone,
        wechat_id=customer.wechat_id,
        wechat_nickname=customer.wechat_nickname,
        address=customer.address,
        source=customer.source,
        lead_source=customer.lead_source,
        lead_status=customer.lead_status,
        pipeline_stage=customer.pipeline_stage,
        intent_level=customer.intent_level,
        intent_score=customer.intent_score,
        demand_summary=customer.demand_summary,
        concerns=customer.concerns,
        product_interest=customer.product_interest,
        budget=customer.budget,
        purchase_time=customer.purchase_time,
        next_action=customer.next_action,
        owner_id=customer.owner_id,
        owner_name=customer.owner_name,
        last_followup_at=customer.last_followup_at,
        created_at=customer.created_at,
        updated_at=customer.updated_at,
        latest_followup=latest_followup,
        latest_call=latest_call,
        latest_ai_robot_call=latest_ai_robot_call,
    )


def _latest_followup(db: Session, tenant_id: int, customer_id: int) -> IntegrationFollowupOut | None:
    followup = (
        db.query(Followup)
        .filter(Followup.tenant_id == tenant_id, Followup.customer_id == customer_id)
        .order_by(Followup.created_at.desc(), Followup.id.desc())
        .first()
    )
    return IntegrationFollowupOut.model_validate(followup) if followup else None


def _latest_call(db: Session, tenant_id: int, customer_id: int) -> IntegrationCallSummary | None:
    call = (
        db.query(CallAttempt)
        .filter(CallAttempt.tenant_id == tenant_id, CallAttempt.customer_id == customer_id)
        .order_by(CallAttempt.created_at.desc(), CallAttempt.id.desc())
        .first()
    )
    if call is None:
        return None
    return IntegrationCallSummary(
        id=call.id,
        call_mode=call.call_mode,
        call_status=call.call_status,
        duration_seconds=call.duration_seconds,
        intent_level=call.intent_level,
        intent_score=call.intent_score,
        next_action=call.next_action,
        created_at=call.created_at,
    )


def _latest_ai_robot_call(db: Session, tenant_id: int, customer_id: int) -> IntegrationAiRobotCallSummary | None:
    robot_call = (
        db.query(AiRobotCall)
        .filter(AiRobotCall.tenant_id == tenant_id, AiRobotCall.customer_id == customer_id)
        .order_by(AiRobotCall.created_at.desc(), AiRobotCall.id.desc())
        .first()
    )
    if robot_call is None:
        return None
    return IntegrationAiRobotCallSummary(
        id=robot_call.id,
        provider=robot_call.provider,
        status=robot_call.status,
        high_intent=robot_call.high_intent,
        intent_level=robot_call.intent_level,
        intent_score=robot_call.intent_score,
        duration_seconds=robot_call.duration_seconds,
        created_at=robot_call.created_at,
    )


def _clean_phone(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = "".join(ch for ch in value.strip() if ch.isdigit() or ch == "+")
    return cleaned or None


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    return text or None
