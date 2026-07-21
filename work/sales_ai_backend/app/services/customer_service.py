import re

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.analysis import AIAnalysisResult
from app.models.customer import Customer
from app.models.user import User


def find_or_create_customer(
    db: Session,
    owner_id: int | None,
    tenant_id: int | None = None,
    customer_id: int | None = None,
    phone: str | None = None,
    name: str | None = None,
    wechat_id: str | None = None,
    wechat_nickname: str | None = None,
) -> Customer:
    resolved_tenant_id = _resolve_tenant_id(db, tenant_id, owner_id)
    if customer_id:
        customer = (
            db.query(Customer)
            .filter(Customer.id == customer_id)
            .filter(Customer.tenant_id == resolved_tenant_id)
            .first()
        )
        if customer:
            return customer

    normalized_phone = _normalize_phone(_clean_unknown(phone))
    normalized_name = _clean_unknown(name)
    normalized_wechat_id = _clean_unknown(wechat_id)
    normalized_wechat_nickname = _clean_unknown(wechat_nickname)

    customer = None
    if normalized_wechat_id:
        customer = (
            db.query(Customer)
            .filter(Customer.tenant_id == resolved_tenant_id)
            .filter(Customer.wechat_id == normalized_wechat_id)
            .filter(or_(Customer.owner_id == owner_id, Customer.owner_id.is_(None)))
            .first()
        )

    if customer is None and normalized_phone:
        customer = _find_by_normalized_phone(db, owner_id, normalized_phone, resolved_tenant_id)

    if customer is None and normalized_wechat_nickname:
        customer = (
            db.query(Customer)
            .filter(Customer.tenant_id == resolved_tenant_id)
            .filter(or_(Customer.owner_id == owner_id, Customer.owner_id.is_(None)))
            .filter(Customer.wechat_nickname == normalized_wechat_nickname)
            .first()
        )

    if customer is None and normalized_name:
        customer = (
            db.query(Customer)
            .filter(Customer.tenant_id == resolved_tenant_id)
            .filter(or_(Customer.owner_id == owner_id, Customer.owner_id.is_(None)))
            .filter(Customer.name == normalized_name)
            .first()
        )

    if customer is None:
        customer = Customer(
            tenant_id=resolved_tenant_id,
            owner_id=owner_id,
            phone=normalized_phone,
            name=normalized_name,
            wechat_id=normalized_wechat_id,
            wechat_nickname=normalized_wechat_nickname,
            source="AI上传",
            lead_source="AI上传",
            lead_status="assigned" if owner_id else "unassigned",
        )
        db.add(customer)
        db.flush()
    else:
        if customer.owner_id is None and owner_id:
            customer.owner_id = owner_id
            customer.lead_status = "assigned"
        if normalized_phone and not _normalize_phone(customer.phone):
            customer.phone = normalized_phone
        if normalized_wechat_id and not _clean_unknown(customer.wechat_id):
            customer.wechat_id = normalized_wechat_id
        if normalized_wechat_nickname and not _clean_unknown(customer.wechat_nickname):
            customer.wechat_nickname = normalized_wechat_nickname
        if normalized_name and _is_missing_or_corrupt_name(customer.name):
            customer.name = normalized_name
    return customer


def update_customer_from_analysis(customer: Customer, analysis: AIAnalysisResult) -> None:
    if _should_keep_existing_profile(customer, analysis):
        return

    if _clean_unknown(analysis.customer_name) and _is_missing_or_corrupt_name(customer.name):
        customer.name = analysis.customer_name
    if _clean_unknown(analysis.customer_wechat_id) and not customer.wechat_id:
        customer.wechat_id = analysis.customer_wechat_id
    if _clean_unknown(analysis.customer_wechat_nickname) and not customer.wechat_nickname:
        customer.wechat_nickname = analysis.customer_wechat_nickname
    normalized_phone = _normalize_phone(_clean_unknown(analysis.customer_phone))
    if normalized_phone and not _normalize_phone(customer.phone):
        customer.phone = normalized_phone
    if _clean_unknown(analysis.customer_address) and not customer.address:
        customer.address = analysis.customer_address
    customer.intent_level = analysis.intent_level
    customer.intent_score = analysis.intent_score
    customer.demand_summary = analysis.customer_needs or analysis.summary
    customer.concerns = analysis.customer_objections or analysis.customer_questions
    customer.product_interest = analysis.product_interest
    customer.budget = analysis.budget
    customer.purchase_time = analysis.purchase_time
    customer.next_action = analysis.next_action


def _should_keep_existing_profile(customer: Customer, analysis: AIAnalysisResult) -> bool:
    has_existing_signal = (customer.intent_score or 0) >= 40 and _clean_unknown(customer.demand_summary)
    incoming_is_weak = (analysis.intent_score or 0) <= 0 and analysis.intent_level in {"无法判断", "暂无意向"}
    incoming_has_no_content = _is_low_information_text(analysis.summary) or not any(
        _clean_unknown(value)
        for value in (
            analysis.customer_needs,
            analysis.summary,
            analysis.product_interest,
            analysis.budget,
            analysis.purchase_time,
        )
    )
    return bool(has_existing_signal and incoming_is_weak and incoming_has_no_content)


def _is_low_information_text(value: str | None) -> bool:
    cleaned = _clean_unknown(value)
    if not cleaned:
        return True
    low_information_markers = (
        "没有可用于判断",
        "本次分析没有拿到",
        "无可用于判断",
        "当前没有可用",
        "请上传",
        "接入图片识别",
        "接入语音识别",
    )
    return any(marker in cleaned for marker in low_information_markers)


def _clean_unknown(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if value in {"", "未提及", "无法判断", "未知"}:
        return None
    return value


def _normalize_phone(value: str | None) -> str | None:
    value = _clean_unknown(value)
    if not value:
        return None
    digits = re.sub(r"\D", "", value)
    if not digits:
        return None
    if len(digits) == 13 and digits.startswith("86"):
        digits = digits[2:]
    return digits


def _resolve_tenant_id(db: Session, tenant_id: int | None, owner_id: int | None) -> int:
    if tenant_id:
        return int(tenant_id)
    if owner_id:
        owner = db.get(User, owner_id)
        if owner is not None and owner.tenant_id:
            return int(owner.tenant_id)
    return 1


def _find_by_normalized_phone(db: Session, owner_id: int | None, phone: str, tenant_id: int | None = None) -> Customer | None:
    resolved_tenant_id = _resolve_tenant_id(db, tenant_id, owner_id)
    candidates = (
        db.query(Customer)
        .filter(Customer.tenant_id == resolved_tenant_id)
        .filter(or_(Customer.owner_id == owner_id, Customer.owner_id.is_(None)))
        .filter(Customer.phone.is_not(None))
        .all()
    )
    for candidate in candidates:
        if _normalize_phone(candidate.phone) == phone:
            return candidate
    return None


def _is_missing_or_corrupt_name(value: str | None) -> bool:
    cleaned = _clean_unknown(value)
    if not cleaned:
        return True
    return all(character in {"?", "\uff1f", "\ufffd"} for character in cleaned)
