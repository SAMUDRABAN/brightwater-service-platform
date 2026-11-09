"""Explicitly distinguish attended engineering calls from UK campaign calls."""
import sqlalchemy as sa
from alembic import op

revision = "20261106_call_purpose"
down_revision = "1494f25872de"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("calls", sa.Column("purpose", sa.String(20), nullable=False, server_default="campaign"))


def downgrade():
    op.drop_column("calls", "purpose")
