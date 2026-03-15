from __future__ import annotations


def _login(client, *, email: str, password: str) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": email,
            "password": password,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["token"]


def _login_response(client, *, email: str, password: str):
    return client.post(
        "/api/v1/auth/login",
        json={
            "email": email,
            "password": password,
        },
    )



def test_default_client_user_can_access_workspace_endpoints(client):
    token = _login(client, email="client@local.dev", password="Client123!!")

    me = client.get("/api/v1/me/workspace", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200, me.text
    assert me.json()["name"] == "Default Workspace"



def test_default_admin_user_can_access_admin_endpoints(client):
    token = _login(client, email="admin@local.dev", password="Admin123!!")

    users = client.get("/api/v1/users", headers={"Authorization": f"Bearer {token}"})
    assert users.status_code == 200, users.text
    assert any(row["email"] == "admin@local.dev" for row in users.json())


def test_admin_can_view_auth_security_backend_status(client):
    token = _login(client, email="admin@local.dev", password="Admin123!!")
    response = client.get("/api/v1/auth/security/backend", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200, response.text

    payload = response.json()
    assert payload["configured_backend"] == "memory"
    assert payload["active_backend"] == "memory"
    assert isinstance(payload["details"], dict)



def test_client_user_cannot_access_admin_endpoints(client):
    token = _login(client, email="client@local.dev", password="Client123!!")

    denied = client.get("/api/v1/workspaces", headers={"Authorization": f"Bearer {token}"})
    assert denied.status_code == 403

    denied_security = client.get("/api/v1/auth/security/backend", headers={"Authorization": f"Bearer {token}"})
    assert denied_security.status_code == 403



def test_admin_can_create_client_user(client):
    admin_token = _login(client, email="admin@local.dev", password="Admin123!!")

    workspace_rows = client.get("/api/v1/workspaces", headers={"Authorization": f"Bearer {admin_token}"})
    assert workspace_rows.status_code == 200
    workspace_id = workspace_rows.json()[0]["id"]

    created = client.post(
        "/api/v1/users",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "email": "newclient@example.com",
            "password": "Client999!!",
            "role": "client",
            "workspace_id": workspace_id,
            "is_active": True,
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["email"] == "newclient@example.com"

    new_token = _login(client, email="newclient@example.com", password="Client999!!")
    me = client.get("/api/v1/me/workspace", headers={"Authorization": f"Bearer {new_token}"})
    assert me.status_code == 200


def test_admin_can_deactivate_user_and_block_login(client):
    admin_token = _login(client, email="admin@local.dev", password="Admin123!!")
    workspace_rows = client.get("/api/v1/workspaces", headers={"Authorization": f"Bearer {admin_token}"})
    workspace_id = workspace_rows.json()[0]["id"]

    created = client.post(
        "/api/v1/users",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "email": "disabled-user@example.com",
            "password": "Client999!!",
            "role": "client",
            "workspace_id": workspace_id,
            "is_active": True,
        },
    )
    assert created.status_code == 201, created.text
    user_id = created.json()["id"]

    updated = client.patch(
        f"/api/v1/users/{user_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "role": "client",
            "workspace_id": workspace_id,
            "is_active": False,
        },
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["is_active"] is False

    denied = _login_response(client, email="disabled-user@example.com", password="Client999!!")
    assert denied.status_code == 403


def test_admin_can_reset_user_password(client):
    admin_token = _login(client, email="admin@local.dev", password="Admin123!!")
    workspace_rows = client.get("/api/v1/workspaces", headers={"Authorization": f"Bearer {admin_token}"})
    workspace_id = workspace_rows.json()[0]["id"]

    created = client.post(
        "/api/v1/users",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "email": "reset-user@example.com",
            "password": "OldPass123!",
            "role": "client",
            "workspace_id": workspace_id,
            "is_active": True,
        },
    )
    assert created.status_code == 201, created.text
    user_id = created.json()["id"]

    reset = client.post(
        f"/api/v1/users/{user_id}/reset-password",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"new_password": "NewPass123!"},
    )
    assert reset.status_code == 200, reset.text

    old_login = _login_response(client, email="reset-user@example.com", password="OldPass123!")
    assert old_login.status_code == 401

    new_login = _login_response(client, email="reset-user@example.com", password="NewPass123!")
    assert new_login.status_code == 200


def test_last_active_admin_cannot_be_deactivated(client):
    admin_token = _login(client, email="admin@local.dev", password="Admin123!!")

    users = client.get("/api/v1/users", headers={"Authorization": f"Bearer {admin_token}"})
    assert users.status_code == 200, users.text
    admin_user = next(row for row in users.json() if row["email"] == "admin@local.dev")

    blocked = client.patch(
        f"/api/v1/users/{admin_user['id']}",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "role": "admin",
            "workspace_id": None,
            "is_active": False,
        },
    )
    assert blocked.status_code == 400
