"""Add verification metadata and an approved OpenStreetMap source.

Revision ID: 0005_free_osm_business_sources
Revises: 0004_dual_lead_pipelines
"""
from alembic import op
import sqlalchemy as sa

revision = "0005_free_osm_business_sources"
down_revision = "0004_dual_lead_pipelines"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("leads", sa.Column("verification_status", sa.String(32), nullable=False, server_default="unverified"))
    op.add_column("leads", sa.Column("verification_source", sa.Text(), nullable=True))
    op.add_column("leads", sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True))
    op.create_check_constraint(
        "lead_verification_status_check",
        "leads",
        "verification_status IN ('unverified','source_confirmed','officially_verified','needs_review')",
    )
    op.execute("""
        INSERT INTO source_registry (
            id, name, base_url, source_type, licence_reference, permitted_use, enabled,
            rate_limit_config, retention_config
        )
        VALUES (
            '00000000-0000-0000-0000-000000000003',
            'OpenStreetMap Business Directory',
            'https://www.openstreetmap.org/',
            'business_directory_osm',
            'Open Database License (ODbL) 1.0; attribution required: © OpenStreetMap contributors',
            'approved',
            TRUE,
            '{"provider":"Overpass API","max_results_per_import":200,"minimum_interval_seconds":60}'::jsonb,
            '{"retain_source_object_id":true,"retain_source_timestamp":true}'::jsonb
        )
        ON CONFLICT DO NOTHING
    """)


def downgrade() -> None:
    op.drop_constraint("lead_verification_status_check", "leads", type_="check")
    op.drop_column("leads", "verified_at")
    op.drop_column("leads", "verification_source")
    op.drop_column("leads", "verification_status")
