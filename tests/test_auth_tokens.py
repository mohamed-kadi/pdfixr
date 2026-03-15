from __future__ import annotations


def test_client_login_and_bearer_workspace_access(client):
    login = client.post(
        "/api/v1/auth/client/login",
        json={
            "email": "client@example.com",
            "access_code": "dev-local-api-key",
        },
    )
    assert login.status_code == 200, login.text
    token = login.json()["token"]

    me = client.get(
        "/api/v1/me/workspace",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me.status_code == 200, me.text
    assert me.json()["name"] == "Default Workspace"



def test_admin_login_and_bearer_admin_access(client):
    login = client.post(
        "/api/v1/auth/admin/login",
        json={
            "email": "owner@example.com",
            "admin_code": "dev-admin-key",
        },
    )
    assert login.status_code == 200, login.text
    token = login.json()["token"]

    workspaces = client.get(
        "/api/v1/workspaces",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert workspaces.status_code == 200, workspaces.text
    assert isinstance(workspaces.json(), list)



def test_invalid_tokens_are_rejected(client):
    invalid = "Bearer not-a-valid-token"

    me = client.get("/api/v1/me/workspace", headers={"Authorization": invalid})
    assert me.status_code == 401

    workspaces = client.get("/api/v1/workspaces", headers={"Authorization": invalid})
    assert workspaces.status_code == 401



def test_wrong_login_codes_are_rejected(client):
    bad_client = client.post(
        "/api/v1/auth/client/login",
        json={
            "email": "client@example.com",
            "access_code": "wrong-code",
        },
    )
    assert bad_client.status_code == 401

    bad_admin = client.post(
        "/api/v1/auth/admin/login",
        json={
            "email": "owner@example.com",
            "admin_code": "wrong-admin-code",
        },
    )
    assert bad_admin.status_code == 401
