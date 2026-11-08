const endpoints = ["campaigns", "sources", "summary", "opportunities"];
const MAX_429_RETRIES = 3;
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function retryAfterMs(response, attempt) {
  const value = response.headers?.get?.("retry-after");
  if (value) {
    const seconds = Number(value);
    if (Number.isFinite(seconds) && seconds >= 0) return Math.min(seconds * 1000, 5000);
    const date = Date.parse(value);
    if (Number.isFinite(date)) return Math.min(Math.max(0, date - Date.now()), 5000);
  }
  return Math.min(250 * (2 ** attempt) + Math.floor(Math.random() * 100), 2500);
}

async function requestDashboardJson(url, endpoint, fetcher, timeoutMs) {
  for (let attempt = 0; ; attempt += 1) {
    const controller = new AbortController();
    let timer;
    let response;
    try {
      response = await Promise.race([
        fetcher(url, { signal: controller.signal, cache: "no-store" }),
        new Promise((_, reject) => {
          timer = setTimeout(() => {
            reject(new Error(`API request for ${endpoint} timed out after ${timeoutMs}ms.`));
            controller.abort();
          }, timeoutMs);
        }),
      ]);
    } finally {
      clearTimeout(timer);
    }

    if (response.status === 429 && attempt < MAX_429_RETRIES) {
      await sleep(retryAfterMs(response, attempt));
      continue;
    }
    if (!response.ok) {
      throw new Error(`API request for ${endpoint} failed with HTTP ${response.status}.`);
    }
    return response.json();
  }
}

/** @param {string} apiBaseUrl @param {typeof fetch} fetcher @param {number} timeoutMs */
export async function loadDashboardData(apiBaseUrl, fetcher = fetch, timeoutMs = 90000) {
  // Serialize startup reads to avoid bursting four requests into a rate-limited service.
  const values = [];
  for (const endpoint of endpoints) {
    values.push(await requestDashboardJson(`${apiBaseUrl}/api/v1/${endpoint}`, endpoint, fetcher, timeoutMs));
  }

  return {
    campaigns: values[0],
    leads: [],
    sources: values[1],
    summary: values[2],
    opportunities: values[3].items,
  };
}

/** @param {string} apiBaseUrl @param {{q?:string,lead_type?:string,category?:string,status?:string,province?:string,verification_status?:string,page?:number,page_size?:number}} filters @param {typeof fetch} fetcher */
export async function loadLeadPage(apiBaseUrl, filters = {}, fetcher = fetch) {
  const params = new URLSearchParams({ page: String(filters.page ?? 1), page_size: String(filters.page_size ?? 25) });
  for (const key of ["q", "lead_type", "category", "status", "province", "verification_status"]) {
    const value = filters[key];
    if (value) params.set(key, value);
  }
  const response = await fetcher(`${apiBaseUrl}/api/v1/leads/search?${params.toString()}`, {
    signal: AbortSignal.timeout(30000),
    cache: "no-store",
  });
  if (!response.ok) throw new Error(`Lead search failed with HTTP ${response.status}.`);
  return response.json();
}


/** @param {string} apiBaseUrl @param {typeof fetch} fetcher */
export async function loadConsumerStatus(apiBaseUrl, fetcher = fetch) {
  const response = await fetcher(`${apiBaseUrl}/api/v1/consumer-enquiries/status`, { cache: "no-store" });
  if (!response.ok) throw new Error(`Consumer intake status failed with HTTP ${response.status}.`);
  return response.json();
}

/** @param {string} apiBaseUrl @param {{category?:string,status?:string,province?:string,page?:number,page_size?:number}} filters @param {typeof fetch} fetcher */
export async function loadConsumerPage(apiBaseUrl, filters = {}, fetcher = fetch) {
  const params = new URLSearchParams({ page: String(filters.page ?? 1), page_size: String(filters.page_size ?? 25) });
  for (const key of ["category", "status", "province"]) if (filters[key]) params.set(key, filters[key]);
  const response = await fetcher(`${apiBaseUrl}/api/v1/consumer-enquiries?${params}`, { signal: AbortSignal.timeout(30000), cache: "no-store" });
  if (!response.ok) throw new Error(`Consumer enquiries unavailable (HTTP ${response.status}).`);
  return response.json();
}

