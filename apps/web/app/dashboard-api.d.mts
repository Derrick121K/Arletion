export interface Campaign {
  id: string;
  name: string;
  objective: string;
  lead_type: string;
  pipeline: "business_procurement" | "consumer";
  geography: string;
  status: string;
  lead_count: number;
}

export interface Lead {
  id: string;
  organization: string;
  lead_type: string;
  category: string | null;
  location: string;
  province: string | null;
  website_url: string | null;
  verification_status: "unverified" | "source_confirmed" | "officially_verified" | "needs_review";
  verification_source: string | null;
  verified_at: string | null;
  source_updated_at: string | null;
  source: string;
  source_url: string;
  status: string;
  score: number;
  evidence_note: string;
  demo: boolean;
}

export interface Source {
  id: string;
  name: string;
  category: string;
  url: string;
  status: string;
  note: string;
}

export interface Summary {
  campaigns: number;
  leads: number;
  business_leads: number;
  consumer_enquiries: number;
  sources: number;
  qualified: number;
  demo_mode: boolean;
}

export interface Opportunity {
  id: string;
  external_id: string;
  ocid: string | null;
  buyer_name: string | null;
  title: string;
  description: string | null;
  category: string | null;
  province: string | null;
  publication_date: string | null;
  closing_date: string | null;
  status: string;
  source_url: string;
  provenance: string;
}

export interface LeadPage {
  items: Lead[];
  categories: string[];
  page: number;
  page_size: number;
  total: number;
}

export function loadLeadPage(
  apiBaseUrl: string,
  filters?: { q?: string; lead_type?: string; category?: string; status?: string; province?: string; verification_status?: "unverified" | "source_confirmed" | "officially_verified" | "needs_review"; page?: number; page_size?: number },
  fetcher?: typeof fetch,
): Promise<LeadPage>;

export function loadDashboardData(
  apiBaseUrl: string,
  fetcher?: typeof fetch,
  timeoutMs?: number,
): Promise<{ campaigns: Campaign[]; leads: Lead[]; sources: Source[]; summary: Summary; opportunities: Opportunity[] }>;

export interface ConsumerEnquiry {
  id: string;
  campaign_id: string;
  contact_protected: boolean;
  has_phone: boolean;
  has_email: boolean;
  category: string;
  province: string | null;
  locality: string | null;
  preferred_channel: string;
  source: string;
  status: string;
  processing_consent_at: string;
  marketing_consent: boolean;
  marketing_consent_at: string | null;
  created_at: string;
  retention_expires_at: string;
}
export interface ConsumerStatus {
  enabled: boolean;
  storage_approved: boolean;
  staff_access_approved: boolean;
  encryption_configured: boolean;
  deduplication_key_configured: boolean;
  separate_contact_access_configured: boolean;
  public_form: boolean;
  note: string;
}
export function loadConsumerStatus(apiBaseUrl: string, fetcher?: typeof fetch): Promise<ConsumerStatus>;
export function loadConsumerPage(apiBaseUrl: string, filters?: { category?: string; status?: string; province?: string; page?: number; page_size?: number }, fetcher?: typeof fetch): Promise<{items: ConsumerEnquiry[]; page: number; page_size: number; total: number}>;
export function createCampaign(apiBaseUrl: string, campaign: { name: string; objective: string; lead_type: string; geography: string; status: string; criteria: Record<string, unknown> }, fetcher?: typeof fetch): Promise<Campaign>;

export interface OpenStreetMapImportResult {
  source: string;
  attribution: string;
  licence: string;
  location: string;
  province: string;
  category: string;
  radius_m: number;
  matched: number;
  inserted: number;
  updated: number;
  skipped: number;
  verification_status: "source_confirmed";
  verification_scope: string;
}
export function importOpenStreetMapBusinesses(
  apiBaseUrl: string,
  request: { campaign_id: string; category: string; locality: string; province: string; latitude: number; longitude: number; radius_m: number; limit: number },
  fetcher?: typeof fetch,
): Promise<OpenStreetMapImportResult>;

export interface AwardedSupplierImportResult {
  source: string;
  matched_releases: number;
  unique_awarded_companies: number;
  inserted: number;
  updated: number;
  skipped_releases_without_company_awards: number;
  verification_status: "source_confirmed";
  verification_scope: string;
}
export function importEtenderAwardedSuppliers(
  apiBaseUrl: string,
  request: { campaign_id: string; max_releases: number },
  fetcher?: typeof fetch,
): Promise<AwardedSupplierImportResult>;

export interface OfficialBatchImportResult {
  source: string;
  inserted: number;
  updated: number;
  unchanged: number;
  stale_releases: number;
  duplicates_in_input: number;
  skipped: number;
  pages_imported: number;
  releases_received: number;
  next_page: number;
  warning: string | null;
  has_more: boolean;
}
export function importOfficialOpportunityPages(
  apiBaseUrl: string,
  request: { start_page: number; page_size: number; page_count: number; date_from: string; date_to: string },
  fetcher?: typeof fetch,
): Promise<OfficialBatchImportResult>;

export interface LeadVerificationResult {
  lead_id: string;
  verification_status: "officially_verified" | "needs_review";
  verification_source: string;
  verified_at: string;
  evidence_url: string;
  reference: string;
}
export function recordLeadVerification(
  apiBaseUrl: string,
  leadId: string,
  payload: { registry: "CSD" | "CIPC"; result: "verified" | "not_found" | "inactive" | "restricted" | "unknown"; evidence_url: string; reference: string; note?: string; checked_at: string },
  fetcher?: typeof fetch,
): Promise<LeadVerificationResult>;
