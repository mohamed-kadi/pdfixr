from __future__ import annotations

from sqlalchemy.orm import sessionmaker

from ..config import settings
from ..models import JobStatus
from ..repository import AuditRepository, JobRepository
from .pdf_processor import PdfProcessingError, fix_pdf_file
from .storage import StorageError, build_storage_backend


def process_job(job_id: str, session_factory: sessionmaker) -> None:
    storage = build_storage_backend(settings)
    with session_factory() as session:
        repo = JobRepository(session)
        audit_repo = AuditRepository(session)
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
            repo.update_status(
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
        except StorageError as exc:
            repo.update_status(job.id, status=JobStatus.FAILED, error_message=f"Storage error: {exc}")
            audit_repo.create(
                actor_type="system_worker",
                actor_id="worker",
                action="job.failed",
                resource_type="job",
                resource_id=job.id,
                workspace_id=job.workspace_id,
                details={"error": f"Storage error: {exc}"},
            )
        except PdfProcessingError as exc:
            repo.update_status(job.id, status=JobStatus.FAILED, error_message=str(exc))
            audit_repo.create(
                actor_type="system_worker",
                actor_id="worker",
                action="job.failed",
                resource_type="job",
                resource_id=job.id,
                workspace_id=job.workspace_id,
                details={"error": str(exc)},
            )
        except Exception as exc:  # pragma: no cover - unexpected guardrail
            repo.update_status(job.id, status=JobStatus.FAILED, error_message=f"Unhandled error: {exc}")
            audit_repo.create(
                actor_type="system_worker",
                actor_id="worker",
                action="job.failed",
                resource_type="job",
                resource_id=job.id,
                workspace_id=job.workspace_id,
                details={"error": f"Unhandled error: {exc}"},
            )