/** @param {string} apiBaseUrl @param {{name:string,objective:string,lead_type:string,geography:string,status:string,criteria:Record<string,unknown>}} campaign @param {typeof fetch} fetcher */
export async function createCampaign(apiBaseUrl, campaign, fetcher = fetch) {
  const response = await fetcher(`${apiBaseUrl}/api/v1/campaigns`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(campaign),
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(typeof payload.detail === "string" ? payload.detail : `Campaign creation failed with HTTP ${response.status}.`);
  }
  return response.json();
}


/** @param {string} apiBaseUrl @param {{campaign_id:string,category:string,locality:string,province:string,latitude:number,longitude:number,radius_m:number,limit:number}} request @param {typeof fetch} fetcher */
export async function importOpenStreetMapBusinesses(apiBaseUrl, request, fetcher = fetch) {
  const response = await fetcher(`${apiBaseUrl}/api/v1/leads/import/openstreetmap`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
    signal: AbortSignal.timeout(60000),
    cache: "no-store",
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(typeof payload.detail === "string" ? payload.detail : `OpenStreetMap import failed with HTTP ${response.status}.`);
  return payload;
}


/** @param {string} apiBaseUrl @param {{campaign_id:string,max_releases:number}} request @param {typeof fetch} fetcher */
export async function importEtenderAwardedSuppliers(apiBaseUrl, request, fetcher = fetch) {
  const response = await fetcher(`${apiBaseUrl}/api/v1/leads/import/etender-awarded-suppliers`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
    signal: AbortSignal.timeout(60000),
    cache: "no-store",
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(typeof payload.detail === "string" ? payload.detail : `Treasury supplier import failed with HTTP ${response.status}.`);
  return payload;
}


/** @param {string} apiBaseUrl @param {{start_page:number,page_size:number,page_count:number,date_from:string,date_to:string}} request @param {typeof fetch} fetcher */
export async function importOfficialOpportunityPages(apiBaseUrl, request, fetcher = fetch) {
  const response = await fetcher(`${apiBaseUrl}/api/v1/opportunities/import/official/batch`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
    signal: AbortSignal.timeout(85000),
    cache: "no-store",
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(typeof payload.detail === "string" ? payload.detail : `Treasury import failed with HTTP ${response.status}.`);
  return payload;
}


/** @param {string} apiBaseUrl @param {string} leadId @param {{registry:"CSD"|"CIPC",result:"verified"|"not_found"|"inactive"|"restricted"|"unknown",evidence_url:string,reference:string,note?:string,checked_at:string}} payload @param {typeof fetch} fetcher */
export async function recordLeadVerification(apiBaseUrl, leadId, payload, fetcher = fetch) {
  const response = await fetcher(`${apiBaseUrl}/api/v1/leads/${encodeURIComponent(leadId)}/verification`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    signal: AbortSignal.timeout(20000),
    cache: "no-store",
  });
  const result = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(typeof result.detail === "string" ? result.detail : `Verification record failed with HTTP ${response.status}.`);
  return result;
}


/** @param {string} apiBaseUrl @param {{campaign_id:string,start_page:number,page_count:number,date_from:string,date_to:string,max_releases:number}} request @param {typeof fetch} fetcher */
export async function importFreeAwardedSupplierLeads(apiBaseUrl, request, fetcher = fetch) {
  const batch = await importOfficialOpportunityPages(apiBaseUrl, {
    start_page: request.start_page, page_size: 100, page_count: request.page_count,
    date_from: request.date_from, date_to: request.date_to,
  }, fetcher);
  const suppliers = await importEtenderAwardedSuppliers(apiBaseUrl, {
    campaign_id: request.campaign_id, max_releases: request.max_releases,
  }, fetcher);
  return { batch, suppliers };
}


/** @param {string} apiBaseUrl @param {{campaign_id:string,keyword?:string,page?:number,limit?:number}} request @param {typeof fetch} fetcher */
export async function importNCRDebtCounsellors(apiBaseUrl, request, fetcher = fetch) {
  const response = await fetcher(`${apiBaseUrl}/api/v1/leads/import/ncr-debt-counsellors`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
    signal: AbortSignal.timeout(25000),
    cache: "no-store",
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(typeof payload.detail === "string" ? payload.detail : `NCR directory import failed with HTTP ${response.status}.`);
  return payload;
}
