"""Expand consent-based debt review categories and add NCR source registry.

Revision ID: 0006_debt_review_leads
Revises: 0005_free_osm_business_sources
"""
from alembic import op

revision = "0006_debt_review_leads"
down_revision = "0005_free_osm_business_sources"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("consumer_enquiry_category_check", "consumer_enquiries", type_="check")
    op.create_check_constraint(
        "consumer_enquiry_category_check", "consumer_enquiries",
        "category IN ('debt_counselling','debt_review_information','considering_debt_review','already_under_review','application_pending','debt_review_assistance','completed_debt_review','budget_guidance','general')",
    )
    op.get_bind().exec_driver_sql("""
        INSERT INTO source_registry (
            id, name, base_url, source_type, licence_reference, permitted_use, enabled,
            rate_limit_config, retention_config
        ) VALUES (
            '00000000-0000-0000-0000-000000000004',
            'National Credit Regulator Registered Debt Counsellors',
            'https://www.ncr.org.za/register_of_registrants/registered_dc.php',
            'official_regulatory_directory',
            'Public NCR registered debt counsellor directory; retain record-level source URL and observation date. Manual terms/reuse review required.',
            'review_required', FALSE,
            '{"provider":"National Credit Regulator","max_records_per_run":100,"minimum_interval_seconds":60}'::jsonb,
            '{"retain_registration_number":true,"store_only_professional_directory_fields":true}'::jsonb
        ) ON CONFLICT DO NOTHING
    """)


def downgrade() -> None:
    op.execute("DELETE FROM source_registry WHERE id='00000000-0000-0000-0000-000000000004'")
    op.drop_constraint("consumer_enquiry_category_check", "consumer_enquiries", type_="check")
    op.create_check_constraint(
        "consumer_enquiry_category_check", "consumer_enquiries",
        "category IN ('debt_counselling','debt_review_information','budget_guidance','general')",
    )
