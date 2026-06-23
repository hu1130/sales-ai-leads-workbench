from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import hash_password
from app.models.user import User


def create_default_admin(db: Session) -> None:
    settings = get_settings()
    existing = db.query(User).filter(User.username == settings.default_admin_username).first()
    if existing:
        return
    admin = User(
        username=settings.default_admin_username,
        password_hash=hash_password(settings.default_admin_password),
        name="系统管理员",
        role="admin",
        status="active",
    )
    db.add(admin)
    db.commit()

