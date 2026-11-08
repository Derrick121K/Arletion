const endpoints = ["campaigns", "sources", "summary", "opportunities"];

/** @param {string} apiBaseUrl @param {typeof fetch} fetcher @param {number} timeoutMs */
export async function loadDashboardData(apiBaseUrl, fetcher = fetch, timeoutMs = 90000) {
  const values = await Promise.all(
    endpoints.map(async (endpoint) => {
      const controller = new AbortController();
      let timer;
      let response;
      try {
        response = await Promise.race([
          fetcher(`${apiBaseUrl}/api/v1/${endpoint}`, { signal: controller.signal }),
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
      if (!response.ok) {
        throw new Error(`API request for ${endpoint} failed with HTTP ${response.status}.`);
      }
      return response.json();
    }),
  );

  return {
    campaigns: values[0],
    leads: [],
    sources: values[1],
    summary: values[2],
    opportunities: values[3].items,
  };
}

/** @param {string} apiBaseUrl @param {{q?:string,lead_type?:string,category?:string,status?:string,province?:string,page?:number,page_size?:number}} filters @param {typeof fetch} fetcher */
export async function loadLeadPage(apiBaseUrl, filters = {}, fetcher = fetch) {
  const params = new URLSearchParams({ page: String(filters.page ?? 1), page_size: String(filters.page_size ?? 25) });
  for (const key of ["q", "lead_type", "category", "status", "province"]) {
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
