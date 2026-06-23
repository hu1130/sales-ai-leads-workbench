from fastapi import APIRouter

from app.api.routes import ai, auth, call_recordings, customers, dashboard, leads, uploads, users

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(ai.router, prefix="/ai", tags=["ai"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(uploads.router, prefix="/uploads", tags=["uploads"])
api_router.include_router(customers.router, prefix="/customers", tags=["customers"])
api_router.include_router(leads.router, prefix="/leads", tags=["leads"])
api_router.include_router(call_recordings.router, prefix="/call-recordings", tags=["call-recordings"])
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
