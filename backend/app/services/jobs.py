from __future__ import annotations

from sqlalchemy.orm import sessionmaker

from ..config import settings
from ..models import Job, JobStatus
from ..repository import AuditRepository, JobRepository, UserRepository
from .mailer import JobStatusEmail, build_job_notification_mailer
from .pdf_processor import PdfProcessingError, fix_pdf_file
from .storage import StorageError, build_storage_backend


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


def process_job(job_id: str, session_factory: sessionmaker) -> None:
    storage = build_storage_backend(settings)
    job_mailer = build_job_notification_mailer(settings)
    with session_factory() as session:
        repo = JobRepository(session)
        audit_repo = AuditRepository(session)
        users = UserRepository(session)
        job = repo.update_status(job_id, status=JobStatus.PROCESSING, error_message=None)
        if not job:
            return

        audit_repo.create(
            actor_type="system_worker",
            actor_id="worker",
            action="job.processing_started",
            resource_type="job",
            resource_id=job.id,
            workspace_id=job.workspace_id,
            details={"input_path": job.input_path},
        )

        output_stage_dir = settings.storage_root / "tmp" / "worker_outputs" / job.workspace_id
        output_stage_dir.mkdir(parents=True, exist_ok=True)
        output_stage_path = output_stage_dir / f"{job.id}_fixed.pdf"

        try:
            with storage.materialize_input(job.input_path) as input_path:
                fix_pdf_file(input_path, output_stage_path)
            output_reference = storage.stage_output_file(
                workspace_id=job.workspace_id,
                job_id=job.id,
                local_source_path=output_stage_path,
            )
            completed = repo.update_status(
                job.id,
                status=JobStatus.COMPLETED,
                output_path=output_reference,
                error_message=None,
            )
            audit_repo.create(
                actor_type="system_worker",
                actor_id="worker",
                action="job.completed",
                resource_type="job",
                resource_id=job.id,
                workspace_id=job.workspace_id,
                details={"output_path": output_reference},
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
            failed = repo.update_status(job.id, status=JobStatus.FAILED, error_message=f"Storage error: {exc}")
            audit_repo.create(
                actor_type="system_worker",
                actor_id="worker",
                action="job.failed",
                resource_type="job",
                resource_id=job.id,
                workspace_id=job.workspace_id,
                details={"error": f"Storage error: {exc}"},
            )
            if failed:
                _notify_workspace_clients(
                    users=users,
                    audit_repo=audit_repo,
                    job_mailer=job_mailer,
                    job=failed,
                    status=JobStatus.FAILED,
                    error_message=f"Storage error: {exc}",
                )
        except PdfProcessingError as exc:
            failed = repo.update_status(job.id, status=JobStatus.FAILED, error_message=str(exc))
            audit_repo.create(
                actor_type="system_worker",
                actor_id="worker",
                action="job.failed",
                resource_type="job",
                resource_id=job.id,
                workspace_id=job.workspace_id,
                details={"error": str(exc)},
            )
            if failed:
                _notify_workspace_clients(
                    users=users,
                    audit_repo=audit_repo,
                    job_mailer=job_mailer,
                    job=failed,
                    status=JobStatus.FAILED,
                    error_message=str(exc),
                )
        except Exception as exc:  # pragma: no cover - unexpected guardrail
            failed = repo.update_status(job.id, status=JobStatus.FAILED, error_message=f"Unhandled error: {exc}")
            audit_repo.create(
                actor_type="system_worker",
                actor_id="worker",
                action="job.failed",
                resource_type="job",
                resource_id=job.id,
                workspace_id=job.workspace_id,
                details={"error": f"Unhandled error: {exc}"},
            )
            if failed:
                _notify_workspace_clients(
                    users=users,
                    audit_repo=audit_repo,
                    job_mailer=job_mailer,
                    job=failed,
                    status=JobStatus.FAILED,
                    error_message=f"Unhandled error: {exc}",
                )
