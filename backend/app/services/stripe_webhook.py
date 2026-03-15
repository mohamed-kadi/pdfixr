from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass

from ..models import BillingStatus
from ..schemas import BillingWebhookRequest
from .plans import parse_billing_status


class StripeSignatureError(ValueError):
    pass


@dataclass(frozen=True)
class ParsedStripeSignature:
    timestamp: int
    signatures_v1: tuple[str, ...]


_EVENT_FORCE_PAST_DUE = {"invoice.payment_failed", "invoice.payment_action_required"}
_EVENT_FORCE_CANCELED = {"customer.subscription.deleted"}
_EVENT_FORCE_INACTIVE = {"customer.subscription.paused"}
_EVENT_RECOVERY_ACTIVE = {
    "invoice.paid",
    "invoice.payment_succeeded",
    "customer.subscription.resumed",
}
_EVENT_USE_OBJECT_STATUS = {
    "customer.subscription.created",
    "customer.subscription.updated",
}


def parse_stripe_signature_header(header_value: str | None) -> ParsedStripeSignature:
    if not header_value:
        raise StripeSignatureError("Missing Stripe-Signature header.")

    parts = [part.strip() for part in header_value.split(",") if part.strip()]
    timestamp = None
    signatures: list[str] = []

    for part in parts:
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        if key == "t":
            try:
                timestamp = int(value)
            except ValueError as exc:
                raise StripeSignatureError("Invalid Stripe-Signature timestamp.") from exc
        elif key == "v1":
            signatures.append(value)

    if timestamp is None or not signatures:
        raise StripeSignatureError("Stripe-Signature header missing required fields.")

    return ParsedStripeSignature(timestamp=timestamp, signatures_v1=tuple(signatures))


def verify_stripe_signature(
    *,
    payload: bytes,
    header_value: str | None,
    secret: str,
    tolerance_seconds: int,
) -> None:
    parsed = parse_stripe_signature_header(header_value)

    now = int(time.time())
    if abs(now - parsed.timestamp) > tolerance_seconds:
        raise StripeSignatureError("Stripe webhook timestamp outside allowed tolerance.")

    signed_payload = f"{parsed.timestamp}.".encode("utf-8") + payload
    expected = hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()

    if not any(hmac.compare_digest(expected, candidate) for candidate in parsed.signatures_v1):
        raise StripeSignatureError("Stripe webhook signature mismatch.")


def infer_billing_status(*, event_type: str, object_status: str | None, default: BillingStatus) -> BillingStatus:
    if event_type in _EVENT_FORCE_PAST_DUE:
        return BillingStatus.PAST_DUE
    if event_type in _EVENT_FORCE_CANCELED:
        return BillingStatus.CANCELED
    if event_type in _EVENT_FORCE_INACTIVE:
        return BillingStatus.INACTIVE
    if event_type in _EVENT_RECOVERY_ACTIVE:
        return BillingStatus.ACTIVE
    if event_type in _EVENT_USE_OBJECT_STATUS:
        return parse_billing_status(object_status)
    return default


def normalize_billing_payload(raw_payload: bytes) -> BillingWebhookRequest:
    try:
        data = json.loads(raw_payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Webhook body is not valid JSON.") from exc

    if "provider_event_id" in data:
        return BillingWebhookRequest.model_validate(data)

    # Stripe-like event envelope.
    event_id = data.get("id")
    event_type = data.get("type")
    obj = ((data.get("data") or {}).get("object") or {})
    metadata = obj.get("metadata") or {}

    workspace_id = metadata.get("workspace_id")
    plan_name = metadata.get("plan_name") or metadata.get("plan")

    monthly_job_limit = None
    raw_limit = metadata.get("monthly_job_limit")
    if raw_limit not in (None, ""):
        try:
            monthly_job_limit = int(raw_limit)
        except (TypeError, ValueError) as exc:
            raise ValueError("Invalid metadata.monthly_job_limit in Stripe payload.") from exc

    default_status = parse_billing_status(obj.get("status"))
    billing_status = infer_billing_status(
        event_type=str(event_type or ""),
        object_status=obj.get("status"),
        default=default_status,
    )

    stripe_customer_id = obj.get("customer")
    stripe_subscription_id = obj.get("id") if str(event_type).startswith("customer.subscription") else obj.get("subscription")

    if not event_id or not event_type:
        raise ValueError("Webhook payload missing required id/type fields.")

    mapped = {
        "provider_event_id": event_id,
        "event_type": event_type,
        "workspace_id": workspace_id,
        "plan_name": plan_name,
        "monthly_job_limit": monthly_job_limit,
        "billing_status": billing_status,
        "stripe_customer_id": stripe_customer_id,
        "stripe_subscription_id": stripe_subscription_id,
    }

    return BillingWebhookRequest.model_validate(mapped)
