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
