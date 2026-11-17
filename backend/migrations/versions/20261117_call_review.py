"""Track technical review separately from the call disposition."""
import sqlalchemy as sa
from alembic import op

revision = "20261117_call_review"
down_revision = "20261106_staff"
branch_labels = depends_on = None


def upgrade():
    op.add_column("calls", sa.Column("outcome_review_required", sa.Boolean(),
                                    server_default=sa.false(), nullable=False))


def downgrade():
    op.drop_column("calls", "outcome_review_required")
