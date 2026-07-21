from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.call_provider_config import CallProviderConfig
from app.services.secret_crypto import decrypt_secret, mask_secret


@dataclass
class EffectiveCallProviderSettings:
    provider: str
    base_url: str | None
    app_id: str | None
    app_key: str | None
    app_secret: str | None
    caller: str | None
    script_id: str | None
    webhook_secret: str | None
    timeout: float
    enabled: bool
    source: str
    updated_at: datetime | None = None
    updated_by: int | None = None

    @property
    def mode(self) -> str:
        return "mock" if self.provider == "mock" else "real"

    @property
    def configured(self) -> bool:
        if self.provider == "mock":
            return True
        if self.provider in {"aliyun", "aliyun_outboundbot", "aliyun-outboundbot"}:
            return bool(self.app_id and self.app_key and self.app_secret and self.caller and self.script_id and self.enabled)
        return bool(self.base_url and (self.app_key or self.app_id) and self.app_secret and self.enabled)


def get_saved_call_provider_config(db: Session, tenant_id: int | None = None) -> CallProviderConfig | None:
    query = db.query(CallProviderConfig)
    if tenant_id is not None:
        query = query.filter(CallProviderConfig.tenant_id == tenant_id)
    return query.order_by(CallProviderConfig.updated_at.desc(), CallProviderConfig.id.desc()).first()


def get_effective_call_provider_settings(db: Session | None = None, tenant_id: int | None = None) -> EffectiveCallProviderSettings:
    settings = get_settings()
    if db is not None:
        saved = get_saved_call_provider_config(db, tenant_id)
        if saved is not None:
            return EffectiveCallProviderSettings(
                provider=(saved.provider or "mock").strip().lower(),
                base_url=_clean(saved.base_url),
                app_id=_clean(saved.app_id),
                app_key=decrypt_secret(saved.app_key_encrypted),
                app_secret=decrypt_secret(saved.app_secret_encrypted),
                caller=_clean(saved.caller),
                script_id=_clean(settings.call_provider_script_id),
                webhook_secret=decrypt_secret(saved.webhook_secret_encrypted),
                timeout=float(saved.timeout or settings.call_provider_timeout),
                enabled=bool(saved.enabled),
                source="database",
                updated_at=saved.updated_at,
                updated_by=saved.updated_by,
            )
    return EffectiveCallProviderSettings(
        provider=(settings.call_provider or "mock").strip().lower(),
        base_url=_clean(settings.call_provider_base_url),
        app_id=_clean(settings.call_provider_app_id),
        app_key=_clean(settings.call_provider_app_key),
        app_secret=_clean(settings.call_provider_app_secret),
        caller=_clean(settings.call_provider_caller),
        script_id=_clean(settings.call_provider_script_id),
        webhook_secret=_clean(settings.call_provider_webhook_secret),
        timeout=float(settings.call_provider_timeout),
        enabled=True,
        source="environment",
    )


def secret_state(value: str | None) -> tuple[bool, str | None]:
    return bool(_clean(value)), mask_secret(value)


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    return text or None
