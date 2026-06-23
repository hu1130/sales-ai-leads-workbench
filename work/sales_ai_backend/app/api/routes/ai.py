from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import require_admin
from app.models.user import User
from app.services.ai_service import AIService

router = APIRouter()


@router.get("/deepseek/status")
def deepseek_status(_: User = Depends(require_admin)) -> dict:
    return AIService().deepseek_status()


@router.get("/recognition/status")
def recognition_status(_: User = Depends(require_admin)) -> dict:
    return AIService().recognition_status()


@router.post("/deepseek/test")
def test_deepseek(_: User = Depends(require_admin)) -> dict:
    result = AIService().test_deepseek()
    if not result["ok"]:
        raise HTTPException(status_code=400, detail=result)
    return result
