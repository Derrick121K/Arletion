CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE TABLE IF NOT EXISTS tenants (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(), name TEXT NOT NULL, slug TEXT NOT NULL UNIQUE,
 status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','suspended','closed')),
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS campaigns (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
 name TEXT NOT NULL, objective TEXT NOT NULL,
 lead_type TEXT NOT NULL CHECK (lead_type IN ('business','procurement','consumer_enquiry','partnership')),
 geography JSONB NOT NULL DEFAULT '{}'::jsonb, criteria JSONB NOT NULL DEFAULT '{}'::jsonb,
 scoring_config JSONB NOT NULL DEFAULT '{}'::jsonb, workflow_config JSONB NOT NULL DEFAULT '{}'::jsonb,
 status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','active','paused','archived')),
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS source_registry (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(), name TEXT NOT NULL UNIQUE, base_url TEXT NOT NULL,
 source_type TEXT NOT NULL, licence_reference TEXT, permitted_use TEXT NOT NULL DEFAULT 'pending_review',
 enabled BOOLEAN NOT NULL DEFAULT false, rate_limit_config JSONB NOT NULL DEFAULT '{}'::jsonb,
 retention_config JSONB NOT NULL DEFAULT '{}'::jsonb, last_synced_at TIMESTAMPTZ, last_error TEXT,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS organizations (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(), canonical_name TEXT NOT NULL, normalized_name TEXT NOT NULL,
 website_domain TEXT, business_category TEXT, country_code CHAR(2) NOT NULL DEFAULT 'ZA', province TEXT,
 municipality TEXT, locality TEXT, created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS organizations_normalized_name_idx ON organizations(normalized_name);
CREATE INDEX IF NOT EXISTS organizations_domain_idx ON organizations(website_domain);
CREATE TABLE IF NOT EXISTS source_records (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(), source_id UUID NOT NULL REFERENCES source_registry(id), external_id TEXT,
 record_type TEXT NOT NULL, source_url TEXT NOT NULL, source_updated_at TIMESTAMPTZ,
 observed_at TIMESTAMPTZ NOT NULL DEFAULT now(), payload_hash TEXT, raw_payload JSONB,
 CONSTRAINT source_records_source_external_uq UNIQUE(source_id, external_id)
);
CREATE TABLE IF NOT EXISTS leads (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
 campaign_id UUID NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE, organization_id UUID REFERENCES organizations(id),
 lead_type TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'new', score SMALLINT NOT NULL DEFAULT 0 CHECK(score BETWEEN 0 AND 100),
 score_breakdown JSONB NOT NULL DEFAULT '{}'::jsonb, qualification_reason TEXT, first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(), next_follow_up_at TIMESTAMPTZ,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 UNIQUE(tenant_id, campaign_id, organization_id)
);
CREATE INDEX IF NOT EXISTS leads_tenant_status_score_idx ON leads(tenant_id,status,score DESC);
CREATE TABLE IF NOT EXISTS opportunities (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(), source_id UUID REFERENCES source_registry(id), external_id TEXT, ocid TEXT,
 buyer_name TEXT, title TEXT NOT NULL, description TEXT, category TEXT, province TEXT, publication_date DATE,
 closing_date DATE, status TEXT NOT NULL DEFAULT 'unknown', source_url TEXT NOT NULL, last_observed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 CONSTRAINT opportunities_source_external_uq UNIQUE(source_id,external_id)
);
CREATE TABLE IF NOT EXISTS evidence_items (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(), organization_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
 source_record_id UUID REFERENCES source_records(id) ON DELETE CASCADE, field_name TEXT NOT NULL, field_value TEXT,
 evidence_url TEXT NOT NULL, observed_at TIMESTAMPTZ NOT NULL DEFAULT now(), verification_status TEXT NOT NULL DEFAULT 'unknown',
 confidence NUMERIC(4,3), expires_at TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS consent_records (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
 subject_reference TEXT NOT NULL, purpose TEXT NOT NULL, channel TEXT NOT NULL, consent_status TEXT NOT NULL,
 captured_at TIMESTAMPTZ, notice_version TEXT, evidence_reference TEXT, withdrawn_at TIMESTAMPTZ, created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS suppression_records (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
 subject_reference TEXT NOT NULL, channel TEXT NOT NULL, reason TEXT NOT NULL, recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 status TEXT NOT NULL DEFAULT 'active'
);
CREATE TABLE IF NOT EXISTS audit_events (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id UUID REFERENCES tenants(id), actor_user_id TEXT, action TEXT NOT NULL,
 entity_type TEXT NOT NULL, entity_id TEXT, occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(), request_id TEXT,
 metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);
