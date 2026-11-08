"""Register the consent-based Tally consumer enquiry webhook source.

Revision ID: 0007_tally_hooks
Revises: 0006_debt_review_leads
"""
from alembic import op

revision = "0007_tally_hooks"
down_revision = "0006_debt_review_leads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.get_bind().exec_driver_sql("""
        INSERT INTO source_registry (
            id, name, base_url, source_type, licence_reference, permitted_use, enabled,
            rate_limit_config, retention_config
        ) VALUES (
            '00000000-0000-0000-0000-000000000005',
            'Tally Voluntary Consumer Enquiry Webhook',
            'https://tally.so/',
            'consent_based_webhook',
            'Tally form submissions sent to an Arletion endpoint; signed webhook verification and field-level consent required. Review processor terms and privacy notice before enabling.',
            'review_required', FALSE,
            '{"provider":"Tally","event":"FORM_RESPONSE","require_signature":true,"deduplicate_event_id":true}'::jsonb,
            '{"encrypt_contact_data":true,"store_minimal_source_metadata":true}'::jsonb
        ) ON CONFLICT DO NOTHING
    """)


def downgrade() -> None:
    op.execute("DELETE FROM source_registry WHERE id='00000000-0000-0000-0000-000000000005'")
