from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.api.deps import require_admin, require_admin_or_platform_service, tenant_id_for
from app.core.database import get_db
from app.models.call_provider_config import CallProviderConfig
from app.models.user import User
from app.schemas.call_provider_config import (
    CallProviderConfigOut,
    CallProviderConfigUpdate,
    CallProviderStatusOut,
    CallProviderTestOut,
    CallProviderTestRequest,
)
from app.services.call_provider import CallProviderError, get_call_provider
from app.services.call_provider_settings import (
    get_effective_call_provider_settings,
    get_saved_call_provider_config,
    secret_state,
)
from app.services.secret_crypto import encrypt_secret

router = APIRouter(prefix="/call-provider", tags=["call-provider"])


@router.get("/config", response_model=CallProviderConfigOut)
def get_call_provider_config(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> CallProviderConfigOut:
    return _config_out(db, tenant_id_for(current_user))


@router.put("/config", response_model=CallProviderConfigOut)
def put_call_provider_config(
    payload: CallProviderConfigUpdate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> CallProviderConfigOut:
    return _save_config(payload, current_user, db)


@router.patch("/config", response_model=CallProviderConfigOut)
def patch_call_provider_config(
    payload: CallProviderConfigUpdate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> CallProviderConfigOut:
    return _save_config(payload, current_user, db)


@router.get("/status", response_model=CallProviderStatusOut)
def get_call_provider_status(
    request: Request,
    current_user: User = Depends(require_admin_or_platform_service),
    db: Session = Depends(get_db),
) -> CallProviderStatusOut:
    effective = get_effective_call_provider_settings(db, tenant_id_for(current_user))
    base_url = str(request.base_url).rstrip("/")
    notes: list[str] = []
    if effective.provider == "mock":
        notes.append("mock provider is for flow testing only; it does not place real calls.")
    if effective.provider in {"aliyun", "aliyun_outboundbot", "aliyun-outboundbot"}:
        notes.append("aliyun outboundbot launch is API-based; call result and recording sync still require polling or RocketMQ integration.")
    if effective.provider != "mock" and not effective.configured:
        notes.append("real provider is selected but required configuration is incomplete.")
    if not effective.webhook_secret:
        notes.append("webhook secret is not set; provider webhooks are not protected by the shared-secret guard.")
    if effective.source == "environment":
        notes.append("configuration is loaded from environment variables.")
    else:
        notes.append("configuration is loaded from encrypted database settings.")

    return CallProviderStatusOut(
        provider=effective.provider,
        configured=effective.configured,
        mode=effective.mode,
        base_url_configured=bool(effective.base_url),
        app_id_configured=bool(effective.app_id),
        app_key_configured=bool(effective.app_key),
        app_secret_configured=bool(effective.app_secret),
        caller_configured=bool(effective.caller),
        script_id_configured=bool(effective.script_id),
        webhook_secret_configured=bool(effective.webhook_secret),
        timeout=effective.timeout,
        ai_robot_webhook_url=f"{base_url}/api/ai-robot-calls/webhook/{effective.provider}",
        sales_callback_webhook_url=f"{base_url}/api/sales-callbacks/webhook/{effective.provider}",
        notes=notes,
    )


@router.post("/test-callback", response_model=CallProviderTestOut)
def test_sales_callback_provider(
    payload: CallProviderTestRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> CallProviderTestOut:
    effective = get_effective_call_provider_settings(db, tenant_id_for(current_user))
    provider = _provider_or_400(payload.provider or effective.provider, effective)
    sales_phone = _clean_phone(payload.sales_phone or effective.caller)
    customer_phone = _clean_phone(payload.customer_phone)
    if not sales_phone:
        raise HTTPException(status_code=400, detail="sales_phone or configured caller is required")
    if not customer_phone:
        raise HTTPException(status_code=400, detail="customer_phone is required")
    try:
        launch = provider.start_callback(
            sales_phone=sales_phone,
            customer_phone=customer_phone,
            sales_id=0,
            customer_id=0,
        )
    except CallProviderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return CallProviderTestOut(
        ok=True,
        provider=provider.name,
        test_type="sales_callback",
        provider_call_id=launch.provider_call_id,
        initial_status=launch.initial_status,
        message="provider callback test launched",
        raw_payload=launch.raw_payload,
    )


@router.post("/test-ai-robot", response_model=CallProviderTestOut)
def test_ai_robot_provider(
    payload: CallProviderTestRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> CallProviderTestOut:
    effective = get_effective_call_provider_settings(db, tenant_id_for(current_user))
    provider = _provider_or_400(payload.provider or effective.provider, effective)
    customer_phone = _clean_phone(payload.customer_phone)
    if not customer_phone:
        raise HTTPException(status_code=400, detail="customer_phone is required")
    try:
        launch = provider.start_ai_robot_call(
            customer_phone=customer_phone,
            script_text=payload.script or "AI robot provider connectivity test.",
            campaign_id=0,
            target_id=0,
            customer_id=0,
        )
    except CallProviderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return CallProviderTestOut(
        ok=True,
        provider=provider.name,
        test_type="ai_robot",
        provider_call_id=launch.provider_call_id,
        initial_status=launch.initial_status,
        message="provider ai robot test launched",
        raw_payload=launch.raw_payload,
    )


def _save_config(payload: CallProviderConfigUpdate, user: User, db: Session) -> CallProviderConfigOut:
    current_tenant_id = tenant_id_for(user)
    config = get_saved_call_provider_config(db, current_tenant_id)
    if config is None:
        config = CallProviderConfig(tenant_id=current_tenant_id)
        db.add(config)
        db.flush()

    updates = payload.model_dump(exclude_unset=True)
    for field in ("provider", "base_url", "app_id", "caller"):
        if field in updates:
            value = updates[field]
            setattr(config, field, _clean(value) if isinstance(value, str) else value)
    if "timeout" in updates and updates["timeout"] is not None:
        config.timeout = float(updates["timeout"])
    if "enabled" in updates and updates["enabled"] is not None:
        config.enabled = bool(updates["enabled"])

    if updates.get("clear_app_key"):
        config.app_key_encrypted = None
    elif "app_key" in updates:
        config.app_key_encrypted = encrypt_secret(updates.get("app_key"))

    if updates.get("clear_app_secret"):
        config.app_secret_encrypted = None
    elif "app_secret" in updates:
        config.app_secret_encrypted = encrypt_secret(updates.get("app_secret"))

    if updates.get("clear_webhook_secret"):
        config.webhook_secret_encrypted = None
    elif "webhook_secret" in updates:
        config.webhook_secret_encrypted = encrypt_secret(updates.get("webhook_secret"))

    config.updated_by = user.id
    config.updated_at = datetime.now()
    db.commit()
    return _config_out(db, current_tenant_id)


def _config_out(db: Session, tenant_id: int) -> CallProviderConfigOut:
    effective = get_effective_call_provider_settings(db, tenant_id)
    app_key_configured, app_key_mask = secret_state(effective.app_key)
    app_secret_configured, app_secret_mask = secret_state(effective.app_secret)
    webhook_secret_configured, webhook_secret_mask = secret_state(effective.webhook_secret)
    return CallProviderConfigOut(
        provider=effective.provider,
        base_url=effective.base_url,
        app_id=effective.app_id,
        app_key_configured=app_key_configured,
        app_key_mask=app_key_mask,
        app_secret_configured=app_secret_configured,
        app_secret_mask=app_secret_mask,
        caller=effective.caller,
        script_id=effective.script_id,
        webhook_secret_configured=webhook_secret_configured,
        webhook_secret_mask=webhook_secret_mask,
        timeout=effective.timeout,
        enabled=effective.enabled,
        source=effective.source,
        updated_at=effective.updated_at.isoformat() if effective.updated_at else None,
        updated_by=effective.updated_by,
    )


def _provider_or_400(provider_name: str | None, effective=None):
    try:
        return get_call_provider(provider_name, effective)
    except CallProviderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _clean_phone(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = "".join(ch for ch in value if ch.isdigit() or ch == "+")
    return cleaned or None


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    return text or None
