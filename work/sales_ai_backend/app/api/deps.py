from hmac import compare_digest

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import decode_access_token
from app.models.user import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")
DEFAULT_TENANT_ID = 1


def _active_user_from_token(token: str, db: Session) -> User:
    subject = decode_access_token(token)
    if subject is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="login expired, please sign in again",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = db.get(User, int(subject)) if subject.isdigit() else None
    if user is None or user.status != "active":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="user not found or disabled")
    if getattr(user, "tenant_id", None) is None:
        user.tenant_id = DEFAULT_TENANT_ID
        db.commit()
        db.refresh(user)
    return user


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    return _active_user_from_token(token, db)


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin role required")
    return current_user


def get_current_user_or_platform_service(
    authorization: str | None = Header(default=None, alias="Authorization"),
    db: Session = Depends(get_db),
) -> User:
    token = ""
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()

    settings = get_settings()
    service_token = (settings.platform_service_token or "").strip()
    if service_token and token and compare_digest(token, service_token):
        user = (
            db.query(User)
            .filter(
                User.tenant_id == int(settings.platform_tenant_id or DEFAULT_TENANT_ID),
                User.role == "admin",
                User.status == "active",
            )
            .order_by(User.id.asc())
            .first()
        )
        if user is None:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="platform service tenant has no active admin")
        return user

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="login expired, please sign in again",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return _active_user_from_token(token, db)


def require_platform_service(
    authorization: str | None = Header(default=None, alias="Authorization"),
    db: Session = Depends(get_db),
) -> User:
    token = ""
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()

    settings = get_settings()
    service_token = (settings.platform_service_token or "").strip()
    if not service_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="platform service authentication is not configured",
        )
    if not token or not compare_digest(token, service_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="platform service authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = (
        db.query(User)
        .filter(
            User.tenant_id == int(settings.platform_tenant_id or DEFAULT_TENANT_ID),
            User.role == "admin",
            User.status == "active",
        )
        .order_by(User.id.asc())
        .first()
    )
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="platform service tenant has no active admin",
        )
    return user


def require_admin_or_platform_service(
    current_user: User = Depends(get_current_user_or_platform_service),
) -> User:
    return require_admin(current_user)


def tenant_id_for(user: User) -> int:
    return int(getattr(user, "tenant_id", None) or DEFAULT_TENANT_ID)


def assert_same_tenant(entity, current_user: User, *, not_found_detail: str = "resource not found") -> None:
    if entity is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=not_found_detail)
    entity_tenant_id = getattr(entity, "tenant_id", None)
    if entity_tenant_id is not None and int(entity_tenant_id) != tenant_id_for(current_user):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=not_found_detail)


def assert_user_same_tenant(
    user: User | None,
    current_user: User,
    *,
    detail: str = "user not found",
    require_active: bool = True,
) -> User:
    if user is None or tenant_id_for(user) != tenant_id_for(current_user) or (require_active and user.status != "active"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)
    return user
