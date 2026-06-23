from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.bootstrap import create_default_admin
from app.core.config import get_settings
from app.core.database import Base, SessionLocal, engine
from app.db_migrations import run_lightweight_migrations
from app import models

settings = get_settings()


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
    def on_startup() -> None:
        settings.upload_path.mkdir(parents=True, exist_ok=True)
        Base.metadata.create_all(bind=engine)
        run_lightweight_migrations()
        db = SessionLocal()
        try:
            create_default_admin(db)
        finally:
            db.close()

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
