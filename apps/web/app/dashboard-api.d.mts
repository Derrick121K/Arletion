export interface Campaign {
  id: string;
  name: string;
  objective: string;
  lead_type: string;
  geography: string;
  status: string;
  lead_count: number;
}

export interface Lead {
  id: string;
  organization: string;
  lead_type: string;
  location: string;
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

export function loadDashboardData(
  apiBaseUrl: string,
  fetcher?: typeof fetch,
  timeoutMs?: number,
): Promise<{ campaigns: Campaign[]; leads: Lead[]; sources: Source[]; summary: Summary; opportunities: Opportunity[] }>;
