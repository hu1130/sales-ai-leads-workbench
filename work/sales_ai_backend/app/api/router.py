from fastapi import APIRouter

from app.api.routes import ai, ai_robot_calls, auth, call_center, call_provider_config, call_recordings, customers, dashboard, integrations, leads, sales_callbacks, uploads, users
from app.api.routes import quotations, scripts

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(ai.router, prefix="/ai", tags=["ai"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(uploads.router, prefix="/uploads", tags=["uploads"])
api_router.include_router(customers.router, prefix="/customers", tags=["customers"])
api_router.include_router(leads.router, prefix="/leads", tags=["leads"])
api_router.include_router(call_recordings.router, prefix="/call-recordings", tags=["call-recordings"])
api_router.include_router(call_center.router, tags=["call-center"])
api_router.include_router(call_provider_config.router)
api_router.include_router(integrations.router)
api_router.include_router(ai_robot_calls.router, tags=["ai-robot-calls"])
api_router.include_router(sales_callbacks.router, tags=["sales-callbacks"])
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
api_router.include_router(quotations.router, prefix="/quotations", tags=["quotations"])
api_router.include_router(scripts.router, prefix="/scripts", tags=["scripts"])
