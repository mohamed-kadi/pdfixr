from __future__ import annotations


def test_login_lockout_after_repeated_failures(client):
    for _ in range(4):
        response = client.post(
            "/api/v1/auth/login",
            json={
                "email": "client@local.dev",
                "password": "WrongPass123!",
            },
        )
        assert response.status_code == 401, response.text

    locked = client.post(
        "/api/v1/auth/login",
        json={
            "email": "client@local.dev",
            "password": "WrongPass123!",
        },
    )
    assert locked.status_code == 429, locked.text
    assert "Retry-After" in locked.headers

    blocked_even_with_valid_password = client.post(
        "/api/v1/auth/login",
        json={
            "email": "client@local.dev",
            "password": "Client123!!",
        },
    )
    assert blocked_even_with_valid_password.status_code == 429, blocked_even_with_valid_password.text


def test_password_reset_request_is_rate_limited_per_email(client):
    for _ in range(3):
        response = client.post(
            "/api/v1/auth/password-reset/request",
            json={"email": "client@local.dev"},
        )
        assert response.status_code == 200, response.text

    limited = client.post(
        "/api/v1/auth/password-reset/request",
        json={"email": "client@local.dev"},
    )
    assert limited.status_code == 429, limited.text
    assert "Retry-After" in limited.headers


def test_password_reset_confirm_is_rate_limited_per_ip(client):
    for _ in range(12):
        response = client.post(
            "/api/v1/auth/password-reset/confirm",
            json={
                "token": "x" * 48,
                "new_password": "Anything123!",
            },
        )
        assert response.status_code == 401, response.text

    limited = client.post(
        "/api/v1/auth/password-reset/confirm",
        json={
            "token": "x" * 48,
            "new_password": "Anything123!",
        },
    )
    assert limited.status_code == 429, limited.text
    assert "Retry-After" in limited.headers
