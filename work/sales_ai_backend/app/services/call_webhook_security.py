from fastapi import HTTPException, Request
import hmac
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.services.call_provider_settings import get_effective_call_provider_settings


def verify_call_provider_webhook(request: Request, db: Session | None = None, tenant_id: int | None = None) -> None:
    """Optional shared guard for telephony provider callbacks.

    Real providers usually have their own signature algorithm. This guard is kept
    disabled by default and gives production deployments a simple shared-secret
    gate until a provider-specific verifier is connected.
    """
    expected = get_effective_call_provider_settings(db, tenant_id).webhook_secret if db is not None else get_settings().call_provider_webhook_secret
    if not expected:
        return

    provided = request.headers.get("X-Call-Provider-Secret") or request.query_params.get("webhook_secret")
    if not provided or not hmac.compare_digest(provided, expected):
        raise HTTPException(status_code=401, detail="invalid call provider webhook secret")
