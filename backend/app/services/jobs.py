from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy.orm import sessionmaker

from ..config import settings
from ..models import Job, JobStatus, JobType
from ..repository import AuditRepository, JobRepository, UserRepository
from .mailer import JobStatusEmail, build_job_notification_mailer
from .pdf_processor import PdfProcessingError, compress_pdf_file, fix_pdf_file
from .storage import StorageError, build_storage_backend


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _notify_workspace_clients(
    *,
    users: UserRepository,
    audit_repo: AuditRepository,
    job_mailer,
    job: Job,
    status: JobStatus,
    error_message: str | None = None,
) -> None:
    recipients = users.list_active_clients_for_workspace(workspace_id=job.workspace_id)
    for recipient in recipients:
        try:
            job_mailer.send_job_status_email(
                JobStatusEmail(
                    to_email=recipient.email,
                    workspace_id=job.workspace_id,
                    job_id=job.id,
                    original_filename=job.original_filename,
                    status=status.value,
                    error_message=error_message,
                )
            )
            audit_repo.create(
                actor_type="system",
                actor_id="mailer",
                action="job.notification_sent",
                resource_type="job",
                resource_id=job.id,
                workspace_id=job.workspace_id,
                details={"email": recipient.email, "status": status.value},
            )
        except Exception as exc:  # pragma: no cover - transport/runtime issues
            audit_repo.create(
                actor_type="system",
                actor_id="mailer",
                action="job.notification_failed",
                resource_type="job",
                resource_id=job.id,
                workspace_id=job.workspace_id,
                details={"email": recipient.email, "status": status.value, "error": str(exc)},
            )


def _calculate_retry_delay_seconds(attempt_count: int) -> int:
    base = max(1, settings.job_retry_base_delay_seconds)
    exponent = max(0, attempt_count - 1)
    return min(3600, base * (2**exponent))


def _output_suffix_for_job_type(job_type: str) -> str:
    if job_type == JobType.FONT_FIX.value:
        return "fixed"
    if job_type == JobType.COMPRESS.value:
        return "compressed"
    return "processed"


def _process_pdf_job(job: Job, input_path, output_path) -> None:
    options: dict[str, object] = {}
    if job.job_options:
        try:
            parsed = json.loads(job.job_options)
        except json.JSONDecodeError:
            parsed = {}
        if isinstance(parsed, dict):
            options = parsed

    if job.job_type == JobType.FONT_FIX.value:
        fix_pdf_file(input_path, output_path)
        return
    if job.job_type == JobType.COMPRESS.value:
        compress_pdf_file(
            input_path,
            output_path,
            linearize=bool(options.get("linearize", False)),
        )
        return
    raise PdfProcessingError(f"Unsupported job type: {job.job_type}")


def _handle_attempt_failure(
    *,
    repo: JobRepository,
    audit_repo: AuditRepository,
    users: UserRepository,
    job_mailer,
    job: Job,
    error_message: str,
) -> None:
    attempt_error = f"Attempt {job.attempt_count}/{job.max_attempts} failed: {error_message}"

    if job.attempt_count < job.max_attempts:
        delay_seconds = _calculate_retry_delay_seconds(job.attempt_count)
        retry_job = repo.schedule_retry(
            job.id,
            error_message=attempt_error,
            delay_seconds=delay_seconds,
        )
        audit_repo.create(
            actor_type="system_worker",
            actor_id="worker",
            action="job.retry_scheduled",
            resource_type="job",
            resource_id=job.id,
            workspace_id=job.workspace_id,
            details={
                "attempt_count": job.attempt_count,
                "max_attempts": job.max_attempts,
                "delay_seconds": delay_seconds,
                "next_retry_at": (
                    retry_job.next_retry_at.isoformat()
                    if retry_job and retry_job.next_retry_at
                    else (_utc_now().isoformat())
                ),
                "error": error_message,
                "job_type": job.job_type,
            },
        )
        return

    failed = repo.update_status(
        job.id,
        status=JobStatus.FAILED,
        error_message=attempt_error,
        set_next_retry_at=True,
        next_retry_at=None,
    )
    audit_repo.create(
        actor_type="system_worker",
        actor_id="worker",
        action="job.failed",
        resource_type="job",
        resource_id=job.id,
        workspace_id=job.workspace_id,
        details={
            "attempt_count": job.attempt_count,
            "max_attempts": job.max_attempts,
            "error": error_message,
            "job_type": job.job_type,
        },
    )
    if failed:
        _notify_workspace_clients(
            users=users,
            audit_repo=audit_repo,
            job_mailer=job_mailer,
            job=failed,
            status=JobStatus.FAILED,
            error_message=attempt_error,
        )


def process_job(job_id: str, session_factory: sessionmaker) -> None:
    storage = build_storage_backend(settings)
    job_mailer = build_job_notification_mailer(settings)
    with session_factory() as session:
        repo = JobRepository(session)
        audit_repo = AuditRepository(session)
        users = UserRepository(session)
        job = repo.mark_processing_attempt(job_id)
        if not job:
            return

        audit_repo.create(
            actor_type="system_worker",
            actor_id="worker",
            action="job.processing_started",
            resource_type="job",
            resource_id=job.id,
            workspace_id=job.workspace_id,
            details={
                "input_path": job.input_path,
                "attempt_count": job.attempt_count,
                "max_attempts": job.max_attempts,
                "job_type": job.job_type,
            },
        )

        output_stage_dir = settings.storage_root / "tmp" / "worker_outputs" / job.workspace_id
        output_stage_dir.mkdir(parents=True, exist_ok=True)
        output_stage_path = output_stage_dir / f"{job.id}_{_output_suffix_for_job_type(job.job_type)}.pdf"

        try:
            with storage.materialize_input(job.input_path) as input_path:
                _process_pdf_job(job, input_path, output_stage_path)
            output_size_bytes = output_stage_path.stat().st_size if output_stage_path.exists() else None
            output_reference = storage.stage_output_file(
                workspace_id=job.workspace_id,
                job_id=job.id,
                local_source_path=output_stage_path,
            )
            completed = repo.update_status(
                job.id,
                status=JobStatus.COMPLETED,
                output_path=output_reference,
                output_size_bytes=output_size_bytes,
                error_message=None,
                set_next_retry_at=True,
                next_retry_at=None,
            )
            audit_repo.create(
                actor_type="system_worker",
                actor_id="worker",
                action="job.completed",
                resource_type="job",
                resource_id=job.id,
                workspace_id=job.workspace_id,
                details={"output_path": output_reference, "job_type": job.job_type},
            )
            if completed:
                _notify_workspace_clients(
                    users=users,
                    audit_repo=audit_repo,
                    job_mailer=job_mailer,
                    job=completed,
                    status=JobStatus.COMPLETED,
                )
        except StorageError as exc:
            _handle_attempt_failure(
                repo=repo,
                audit_repo=audit_repo,
                users=users,
                job_mailer=job_mailer,
                job=job,
                error_message=f"Storage error: {exc}",
            )
        except PdfProcessingError as exc:
            _handle_attempt_failure(
                repo=repo,
                audit_repo=audit_repo,
                users=users,
                job_mailer=job_mailer,
                job=job,
                error_message=str(exc),
            )
        except Exception as exc:  # pragma: no cover - unexpected guardrail
            _handle_attempt_failure(
                repo=repo,
                audit_repo=audit_repo,
                users=users,
                job_mailer=job_mailer,
                job=job,
                error_message=f"Unhandled error: {exc}",
            )
