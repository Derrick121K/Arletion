const endpoints = ["campaigns", "leads", "sources", "summary", "opportunities"];

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
    leads: values[1],
    sources: values[2],
    summary: values[3],
    opportunities: values[4].items,
  };
}
