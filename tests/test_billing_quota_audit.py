from __future__ import annotations

import hashlib
import hmac
import json
import time
from pathlib import Path


def _sign_stripe_payload(raw_body: bytes, secret: str = "dev-billing-secret") -> str:
    ts = str(int(time.time()))
    digest = hmac.new(secret.encode("utf-8"), f"{ts}.".encode("utf-8") + raw_body, hashlib.sha256).hexdigest()
    return f"t={ts},v1={digest}"


def _post_stripe_envelope(client, envelope: dict, signature_secret: str = "dev-billing-secret"):
    body = json.dumps(envelope, separators=(",", ":")).encode("utf-8")
    signature = _sign_stripe_payload(body, secret=signature_secret)
    return client.post(
        "/api/v1/billing/webhook/stripe",
        content=body,
        headers={
            "Content-Type": "application/json",
            "Stripe-Signature": signature,
        },
    )


def _create_workspace(client, *, name: str, plan_name: str = "starter", monthly_job_limit: int = 2) -> dict:
    response = client.post(
        "/api/v1/workspaces",
        headers={"X-Admin-Key": "dev-admin-key"},
        json={
            "name": name,
            "plan_name": plan_name,
            "monthly_job_limit": monthly_job_limit,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _upload_pdf(client, input_pdf_path: Path, api_key: str):
    with input_pdf_path.open("rb") as f:
        return client.post(
            "/api/v1/jobs",
            headers={"X-API-Key": api_key},
            files={"file": ("input.pdf", f, "application/pdf")},
        )


def _wait_for_job_completion(client, *, api_key: str, job_id: str, timeout_seconds: float = 5.0):
    start = time.time()
    while time.time() - start < timeout_seconds:
        r = client.get(f"/api/v1/jobs/{job_id}", headers={"X-API-Key": api_key})
        assert r.status_code == 200, r.text
        payload = r.json()
        if payload["status"] in {"completed", "failed"}:
            return payload
        time.sleep(0.1)
    raise AssertionError("Timed out waiting for job completion")


def _workspace_input_files(client, workspace_id: str) -> list[Path]:
    input_dir = Path(client.app.state.settings.input_dir) / workspace_id
    if not input_dir.exists():
        return []
    return sorted([path for path in input_dir.iterdir() if path.is_file()])


def test_stripe_event_handlers_and_workspace_resolution(client, input_pdf_path: Path):
    ws = _create_workspace(client, name="Stripe Handlers QA", monthly_job_limit=3)
    ws_id = ws["id"]
    ws_key = ws["api_key"]

    # 1) payment failed -> past_due -> processing disabled
    payment_failed_envelope = {
        "id": "evt_payment_failed_1",
        "type": "invoice.payment_failed",
        "data": {
            "object": {
                "id": "in_100",
                "customer": "cus_100",
                "subscription": "sub_100",
                "metadata": {"workspace_id": ws_id},
            }
        },
    }
    r = _post_stripe_envelope(client, payment_failed_envelope)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "processed"

    me = client.get("/api/v1/me/workspace", headers={"X-API-Key": ws_key})
    assert me.status_code == 200
    assert me.json()["billing_status"] == "past_due"

    before_blocked_files = _workspace_input_files(client, ws_id)
    blocked = _upload_pdf(client, input_pdf_path, ws_key)
    assert blocked.status_code == 402
    after_blocked_files = _workspace_input_files(client, ws_id)
    assert len(after_blocked_files) == len(before_blocked_files)
    ws_logs = client.get("/api/v1/me/audit/logs?limit=30", headers={"X-API-Key": ws_key})
    assert ws_logs.status_code == 200
    ws_actions = [row["action"] for row in ws_logs.json()["items"]]
    assert "job.rejected_billing" in ws_actions

    # 2) deleted subscription without workspace_id -> resolve workspace by subscription/customer
    deleted_envelope = {
        "id": "evt_subscription_deleted_1",
        "type": "customer.subscription.deleted",
        "data": {
            "object": {
                "id": "sub_100",
                "customer": "cus_100",
                "status": "canceled",
                "metadata": {},
            }
        },
    }
    r = _post_stripe_envelope(client, deleted_envelope)
    assert r.status_code == 200, r.text

    me = client.get("/api/v1/me/workspace", headers={"X-API-Key": ws_key})
    assert me.status_code == 200
    assert me.json()["billing_status"] == "canceled"

    blocked_canceled = _upload_pdf(client, input_pdf_path, ws_key)
    assert blocked_canceled.status_code == 402

    # 3) active subscription update -> re-enable workspace and update plan limit
    updated_envelope = {
        "id": "evt_subscription_updated_1",
        "type": "customer.subscription.updated",
        "data": {
            "object": {
                "id": "sub_100",
                "customer": "cus_100",
                "status": "active",
                "metadata": {"plan_name": "pro"},
            }
        },
    }
    r = _post_stripe_envelope(client, updated_envelope)
    assert r.status_code == 200, r.text

    me = client.get("/api/v1/me/workspace", headers={"X-API-Key": ws_key})
    assert me.status_code == 200
    me_json = me.json()
    assert me_json["billing_status"] == "active"
    assert me_json["plan_name"] == "pro"
    assert me_json["monthly_job_limit"] == 5000

    allowed = _upload_pdf(client, input_pdf_path, ws_key)
    assert allowed.status_code == 201


def test_quota_enforcement_and_audit_logs(client, input_pdf_path: Path):
    ws = _create_workspace(client, name="Quota Audit QA", monthly_job_limit=1)
    ws_id = ws["id"]
    ws_key = ws["api_key"]

    first = _upload_pdf(client, input_pdf_path, ws_key)
    assert first.status_code == 201, first.text
    job_id = first.json()["id"]

    done = _wait_for_job_completion(client, api_key=ws_key, job_id=job_id)
    assert done["status"] == "completed"

    before_second = _workspace_input_files(client, ws_id)
    second = _upload_pdf(client, input_pdf_path, ws_key)
    assert second.status_code == 429
    after_second = _workspace_input_files(client, ws_id)
    assert len(after_second) == len(before_second)

    workspace_logs = client.get("/api/v1/me/audit/logs?limit=50", headers={"X-API-Key": ws_key})
    assert workspace_logs.status_code == 200
    actions = [row["action"] for row in workspace_logs.json()["items"]]
    assert "job.created" in actions
    assert "job.rejected_quota" in actions
    assert "job.processing_started" in actions
    assert "job.completed" in actions

    admin_logs = client.get(
        f"/api/v1/audit/logs?workspace_id={ws_id}&limit=50",
        headers={"X-Admin-Key": "dev-admin-key"},
    )
    assert admin_logs.status_code == 200
    admin_actions = [row["action"] for row in admin_logs.json()["items"]]
    assert "workspace.created" in admin_actions


def test_stripe_signature_validation(client):
    # Missing/invalid signature should be rejected.
    body = {
        "id": "evt_invalid_sig",
        "type": "invoice.payment_failed",
        "data": {"object": {"id": "in_x", "metadata": {"workspace_id": "nope"}}},
    }

    bad = client.post(
        "/api/v1/billing/webhook/stripe",
        json=body,
        headers={"Stripe-Signature": "t=1,v1=deadbeef"},
    )
    assert bad.status_code == 401
    assert "Stripe webhook" in bad.json()["detail"]


def test_admin_billing_events_listing(client):
    ws = _create_workspace(client, name="Billing Events QA", monthly_job_limit=3)
    ws_id = ws["id"]

    envelope = {
        "id": "evt_admin_events_1",
        "type": "invoice.payment_failed",
        "data": {
            "object": {
                "id": "in_admin_1",
                "customer": "cus_admin_1",
                "subscription": "sub_admin_1",
                "metadata": {"workspace_id": ws_id},
            }
        },
    }
    posted = _post_stripe_envelope(client, envelope)
    assert posted.status_code == 200, posted.text

    denied = client.get("/api/v1/billing/events")
    assert denied.status_code == 401

    listed = client.get(
        "/api/v1/billing/events?limit=20",
        headers={"X-Admin-Key": "dev-admin-key"},
    )
    assert listed.status_code == 200, listed.text
    items = listed.json()["items"]
    assert any(row["provider_event_id"] == "evt_admin_events_1" for row in items)

    target = next(row for row in items if row["provider_event_id"] == "evt_admin_events_1")
    assert target["workspace_id"] == ws_id
    assert target["status"] == "processed"
