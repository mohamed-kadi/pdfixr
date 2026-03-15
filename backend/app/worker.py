from __future__ import annotations

from celery import Celery

from .config import settings
from .db import SessionLocal
from .services.jobs import process_job

celery_app = Celery(
    "pdf_form_saas",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

celery_app.conf.task_default_queue = "pdf_jobs"
celery_app.conf.task_serializer = "json"
celery_app.conf.result_serializer = "json"
celery_app.conf.accept_content = ["json"]
celery_app.conf.timezone = "UTC"


@celery_app.task(name="backend.app.worker.process_job_task")
def process_job_task(job_id: str) -> None:
    process_job(job_id, SessionLocal)
