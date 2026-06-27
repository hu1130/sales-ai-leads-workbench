from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.analysis import AIAnalysisResult
from app.models.customer import Customer


def find_or_create_customer(
    db: Session,
    owner_id: int | None,
    customer_id: int | None = None,
    phone: str | None = None,
    name: str | None = None,
    wechat_id: str | None = None,
    wechat_nickname: str | None = None,
) -> Customer:
    if customer_id:
        customer = db.get(Customer, customer_id)
        if customer:
            return customer

    normalized_phone = _clean_unknown(phone)
    normalized_name = _clean_unknown(name)
    normalized_wechat_id = _clean_unknown(wechat_id)
    normalized_wechat_nickname = _clean_unknown(wechat_nickname)

    customer = None
    if normalized_wechat_id:
        customer = (
            db.query(Customer)
            .filter(Customer.wechat_id == normalized_wechat_id)
            .filter(or_(Customer.owner_id == owner_id, Customer.owner_id.is_(None)))
            .first()
        )

    if customer is None and normalized_phone:
        customer = (
            db.query(Customer)
            .filter(Customer.phone == normalized_phone)
            .filter(or_(Customer.owner_id == owner_id, Customer.owner_id.is_(None)))
            .first()
        )

    if customer is None and normalized_wechat_nickname:
        customer = (
            db.query(Customer)
            .filter(or_(Customer.owner_id == owner_id, Customer.owner_id.is_(None)))
            .filter(Customer.wechat_nickname == normalized_wechat_nickname)
            .first()
        )

    if customer is None and normalized_name:
        customer = (
            db.query(Customer)
            .filter(or_(Customer.owner_id == owner_id, Customer.owner_id.is_(None)))
            .filter(Customer.name == normalized_name)
            .first()
        )

    if customer is None:
        customer = Customer(
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
    if _clean_unknown(analysis.customer_phone) and not customer.phone:
        customer.phone = analysis.customer_phone
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


def _is_missing_or_corrupt_name(value: str | None) -> bool:
    cleaned = _clean_unknown(value)
    if not cleaned:
        return True
    return all(character in {"?", "\uff1f", "\ufffd"} for character in cleaned)
