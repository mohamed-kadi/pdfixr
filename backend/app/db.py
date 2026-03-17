from __future__ import annotations

from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

from .config import settings

sqlite_connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}

engine = create_engine(settings.database_url, future=True, connect_args=sqlite_connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def _rebuild_required_for_sqlite() -> bool:
    if not settings.database_url.startswith("sqlite"):
        return False

    inspector = inspect(engine)
    tables = set(inspector.get_table_names())

    required_tables = {"workspaces", "jobs", "workspace_usage", "billing_events", "audit_logs"}
    if tables and not required_tables.issubset(tables):
        return True

    if "jobs" in tables:
        columns = {col["name"] for col in inspector.get_columns("jobs")}
        required = {
            "workspace_id",
            "job_type",
            "job_options",
            "input_size_bytes",
            "output_size_bytes",
            "attempt_count",
            "max_attempts",
            "next_retry_at",
        }
        if not required.issubset(columns):
            return True

    if "workspaces" in tables:
        columns = {col["name"] for col in inspector.get_columns("workspaces")}
        required = {
            "billing_status",
            "stripe_customer_id",
            "stripe_subscription_id",
            "monthly_job_limit",
        }
        if not required.issubset(columns):
            return True

    if "billing_events" in tables:
        columns = {col["name"] for col in inspector.get_columns("billing_events")}
        if "provider_event_id" not in columns:
            return True

    return False


def init_db() -> None:
    from .models import Base

    if not settings.db_auto_init:
        return

    if _rebuild_required_for_sqlite():
        Base.metadata.drop_all(bind=engine)

    Base.metadata.create_all(bind=engine)
