from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Protocol

from sqlalchemy.orm import sessionmaker

from .config import settings
from .services.jobs import process_job


class JobDispatcher(Protocol):
    def enqueue(self, job_id: str) -> None: ...

    def shutdown(self) -> None: ...


class LocalJobDispatcher:
    def __init__(self, session_factory: sessionmaker, worker_concurrency: int) -> None:
        self._session_factory = session_factory
        self._executor = ThreadPoolExecutor(max_workers=worker_concurrency)

    def enqueue(self, job_id: str) -> None:
        self._executor.submit(process_job, job_id, self._session_factory)

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=False)


class CeleryJobDispatcher:
    def enqueue(self, job_id: str) -> None:
        from .worker import process_job_task

        process_job_task.delay(job_id)

    def shutdown(self) -> None:
        return


def build_dispatcher(session_factory: sessionmaker) -> JobDispatcher:
    if settings.queue_backend == "celery":
        return CeleryJobDispatcher()
    return LocalJobDispatcher(session_factory, settings.worker_concurrency)
