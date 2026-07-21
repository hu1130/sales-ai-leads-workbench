import asyncio
import contextlib
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.api.routes.ai_robot_calls import sync_pending_ai_robot_call_batch
from app.bootstrap import create_default_admin
from app.core.config import get_settings
from app.core.database import Base, SessionLocal, engine
from app.db_migrations import run_lightweight_migrations
from app import models

settings = get_settings()
logger = logging.getLogger(__name__)
ALIYUN_PROVIDER_NAMES = {"aliyun", "aliyun_outboundbot", "aliyun-outboundbot"}


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=settings.cors_origins != "*",
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(api_router, prefix="/api")

    @app.on_event("startup")
    async def on_startup() -> None:
        settings.upload_path.mkdir(parents=True, exist_ok=True)
        Base.metadata.create_all(bind=engine)
        run_lightweight_migrations()
        db = SessionLocal()
        try:
            create_default_admin(db)
        finally:
            db.close()
        if _should_start_ai_robot_auto_sync():
            interval = max(5, int(settings.ai_robot_auto_sync_interval_seconds or 15))
            batch_size = min(100, max(1, int(settings.ai_robot_auto_sync_batch_size or 20)))
            app.state.ai_robot_sync_task = asyncio.create_task(
                _ai_robot_auto_sync_loop(interval_seconds=interval, batch_size=batch_size)
            )
            logger.info("AI robot auto sync started: interval=%ss batch_size=%s", interval, batch_size)

    @app.on_event("shutdown")
    async def on_shutdown() -> None:
        task = getattr(app.state, "ai_robot_sync_task", None)
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()


def _should_start_ai_robot_auto_sync() -> bool:
    provider = (settings.call_provider or "").strip().lower()
    return bool(settings.ai_robot_auto_sync_enabled) and provider in ALIYUN_PROVIDER_NAMES


async def _ai_robot_auto_sync_loop(*, interval_seconds: int, batch_size: int) -> None:
    while True:
        await asyncio.to_thread(_run_ai_robot_auto_sync_once, batch_size)
        await asyncio.sleep(interval_seconds)


def _run_ai_robot_auto_sync_once(batch_size: int) -> None:
    db = SessionLocal()
    try:
        synced, errors = sync_pending_ai_robot_call_batch(db, limit=batch_size)
        if synced or errors:
            logger.info("AI robot auto sync finished: synced=%s failed=%s", len(synced), len(errors))
        for error in errors[:5]:
            logger.warning("AI robot auto sync failed: %s", error)
    except Exception:
        logger.exception("AI robot auto sync loop failed")
    finally:
        db.close()
