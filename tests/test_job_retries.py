from __future__ import annotations

import importlib
import time
from pathlib import Path

from backend.app.services.pdf_processor import PdfProcessingError, fix_pdf_file as real_fix_pdf_file


def _upload_pdf(client, input_pdf_path: Path, api_key: str = "dev-local-api-key"):
    with input_pdf_path.open("rb") as f:
        return client.post(
            "/api/v1/jobs",
            headers={"X-API-Key": api_key},
            files={"file": ("input.pdf", f, "application/pdf")},
        )


def _wait_for_terminal_status(client, *, api_key: str, job_id: str, timeout_seconds: float = 20.0) -> dict:
    start = time.time()
    while time.time() - start < timeout_seconds:
        response = client.get(f"/api/v1/jobs/{job_id}", headers={"X-API-Key": api_key})
        assert response.status_code == 200, response.text
        payload = response.json()
        if payload["status"] in {"completed", "failed"}:
            return payload
        time.sleep(0.1)
    raise AssertionError("Timed out waiting for terminal job status")


def _job_audit_rows(client, *, job_id: str, api_key: str = "dev-local-api-key") -> list[dict]:
    response = client.get("/api/v1/me/audit/logs?limit=200", headers={"X-API-Key": api_key})
    assert response.status_code == 200, response.text
    items = response.json()["items"]
    return [row for row in items if row.get("resource_id") == job_id]


def test_transient_processing_failure_retries_and_completes(client, input_pdf_path: Path, monkeypatch):
    state = {"calls": 0}

    def _flaky_fix(input_path, output_path):
        state["calls"] += 1
        if state["calls"] == 1:
            raise PdfProcessingError("transient test failure")
        return real_fix_pdf_file(input_path, output_path)

    jobs_service = importlib.import_module("backend.app.services.jobs")
    monkeypatch.setattr(jobs_service, "fix_pdf_file", _flaky_fix)

    created = _upload_pdf(client, input_pdf_path)
    assert created.status_code == 201, created.text
    job_id = created.json()["id"]

    done = _wait_for_terminal_status(client, api_key="dev-local-api-key", job_id=job_id)
    assert done["status"] == "completed"
    assert done["attempt_count"] == 2
    assert done["max_attempts"] == 3
    assert done["next_retry_at"] is None

    rows = _job_audit_rows(client, job_id=job_id)
    actions = [row["action"] for row in rows]
    assert "job.retry_scheduled" in actions
    assert "job.retry_enqueued" in actions
    assert "job.completed" in actions


def test_processing_failure_exhausts_retries_then_fails(client, input_pdf_path: Path, monkeypatch):
    def _always_fail(_input_path, _output_path):
        raise PdfProcessingError("permanent test failure")

    jobs_service = importlib.import_module("backend.app.services.jobs")
    monkeypatch.setattr(jobs_service, "fix_pdf_file", _always_fail)

    created = _upload_pdf(client, input_pdf_path)
    assert created.status_code == 201, created.text
    job_id = created.json()["id"]

    done = _wait_for_terminal_status(client, api_key="dev-local-api-key", job_id=job_id)
    assert done["status"] == "failed"
    assert done["attempt_count"] == done["max_attempts"] == 3
    assert "Attempt 3/3 failed" in (done.get("error_message") or "")
    assert done["next_retry_at"] is None

    rows = _job_audit_rows(client, job_id=job_id)
    actions = [row["action"] for row in rows]
    assert actions.count("job.retry_scheduled") >= 2
    assert "job.failed" in actions
