"""Index the lead filters used by the workspace search API.

Revision ID: 0003_lead_filter_indexes
Revises: 0002_seed_reference_rows
"""
from alembic import op

revision = "0003_lead_filter_indexes"
down_revision = "0002_seed_reference_rows"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("organizations_business_category_idx", "organizations", ["business_category"], if_not_exists=True)
    op.create_index("organizations_location_idx", "organizations", ["province", "municipality", "locality"], if_not_exists=True)
    op.create_index("leads_tenant_type_status_created_idx", "leads", ["tenant_id", "lead_type", "status", "created_at"], if_not_exists=True)


def downgrade() -> None:
    op.drop_index("leads_tenant_type_status_created_idx", table_name="leads", if_exists=True)
    op.drop_index("organizations_location_idx", table_name="organizations", if_exists=True)
    op.drop_index("organizations_business_category_idx", table_name="organizations", if_exists=True)