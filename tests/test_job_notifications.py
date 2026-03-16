from __future__ import annotations

import json
import importlib
import time
from pathlib import Path

from backend.app.services.pdf_processor import PdfProcessingError


def _upload_pdf(client, input_pdf_path: Path, api_key: str = "dev-local-api-key"):
    with input_pdf_path.open("rb") as f:
        return client.post(
            "/api/v1/jobs",
            headers={"X-API-Key": api_key},
            files={"file": ("input.pdf", f, "application/pdf")},
        )


def _wait_for_job_completion(client, *, api_key: str, job_id: str, timeout_seconds: float = 6.0):
    start = time.time()
    while time.time() - start < timeout_seconds:
        r = client.get(f"/api/v1/jobs/{job_id}", headers={"X-API-Key": api_key})
        assert r.status_code == 200, r.text
        payload = r.json()
        if payload["status"] in {"completed", "failed"}:
            return payload
        time.sleep(0.1)
    raise AssertionError("Timed out waiting for job completion")


def _wait_for_job_notification(outbox_dir: Path, *, job_id: str, timeout_seconds: float = 6.0) -> dict:
    start = time.time()
    while time.time() - start < timeout_seconds:
        files = sorted(outbox_dir.glob("*.json"))
        for path in files:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload.get("type") == "job_status" and payload.get("job_id") == job_id:
                return payload
        time.sleep(0.1)
    raise AssertionError("Timed out waiting for job notification email in outbox")


def test_job_completion_writes_client_notification_email(client, input_pdf_path: Path, outbox_dir: Path):
    created = _upload_pdf(client, input_pdf_path)
    assert created.status_code == 201, created.text
    job_id = created.json()["id"]

    done = _wait_for_job_completion(client, api_key="dev-local-api-key", job_id=job_id)
    assert done["status"] == "completed"

    payload = _wait_for_job_notification(outbox_dir, job_id=job_id)
    assert payload["to"] == "client@local.dev"
    assert payload["status"] == "completed"
    assert payload["subject"] == "Your PDF is ready for download"


def test_job_failure_writes_client_notification_email(client, input_pdf_path: Path, outbox_dir: Path, monkeypatch):
    def _boom(_input_path, _output_path):
        raise PdfProcessingError("forced processing failure for test")

    jobs_service = importlib.import_module("backend.app.services.jobs")
    monkeypatch.setattr(jobs_service, "fix_pdf_file", _boom)

    created = _upload_pdf(client, input_pdf_path)
    assert created.status_code == 201, created.text
    job_id = created.json()["id"]

    done = _wait_for_job_completion(client, api_key="dev-local-api-key", job_id=job_id)
    assert done["status"] == "failed"

    payload = _wait_for_job_notification(outbox_dir, job_id=job_id)
    assert payload["to"] == "client@local.dev"
    assert payload["status"] == "failed"
    assert payload["subject"] == "Your PDF processing job needs attention"
    assert "forced processing failure for test" in (payload.get("error_message") or "")
