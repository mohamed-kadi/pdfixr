"""initial schema

Revision ID: 20260314_000001
Revises: 
Create Date: 2026-03-14 00:00:01

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260314_000001"
down_revision = None
branch_labels = None
depends_on = None


job_status_enum = sa.Enum("queued", "processing", "completed", "failed", name="job_status")
billing_status_enum = sa.Enum("trialing", "active", "past_due", "canceled", "inactive", name="billing_status")
billing_event_status_enum = sa.Enum("received", "processed", "ignored", "failed", name="billing_event_status")


def upgrade() -> None:
    bind = op.get_bind()
    job_status_enum.create(bind, checkfirst=True)
    billing_status_enum.create(bind, checkfirst=True)
    billing_event_status_enum.create(bind, checkfirst=True)

    op.create_table(
        "workspaces",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("api_key_hash", sa.String(length=128), nullable=False),
        sa.Column("api_key_prefix", sa.String(length=16), nullable=False),
        sa.Column("plan_name", sa.String(length=64), nullable=False),
        sa.Column("monthly_job_limit", sa.Integer(), nullable=False),
        sa.Column("billing_status", billing_status_enum, nullable=False),
        sa.Column("stripe_customer_id", sa.String(length=128), nullable=True),
        sa.Column("stripe_subscription_id", sa.String(length=128), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("api_key_hash"),
        sa.UniqueConstraint("name"),
    )

    op.create_table(
        "jobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("input_path", sa.String(length=1024), nullable=False),
        sa.Column("output_path", sa.String(length=1024), nullable=True),
        sa.Column("status", job_status_enum, nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_jobs_workspace_id"), "jobs", ["workspace_id"], unique=False)

    op.create_table(
        "workspace_usage",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("jobs_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "period_start", name="uq_workspace_period"),
    )
    op.create_index(op.f("ix_workspace_usage_workspace_id"), "workspace_usage", ["workspace_id"], unique=False)

    op.create_table(
        "billing_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("provider_event_id", sa.String(length=160), nullable=False),
        sa.Column("event_type", sa.String(length=120), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=True),
        sa.Column("status", billing_event_status_enum, nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("raw_payload", sa.Text(), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider_event_id"),
    )

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=True),
        sa.Column("actor_type", sa.String(length=48), nullable=False),
        sa.Column("actor_id", sa.String(length=128), nullable=False),
        sa.Column("action", sa.String(length=96), nullable=False),
        sa.Column("resource_type", sa.String(length=96), nullable=False),
        sa.Column("resource_id", sa.String(length=160), nullable=True),
        sa.Column("details_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_audit_logs_workspace_id"), "audit_logs", ["workspace_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_audit_logs_workspace_id"), table_name="audit_logs")
    op.drop_table("audit_logs")

    op.drop_table("billing_events")

    op.drop_index(op.f("ix_workspace_usage_workspace_id"), table_name="workspace_usage")
    op.drop_table("workspace_usage")

    op.drop_index(op.f("ix_jobs_workspace_id"), table_name="jobs")
    op.drop_table("jobs")

    op.drop_table("workspaces")

    bind = op.get_bind()
    billing_event_status_enum.drop(bind, checkfirst=True)
    billing_status_enum.drop(bind, checkfirst=True)
    job_status_enum.drop(bind, checkfirst=True)
