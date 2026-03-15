from __future__ import annotations

import json
from urllib.parse import parse_qs, urlparse


def _login_response(client, *, email: str, password: str):
    return client.post(
        "/api/v1/auth/login",
        json={
            "email": email,
            "password": password,
        },
    )


def test_password_reset_request_returns_token_for_known_user(client):
    response = client.post(
        "/api/v1/auth/password-reset/request",
        json={"email": "client@local.dev"},
    )
    assert response.status_code == 200, response.text

    payload = response.json()
    assert payload["status"] == "accepted"
    assert isinstance(payload["reset_token"], str)
    assert payload["reset_token"]
    assert payload["expires_at"] is not None


def test_password_reset_request_writes_reset_email_to_outbox(client, outbox_dir):
    response = client.post(
        "/api/v1/auth/password-reset/request",
        json={"email": "client@local.dev"},
    )
    assert response.status_code == 200, response.text

    files = sorted(outbox_dir.glob("*.json"))
    assert files, "Expected at least one outbox email file."

    latest = json.loads(files[-1].read_text(encoding="utf-8"))
    assert latest["type"] == "password_reset"
    assert latest["to"] == "client@local.dev"
    assert latest["from"] == "no-reply@local.dev"
    assert "/reset-password?token=" in latest["reset_url"]
    parsed = urlparse(latest["reset_url"])
    token = parse_qs(parsed.query).get("token", [""])[0]
    assert token


def test_password_reset_request_unknown_user_is_generic(client):
    response = client.post(
        "/api/v1/auth/password-reset/request",
        json={"email": "does-not-exist@example.com"},
    )
    assert response.status_code == 200, response.text

    payload = response.json()
    assert payload["status"] == "accepted"
    assert payload["reset_token"] is None


def test_password_reset_confirm_updates_password_and_invalidates_token(client):
    request_reset = client.post(
        "/api/v1/auth/password-reset/request",
        json={"email": "client@local.dev"},
    )
    assert request_reset.status_code == 200, request_reset.text
    token = request_reset.json()["reset_token"]
    assert token

    confirm = client.post(
        "/api/v1/auth/password-reset/confirm",
        json={
            "token": token,
            "new_password": "Client456!!",
        },
    )
    assert confirm.status_code == 200, confirm.text

    old_login = _login_response(client, email="client@local.dev", password="Client123!!")
    assert old_login.status_code == 401

    new_login = _login_response(client, email="client@local.dev", password="Client456!!")
    assert new_login.status_code == 200

    reused = client.post(
        "/api/v1/auth/password-reset/confirm",
        json={
            "token": token,
            "new_password": "Client789!!",
        },
    )
    assert reused.status_code == 401


def test_password_reset_confirm_rejects_bad_token(client):
    response = client.post(
        "/api/v1/auth/password-reset/confirm",
        json={
            "token": "x" * 48,
            "new_password": "Whatever123!",
        },
    )
    assert response.status_code == 401
