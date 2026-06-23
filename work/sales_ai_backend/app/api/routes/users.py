from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.core.database import get_db
from app.core.security import hash_password
from app.models.user import User
from app.schemas.user import UserCreate, UserOut, UserUpdate

router = APIRouter()


@router.get("", response_model=list[UserOut])
def list_users(
    role: str | None = None,
    status: str | None = None,
    keyword: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[User]:
    query = db.query(User)
    if role:
        query = query.filter(User.role == role)
    if status:
        query = query.filter(User.status == status)
    if keyword:
        like = f"%{keyword}%"
        query = query.filter((User.username.like(like)) | (User.name.like(like)) | (User.phone.like(like)))
    return query.order_by(User.id.desc()).offset((page - 1) * page_size).limit(page_size).all()


@router.post("", response_model=UserOut)
def create_user(
    payload: UserCreate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> User:
    existing = db.query(User).filter(User.username == payload.username).first()
    if existing:
        raise HTTPException(status_code=400, detail="账号已存在")
    if payload.role not in {"sales", "admin"}:
        raise HTTPException(status_code=400, detail="角色只能是 sales 或 admin")
    user = User(
        username=payload.username,
        password_hash=hash_password(payload.password),
        name=payload.name,
        phone=payload.phone,
        role=payload.role,
        status="active",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.patch("/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    payload: UserUpdate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    if payload.role is not None and payload.role not in {"sales", "admin"}:
        raise HTTPException(status_code=400, detail="角色只能是 sales 或 admin")
    if payload.status is not None and payload.status not in {"active", "disabled"}:
        raise HTTPException(status_code=400, detail="状态只能是 active 或 disabled")

    for field in ("name", "phone", "role", "status"):
        value = getattr(payload, field)
        if value is not None:
            setattr(user, field, value)
    if payload.password:
        user.password_hash = hash_password(payload.password)
    db.commit()
    db.refresh(user)
    return user

