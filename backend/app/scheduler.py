from __future__ import annotations

import threading
from typing import Protocol

from sqlalchemy.orm import sessionmaker

from .config import settings
from .repository import AuditRepository, JobRepository, UsageRepository, WorkspaceRepository
from .services.plans import months_ago_start, period_start_utc


class QuotaResetScheduler:
    def __init__(self, session_factory: sessionmaker, interval_seconds: int) -> None:
        self._session_factory = session_factory
        self._interval_seconds = interval_seconds
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="quota-reset-scheduler")

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread.is_alive():
            self._thread.join(timeout=2)

    def run_once(self) -> None:
        period_start = period_start_utc()
        cleanup_cutoff = months_ago_start(settings.usage_retention_months)

        with self._session_factory() as session:
            workspace_repo = WorkspaceRepository(session)
            usage_repo = UsageRepository(session)

            workspace_ids = [workspace.id for workspace in workspace_repo.list_active()]
            usage_repo.ensure_period_rows(workspace_ids=workspace_ids, period_start=period_start)
            usage_repo.cleanup_before(cutoff=cleanup_cutoff)

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.run_once()
            except Exception:
                # Do not crash the server process if scheduler work fails.
                pass
            self._stop_event.wait(self._interval_seconds)


class JobEnqueuer(Protocol):
    def enqueue(self, job_id: str) -> None: ...


class RetryJobScheduler:
    def __init__(
        self,
        session_factory: sessionmaker,
        job_dispatcher: JobEnqueuer,
        *,
        interval_seconds: int,
        batch_size: int,
    ) -> None:
        self._session_factory = session_factory
        self._job_dispatcher = job_dispatcher
        self._interval_seconds = max(1, interval_seconds)
        self._batch_size = max(1, batch_size)
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="retry-job-scheduler")

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread.is_alive():
            self._thread.join(timeout=2)

    def run_once(self) -> None:
        with self._session_factory() as session:
            job_repo = JobRepository(session)
            audit_repo = AuditRepository(session)
            ready_jobs = job_repo.list_and_claim_ready_retries(limit=self._batch_size)
            for job in ready_jobs:
                try:
                    self._job_dispatcher.enqueue(job.id)
                    audit_repo.create(
                        actor_type="system_scheduler",
                        actor_id="retry_scheduler",
                        action="job.retry_enqueued",
                        resource_type="job",
                        resource_id=job.id,
                        workspace_id=job.workspace_id,
                        details={"attempt_count": job.attempt_count, "max_attempts": job.max_attempts},
                    )
                except Exception as exc:
                    job_repo.schedule_retry(
                        job.id,
                        error_message=f"Retry dispatch failed: {exc}",
                        delay_seconds=self._interval_seconds,
                    )
                    audit_repo.create(
                        actor_type="system_scheduler",
                        actor_id="retry_scheduler",
                        action="job.retry_dispatch_failed",
                        resource_type="job",
                        resource_id=job.id,
                        workspace_id=job.workspace_id,
                        details={"error": str(exc)},
                    )

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.run_once()
            except Exception:
                # Do not crash the server process if scheduler work fails.
                pass
            self._stop_event.wait(self._interval_seconds)
