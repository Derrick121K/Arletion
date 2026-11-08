"""Create isolated consumer enquiry records with encrypted contact fields.

Revision ID: 0004_dual_lead_pipelines
Revises: 0003_lead_filter_indexes
"""
from alembic import op
from app.models import ConsumerEnquiry

revision = "0004_dual_lead_pipelines"
down_revision = "0003_lead_filter_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    ConsumerEnquiry.__table__.create(bind=op.get_bind(), checkfirst=True)


def downgrade() -> None:
    ConsumerEnquiry.__table__.drop(bind=op.get_bind(), checkfirst=True)