"""auth user ownership

Revision ID: 20260511_0002
Revises: 20260511_0001
Create Date: 2026-05-11 00:00:01.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260511_0002"
down_revision = "20260511_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("risk_assessment_log") as batch_op:
        batch_op.add_column(sa.Column("user_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_risk_assessment_log_user_id_users",
            "users",
            ["user_id"],
            ["id"],
        )
        batch_op.create_index("ix_risk_assessment_log_user_id", ["user_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("risk_assessment_log") as batch_op:
        batch_op.drop_index("ix_risk_assessment_log_user_id")
        batch_op.drop_constraint("fk_risk_assessment_log_user_id_users", type_="foreignkey")
        batch_op.drop_column("user_id")
