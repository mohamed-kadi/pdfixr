from __future__ import annotations

import io
import time
from pathlib import Path

import pikepdf


def _upload_pdf(client, input_pdf_path: Path, *, api_key: str = "dev-local-api-key", job_type: str | None = None):
    with input_pdf_path.open("rb") as f:
        data = {"job_type": job_type} if job_type else None
        return client.post(
            "/api/v1/jobs",
            headers={"X-API-Key": api_key},
            data=data,
            files={"file": ("input.pdf", f, "application/pdf")},
        )


def _upload_merge_pdfs(client, input_pdf_path: Path, *, count: int = 2, api_key: str = "dev-local-api-key"):
    handles = [input_pdf_path.open("rb") for _ in range(count)]
    payload = [
        (
            "files",
            (f"input_{idx + 1}.pdf", handle, "application/pdf"),
        )
        for idx, handle in enumerate(handles)
    ]
    try:
        return client.post(
            "/api/v1/jobs",
            headers={"X-API-Key": api_key},
            data={"job_type": "merge"},
            files=payload,
        )
    finally:
        for handle in handles:
            handle.close()


def _wait_for_terminal_status(client, *, api_key: str, job_id: str, timeout_seconds: float = 10.0) -> dict:
    start = time.time()
    while time.time() - start < timeout_seconds:
        response = client.get(f"/api/v1/jobs/{job_id}", headers={"X-API-Key": api_key})
        assert response.status_code == 200, response.text
        payload = response.json()
        if payload["status"] in {"completed", "failed"}:
            return payload
        time.sleep(0.1)
    raise AssertionError("Timed out waiting for terminal job status")


def test_default_job_type_is_font_fix(client, input_pdf_path: Path):
    created = _upload_pdf(client, input_pdf_path)
    assert created.status_code == 201, created.text
    payload = created.json()
    assert payload["job_type"] == "font_fix"


def test_compress_job_type_completes_and_downloads_pdf(client, input_pdf_path: Path):
    created = _upload_pdf(client, input_pdf_path, job_type="compress")
    assert created.status_code == 201, created.text
    job_id = created.json()["id"]

    done = _wait_for_terminal_status(client, api_key="dev-local-api-key", job_id=job_id)
    assert done["status"] == "completed"
    assert done["job_type"] == "compress"
    assert done["attempt_count"] >= 1
    assert done["input_size_bytes"] is not None
    assert done["output_size_bytes"] is not None
    assert done["size_reduction_percent"] is not None

    downloaded = client.get(f"/api/v1/jobs/{job_id}/download", headers={"X-API-Key": "dev-local-api-key"})
    assert downloaded.status_code == 200, downloaded.text

    with pikepdf.open(io.BytesIO(downloaded.content)) as pdf:
        assert len(pdf.pages) >= 1


def test_merge_job_type_completes_and_downloads_pdf(client, input_pdf_path: Path):
    with pikepdf.open(input_pdf_path) as source:
        source_pages = len(source.pages)

    created = _upload_merge_pdfs(client, input_pdf_path, count=2)
    assert created.status_code == 201, created.text
    job_id = created.json()["id"]

    done = _wait_for_terminal_status(client, api_key="dev-local-api-key", job_id=job_id)
    assert done["status"] == "completed"
    assert done["job_type"] == "merge"
    assert done["input_size_bytes"] is not None
    assert done["output_size_bytes"] is not None

    downloaded = client.get(f"/api/v1/jobs/{job_id}/download", headers={"X-API-Key": "dev-local-api-key"})
    assert downloaded.status_code == 200, downloaded.text

    with pikepdf.open(io.BytesIO(downloaded.content)) as merged:
        assert len(merged.pages) == source_pages * 2


def test_invalid_job_type_is_rejected(client, input_pdf_path: Path):
    created = _upload_pdf(client, input_pdf_path, job_type="unknown")
    assert created.status_code == 422


def test_compress_job_accepts_linearize_option(client, input_pdf_path: Path):
    with input_pdf_path.open("rb") as f:
        response = client.post(
            "/api/v1/jobs",
            headers={"X-API-Key": "dev-local-api-key"},
            data={"job_type": "compress", "job_options": '{"linearize":true}'},
            files={"file": ("input.pdf", f, "application/pdf")},
        )
    assert response.status_code == 201, response.text
    assert response.json()["job_type"] == "compress"


def test_font_fix_rejects_non_empty_job_options(client, input_pdf_path: Path):
    with input_pdf_path.open("rb") as f:
        response = client.post(
            "/api/v1/jobs",
            headers={"X-API-Key": "dev-local-api-key"},
            data={"job_type": "font_fix", "job_options": '{"linearize":true}'},
            files={"file": ("input.pdf", f, "application/pdf")},
        )
    assert response.status_code == 400
    assert "job_options are not supported" in response.json()["detail"]


def test_merge_requires_multiple_files(client, input_pdf_path: Path):
    created = _upload_pdf(client, input_pdf_path, job_type="merge")
    assert created.status_code == 400
    assert "at least 2 PDF files" in created.json()["detail"]


def test_merge_rejects_non_empty_job_options(client, input_pdf_path: Path):
    handles = [input_pdf_path.open("rb"), input_pdf_path.open("rb")]
    payload = [
        ("files", ("first.pdf", handles[0], "application/pdf")),
        ("files", ("second.pdf", handles[1], "application/pdf")),
    ]
    try:
        response = client.post(
            "/api/v1/jobs",
            headers={"X-API-Key": "dev-local-api-key"},
            data={"job_type": "merge", "job_options": '{"foo":"bar"}'},
            files=payload,
        )
    finally:
        for handle in handles:
            handle.close()

    assert response.status_code == 400
    assert "job_options are not supported for job_type=merge yet." == response.json()["detail"]
