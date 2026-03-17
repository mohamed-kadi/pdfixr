"""add job size metrics

Revision ID: 20260316_000003
Revises: 20260316_000002
Create Date: 2026-03-16 00:00:03

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260316_000003"
down_revision = "20260316_000002"
branch_labels = None
depends_on = None


def _job_columns() -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {column["name"] for column in inspector.get_columns("jobs")}


def upgrade() -> None:
    existing = _job_columns()
    if "input_size_bytes" not in existing:
        op.add_column("jobs", sa.Column("input_size_bytes", sa.Integer(), nullable=True))
    if "output_size_bytes" not in existing:
        op.add_column("jobs", sa.Column("output_size_bytes", sa.Integer(), nullable=True))


def downgrade() -> None:
    existing = _job_columns()
    if "output_size_bytes" in existing:
        op.drop_column("jobs", "output_size_bytes")
    if "input_size_bytes" in existing:
        op.drop_column("jobs", "input_size_bytes")
