"""Seed the initial Arletion workspace and official eTender source.

Revision ID: 0002_seed_reference_rows
Revises: 0001_initial
"""
from alembic import op

revision = "0002_seed_reference_rows"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        INSERT INTO tenants (id, name, slug, status)
        VALUES (
            '00000000-0000-0000-0000-000000000001',
            'Arletion Local Workspace',
            'arletion-local',
            'active'
        )
        ON CONFLICT DO NOTHING
    """)
    op.execute("""
        INSERT INTO source_registry (
            id, name, base_url, source_type, licence_reference, permitted_use, enabled,
            rate_limit_config, retention_config
        )
        VALUES (
            '00000000-0000-0000-0000-000000000002',
            'National Treasury eTender Transparency Portal',
            'https://data.etenders.gov.za/',
            'procurement_ocds',
            'API OpenAPI declares ODC PDDL 1.0; bulk-download terms differ; verify document-specific terms',
            'review_required',
            FALSE,
            '{}'::jsonb,
            '{}'::jsonb
        )
        ON CONFLICT DO NOTHING
    """)


def downgrade() -> None:
    # Reference rows are intentionally retained on downgrade to avoid deleting
    # tenant/source rows that may already be referenced by application data.
    pass
