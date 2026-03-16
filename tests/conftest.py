from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

import pikepdf
import pytest
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture()
def client(tmp_path, monkeypatch):
    storage_root = tmp_path / "storage"
    outbox_dir = storage_root / "mail_outbox"

    monkeypatch.setenv("PDF_SAAS_STORAGE_ROOT", str(storage_root))
    monkeypatch.setenv("PDF_SAAS_REQUIRE_API_KEY", "true")
    monkeypatch.setenv("PDF_SAAS_DEFAULT_WORKSPACE_API_KEY", "dev-local-api-key")
    monkeypatch.setenv("PDF_SAAS_DEFAULT_WORKSPACE_NAME", "Default Workspace")
    monkeypatch.setenv("PDF_SAAS_DEFAULT_ADMIN_EMAIL", "admin@local.dev")
    monkeypatch.setenv("PDF_SAAS_DEFAULT_ADMIN_PASSWORD", "Admin123!!")
    monkeypatch.setenv("PDF_SAAS_DEFAULT_CLIENT_EMAIL", "client@local.dev")
    monkeypatch.setenv("PDF_SAAS_DEFAULT_CLIENT_PASSWORD", "Client123!!")
    monkeypatch.setenv("PDF_SAAS_ADMIN_API_KEY", "dev-admin-key")
    monkeypatch.setenv("PDF_SAAS_BILLING_WEBHOOK_SECRET", "dev-billing-secret")
    monkeypatch.setenv("PDF_SAAS_PASSWORD_RESET_RETURN_TOKEN", "true")
    monkeypatch.setenv("PDF_SAAS_PASSWORD_RESET_TOKEN_TTL_SECONDS", "1800")
    monkeypatch.setenv("PDF_SAAS_PASSWORD_RESET_UI_BASE_URL", "http://localhost:4200")
    monkeypatch.setenv("PDF_SAAS_EMAIL_DELIVERY_MODE", "file")
    monkeypatch.setenv("PDF_SAAS_EMAIL_OUTBOX_DIR", str(outbox_dir))
    monkeypatch.setenv("PDF_SAAS_SMTP_FROM_EMAIL", "no-reply@local.dev")
    monkeypatch.setenv("PDF_SAAS_AUTH_RATE_LIMIT_WINDOW_SECONDS", "300")
    monkeypatch.setenv("PDF_SAAS_AUTH_LOGIN_RATE_LIMIT_PER_IP", "30")
    monkeypatch.setenv("PDF_SAAS_AUTH_LOGIN_LOCKOUT_THRESHOLD", "5")
    monkeypatch.setenv("PDF_SAAS_AUTH_LOGIN_LOCKOUT_SECONDS", "900")
    monkeypatch.setenv("PDF_SAAS_AUTH_LOGIN_FAILURE_WINDOW_SECONDS", "900")
    monkeypatch.setenv("PDF_SAAS_AUTH_PASSWORD_RESET_REQUEST_RATE_LIMIT_PER_IP", "10")
    monkeypatch.setenv("PDF_SAAS_AUTH_PASSWORD_RESET_REQUEST_RATE_LIMIT_PER_EMAIL", "3")
    monkeypatch.setenv("PDF_SAAS_AUTH_PASSWORD_RESET_CONFIRM_RATE_LIMIT_PER_IP", "12")
    monkeypatch.setenv("PDF_SAAS_AUTH_SECURITY_BACKEND", "memory")
    monkeypatch.setenv("PDF_SAAS_AUTH_SECURITY_REDIS_URL", "")
    monkeypatch.setenv("PDF_SAAS_AUTH_SECURITY_REDIS_KEY_NAMESPACE", "pdfsaas:test:auth")
    monkeypatch.setenv("PDF_SAAS_DB_AUTO_INIT", "true")
    monkeypatch.setenv("PDF_SAAS_QUEUE_BACKEND", "local")

    for key in list(sys.modules.keys()):
        if key.startswith("backend.app"):
            del sys.modules[key]

    main_module = importlib.import_module("backend.app.main")
    app = main_module.app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def outbox_dir(tmp_path) -> Path:
    return tmp_path / "storage" / "mail_outbox"


@pytest.fixture()
def input_pdf_path(tmp_path) -> Path:
    path = Path(__file__).resolve().parents[1] / "input.pdf"
    if path.exists():
        return path

    generated = tmp_path / "generated_input.pdf"
    with pikepdf.Pdf.new() as pdf:
        pdf.add_blank_page(page_size=(612, 792))
        pdf.Root["/AcroForm"] = pikepdf.Dictionary(
            {
                "/Fields": pikepdf.Array(),
                "/NeedAppearances": False,
            }
        )
        pdf.save(generated)
    return generated
