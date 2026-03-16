from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.routes import router
from .bootstrap import ensure_bootstrap
from .config import settings
from .db import SessionLocal, init_db
from .queueing import build_dispatcher
from .scheduler import QuotaResetScheduler, RetryJobScheduler
from .services.auth_security import build_auth_security
from .services.mailer import build_job_notification_mailer, build_password_reset_mailer
from .services.storage import build_storage_backend


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.storage_root.mkdir(parents=True, exist_ok=True)
    settings.input_dir.mkdir(parents=True, exist_ok=True)
    settings.output_dir.mkdir(parents=True, exist_ok=True)
    settings.email_outbox_dir.mkdir(parents=True, exist_ok=True)

    init_db()
    ensure_bootstrap(SessionLocal)

    app.state.settings = settings
    app.state.session_factory = SessionLocal
    app.state.job_dispatcher = build_dispatcher(SessionLocal)
    app.state.storage = build_storage_backend(settings)
    app.state.password_reset_mailer = build_password_reset_mailer(settings)
    app.state.job_notification_mailer = build_job_notification_mailer(settings)
    app.state.auth_security = build_auth_security(settings)
    app.state.quota_scheduler = QuotaResetScheduler(
        SessionLocal,
        interval_seconds=settings.quota_scheduler_interval_seconds,
    )
    app.state.retry_scheduler = RetryJobScheduler(
        SessionLocal,
        app.state.job_dispatcher,
        interval_seconds=settings.retry_scheduler_interval_seconds,
        batch_size=settings.retry_scheduler_batch_size,
    )
    app.state.quota_scheduler.start()
    app.state.retry_scheduler.start()

    yield

    app.state.retry_scheduler.stop()
    app.state.job_dispatcher.shutdown()
    app.state.quota_scheduler.stop()


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.include_router(router, prefix=settings.api_prefix)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.frontend_cors_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def root() -> dict[str, str]:
    return {
        "service": settings.app_name,
        "status": "ok",
        "docs": "/docs",
        "api_prefix": settings.api_prefix,
    }
