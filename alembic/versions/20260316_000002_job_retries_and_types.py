"""add job retries and job types

Revision ID: 20260316_000002
Revises: 20260314_000001
Create Date: 2026-03-16 00:00:02

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260316_000002"
down_revision = "20260314_000001"
branch_labels = None
depends_on = None


def _job_columns() -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {column["name"] for column in inspector.get_columns("jobs")}


def upgrade() -> None:
    existing = _job_columns()

    if "job_type" not in existing:
        op.add_column(
            "jobs",
            sa.Column("job_type", sa.String(length=32), nullable=False, server_default="font_fix"),
        )
    if "job_options" not in existing:
        op.add_column("jobs", sa.Column("job_options", sa.Text(), nullable=True))
    if "attempt_count" not in existing:
        op.add_column(
            "jobs",
            sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        )
    if "max_attempts" not in existing:
        op.add_column(
            "jobs",
            sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        )
    if "next_retry_at" not in existing:
        op.add_column("jobs", sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    existing = _job_columns()

    if "next_retry_at" in existing:
        op.drop_column("jobs", "next_retry_at")
    if "max_attempts" in existing:
        op.drop_column("jobs", "max_attempts")
    if "attempt_count" in existing:
        op.drop_column("jobs", "attempt_count")
    if "job_options" in existing:
        op.drop_column("jobs", "job_options")
    if "job_type" in existing:
        op.drop_column("jobs", "job_type")
