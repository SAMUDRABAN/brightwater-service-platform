"""Store a pending office-scheduled call on the customer record."""
import sqlalchemy as sa
from alembic import op

revision = "20261117_customer_schedule"
down_revision = "20261117_call_review"
branch_labels = depends_on = None


def upgrade():
    op.add_column("customers", sa.Column("scheduled_call_at", sa.DateTime(timezone=True)))


def downgrade():
    op.drop_column("customers", "scheduled_call_at")
