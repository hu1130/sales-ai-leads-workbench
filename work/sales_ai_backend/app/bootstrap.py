from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import hash_password
from app.models.tenant import Tenant
from app.models.user import User

DEFAULT_TENANT_NAME = "深度觉醒（上海）人工智能科技有限公司"
LEGACY_DEFAULT_TENANT_NAMES = {"默认公司", "é»˜è®¤å…¬å�¸", "榛樿鍏徃"}


def create_default_admin(db: Session) -> None:
    settings = get_settings()
    tenant = db.get(Tenant, 1)
    if tenant is None:
        tenant = Tenant(id=1, name=DEFAULT_TENANT_NAME, status="active")
        db.add(tenant)
        db.flush()
    elif tenant.name in LEGACY_DEFAULT_TENANT_NAMES:
        tenant.name = DEFAULT_TENANT_NAME
        tenant.status = "active"
        db.flush()
    existing = db.query(User).filter(User.username == settings.default_admin_username).first()
    if existing:
        if existing.tenant_id is None:
            existing.tenant_id = tenant.id
            db.commit()
        return
    admin = User(
        tenant_id=tenant.id,
        username=settings.default_admin_username,
        password_hash=hash_password(settings.default_admin_password),
        name="系统管理员",
        role="admin",
        status="active",
    )
    db.add(admin)
    db.commit()
