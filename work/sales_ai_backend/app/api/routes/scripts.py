from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_admin
from app.core.database import get_db
from app.models.script import Script
from app.models.user import User
from app.schemas.script import ScriptCreate

router = APIRouter()


@router.get("")
def list_scripts(
    category: str | None = None,
    keyword: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    query = db.query(Script)
    if category:
        query = query.filter(Script.category == category)
    if keyword:
        like = f"%{keyword}%"
        query = query.filter(Script.title.like(like) | Script.content.like(like))
    total = query.count()
    items = query.order_by(Script.updated_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return {
        "items": [{"id": s.id, "title": s.title, "category": s.category, "content": s.content,
                    "created_at": s.created_at.isoformat() if s.created_at else None} for s in items],
        "total": total,
    }


@router.post("")
def create_script(
    payload: ScriptCreate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    s = Script(title=payload.title, category=payload.category, content=payload.content)
    db.add(s)
    db.commit()
    db.refresh(s)
    return {"id": s.id, "title": s.title, "category": s.category, "content": s.content}


@router.delete("/{script_id}")
def delete_script(
    script_id: int,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    s = db.get(Script, script_id)
    if s is None:
        raise HTTPException(status_code=404, detail="话术不存在")
    db.delete(s)
    db.commit()
    return {"ok": True}
