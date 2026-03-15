from __future__ import annotations

from datetime import date, datetime, timezone

from ..models import BillingStatus

PLAN_LIMITS: dict[str, int] = {
    "starter": 200,
    "pro": 5_000,
    "business": 25_000,
    "enterprise": 100_000,
}


def utc_today() -> date:
    return datetime.now(timezone.utc).date()


def resolve_monthly_limit(plan_name: str, explicit_limit: int | None = None) -> int:
    if explicit_limit and explicit_limit > 0:
        return explicit_limit
    return PLAN_LIMITS.get(plan_name, PLAN_LIMITS["starter"])


def period_start_utc(today: date | None = None) -> date:
    dt = today or utc_today()
    return date(dt.year, dt.month, 1)


def months_ago_start(months_ago: int, today: date | None = None) -> date:
    dt = today or utc_today()
    year = dt.year
    month = dt.month
    for _ in range(months_ago):
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    return date(year, month, 1)


def parse_billing_status(raw: str | None) -> BillingStatus:
    if not raw:
        return BillingStatus.ACTIVE

    normalized = raw.strip().lower()
    for status in BillingStatus:
        if status.value == normalized:
            return status
    return BillingStatus.ACTIVE


def is_processing_allowed_for_billing_status(status: BillingStatus) -> bool:
    return status in {BillingStatus.ACTIVE, BillingStatus.TRIALING}


def is_workspace_active_for_billing_status(status: BillingStatus) -> bool:
    return status not in {BillingStatus.CANCELED, BillingStatus.INACTIVE}


def resolve_limit_for_update(
    *,
    current_plan_name: str,
    current_monthly_limit: int,
    incoming_plan_name: str | None,
    incoming_monthly_limit: int | None,
) -> tuple[str, int]:
    plan_name = incoming_plan_name or current_plan_name

    if incoming_monthly_limit is not None:
        return plan_name, incoming_monthly_limit

    if incoming_plan_name and incoming_plan_name != current_plan_name:
        return plan_name, resolve_monthly_limit(plan_name, None)

    return plan_name, current_monthly_limit
