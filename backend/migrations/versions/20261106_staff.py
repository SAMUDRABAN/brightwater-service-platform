"""Individual staff identities and revocable sessions."""
import sqlalchemy as sa
from alembic import op

revision = "20261106_staff"
down_revision = "20261106_call_purpose"
branch_labels = depends_on = None


def upgrade():
    op.create_table("staff_users",
        sa.Column("username", sa.String(80), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("engineer_id", sa.String(40), sa.ForeignKey("engineers.id")),
        sa.Column("password_hash", sa.String(300), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("change_required", sa.Boolean(), nullable=False),
        sa.CheckConstraint("role IN ('admin', 'office', 'engineer')", name="staff_role_valid"),
        sa.CheckConstraint("role != 'engineer' OR engineer_id IS NOT NULL", name="staff_engineer_link"))
    op.create_table("staff_sessions",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column("username", sa.String(80), sa.ForeignKey("staff_users.username"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_staff_sessions_username", "staff_sessions", ["username"])
    op.create_table("staff_audit",
        sa.Column("id", sa.String(40), primary_key=True),
        sa.Column("username", sa.String(80), nullable=False),
        sa.Column("action", sa.String(150), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))


def downgrade():
    for table in ("staff_audit", "staff_sessions", "staff_users"):
        op.drop_table(table)
