import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { access } from "node:fs/promises";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import test from "node:test";
import { createCampaign, importFreeAwardedSupplierLeads, importNCRDebtCounsellors, importOpenStreetMapBusinesses, loadConsumerPage, loadConsumerStatus, loadDashboardData, loadLeadPage } from "../app/dashboard-api.mjs";

const webRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const monorepoRoot = resolve(webRoot, "../..");
const read = (path) => readFile(resolve(webRoot, path), "utf8");

test("frontend and monorepo scripts delegate to the canonical app", async () => {
  const frontend = JSON.parse(await read("package.json"));
  const root = JSON.parse(await readFile(resolve(monorepoRoot, "package.json"), "utf8"));

  for (const script of ["dev", "build", "start", "lint", "typecheck", "test"]) {
    assert.ok(frontend.scripts[script], `frontend script ${script} is configured`);
    assert.match(root.scripts[script], /npm --prefix apps\/web run/);
  }
  assert.match(frontend.scripts.start, /start-built\.mjs/);
});

test("approved brand images are preserved and referenced by the dashboard", async () => {
  const layout = await read("app/layout.tsx");
  const page = await read("app/page.tsx");
  const build = await read("scripts/build.mjs");
  const assets = [
    "arletion-emblem.png",
    "arletion-icon.png",
    "arletion-logo-variant.png",
    "arletion-logo.png",
    "arletion-mainlogo.png",
  ];

  assert.match(page, /src="\/arletion-logo\.png"/);
  assert.match(layout, /icon: "\/arletion-icon\.png"/);
  assert.match(layout, /apple: "\/arletion-icon\.png"/);
  assert.match(build, /cp\(resolve\(root, "public"\), resolve\(standalone, "public"\)/);
  assert.match(build, /resolve\(standalone, buildDir, "static"\)/);
  const manifest = await readFile(resolve(webRoot, ".arletion-latest-build.json"), "utf8").then(JSON.parse, () => null);
  const builtDir = manifest?.buildDir;
  const builtStandalone = builtDir && await access(resolve(webRoot, builtDir, "standalone/server.js")).then(() => true, () => false);
  for (const asset of assets) {
    const original = await readFile(resolve(webRoot, "public", asset));
    assert.equal(original.subarray(0, 8).toString("hex"), "89504e470d0a1a0a");
    if (builtStandalone) {
      const standalone = await readFile(resolve(webRoot, builtDir, "standalone/public", asset));
      assert.equal(createHash("sha256").update(standalone).digest("hex"), createHash("sha256").update(original).digest("hex"));
    }
  }
  const dockerfile = await read("Dockerfile");
  assert.match(dockerfile, /\.next-arletion\/static \.\/\.next-arletion\/static/);
});

test("production dashboard uses the protected same-origin API proxy", async () => {
  const page = await read("app/page.tsx");
  const proxy = await read("proxy.ts");
  const apiProxy = await read("app/api/backend/[...path]/route.ts");
  const render = await readFile(resolve(monorepoRoot, "render.yaml"), "utf8");

  assert.ok(page.includes('const API="/api/backend"'));
  assert.doesNotMatch(page, /NEXT_PUBLIC_API_BASE_URL/);
  assert.match(proxy, /ARLETION_BASIC_AUTH_USER/);
  assert.match(proxy, /ARLETION_BASIC_AUTH_PASSWORD/);
  assert.match(apiProxy, /ARLETION_API_KEY/);
  assert.ok(apiProxy.includes('path[0] !== "api"') && apiProxy.includes('path[1] !== "v1"'));
  assert.match(render, /ARLETION_REQUIRE_API_KEY/);
  assert.match(render, /value: https:\/\/arletion-api\.onrender\.com/);
  assert.match(render, /sync: false/);
});

test("opportunities page offers bounded, resumable official Treasury imports", async () => {
  const page = await read("app/page.tsx");
  const api = await read("app/dashboard-api.mjs");
  assert.match(page, /Import next eTender pages/);
  assert.match(page, /Approve source first/);
  assert.match(page, /approveSource/);
  assert.match(page, /date_from:dateFrom/);
  assert.match(page, /date_to:dateTo/);
  assert.match(page, /treasuryStartPage/);
  assert.match(api, /importOfficialOpportunityPages/);
  assert.match(api, /official\/batch/);
  assert.ok(page.includes("setReloadKey(value=>value+1)"));
});

test("dashboard data loader reads all API summaries", async () => {
  const calls = [];
  const result = await loadDashboardData("http://127.0.0.1:8000", async (url) => {
    calls.push(url);
    const endpoint = url.split("/").at(-1);
    const bodies = {
      campaigns: [],
      sources: [],
      summary: { campaigns: 0, leads: 0, sources: 0, qualified: 0, demo_mode: true },
      opportunities: { items: [], demo_mode: true, message: "No records" },
    };
    return { ok: true, json: async () => bodies[endpoint] };
  });

  assert.equal(calls.length, 4);
  assert.deepEqual(result.campaigns, []);
  assert.deepEqual(result.leads, []);
  assert.deepEqual(result.sources, []);
  assert.equal(result.summary.demo_mode, true);
  assert.deepEqual(result.opportunities, []);
});

test("lead search sends category, type, status and pagination filters to the API", async () => {
  let requestedUrl = "";
  const result = await loadLeadPage("http://127.0.0.1:8000", {
    q: "Witbank", lead_type: "business", category: "Construction",
    status: "qualified", province: "Mpumalanga", verification_status: "source_confirmed", page: 2, page_size: 10,
  }, async (url, options) => {
    requestedUrl = url;
    assert.ok(options.signal instanceof AbortSignal);
    return { ok: true, json: async () => ({
      items: [], categories: ["Construction"], page: 2, page_size: 10, total: 0,
    }) };
  });
  const parsed = new URL(requestedUrl);
  assert.equal(parsed.pathname, "/api/v1/leads/search");
  assert.equal(parsed.searchParams.get("category"), "Construction");
  assert.equal(parsed.searchParams.get("lead_type"), "business");
  assert.equal(parsed.searchParams.get("status"), "qualified");
  assert.equal(parsed.searchParams.get("province"), "Mpumalanga");
  assert.equal(parsed.searchParams.get("verification_status"), "source_confirmed");
  assert.equal(parsed.searchParams.get("page"), "2");
  assert.equal(result.total, 0);
});

test("lead search surfaces API failures and the UI exposes server-side category filters", async () => {
  await assert.rejects(
    loadLeadPage("http://127.0.0.1:8000", {}, async () => ({ ok: false, status: 502 })),
    /Lead search failed with HTTP 502/,
  );
  const page = await read("app/page.tsx");
  assert.match(page, /Industry category/);
  assert.match(page, /loadLeadPage/);
  assert.match(page, /Previous/);
  assert.match(page, /Next/);
  assert.doesNotMatch(page, /const filtered=useMemo/);
});

test("consumer intake status and enquiries use separate API routes and category filters", async () => {
  const status = await loadConsumerStatus("http://127.0.0.1:8000", async (url) => {
    assert.ok(url.endsWith("/api/v1/consumer-enquiries/status"));
    return { ok: true, json: async () => ({
      enabled: false, storage_approved: false, encryption_configured: false,
      deduplication_key_configured: false, separate_contact_access_configured: false,
      public_form: false, note: "Disabled",
    }) };
  });
  assert.equal(status.enabled, false);
  let requested = "";
  const page = await loadConsumerPage("http://127.0.0.1:8000", {
    category: "debt_counselling", status: "new", province: "Mpumalanga",
  }, async (url) => {
    requested = url;
    return { ok: true, json: async () => ({ items: [], page: 1, page_size: 25, total: 0 }) };
  });
  const parsed = new URL(requested);
  assert.equal(parsed.pathname, "/api/v1/consumer-enquiries");
  assert.equal(parsed.searchParams.get("category"), "debt_counselling");
  assert.equal(parsed.searchParams.get("province"), "Mpumalanga");
  assert.equal(page.total, 0);
});

test("campaign creation keeps consumer pipeline type and campaign category in criteria", async () => {
  let request;
  const created = await createCampaign("http://127.0.0.1:8000", {
    name: "Debt enquiries", objective: "Respond to opt-in requests",
    lead_type: "consumer_enquiry", geography: "South Africa", status: "draft",
    criteria: { enquiry_category: "debt_counselling" },
  }, async (url, options) => {
    request = { url, options };
    return { ok: true, json: async () => ({ id: "campaign-1", pipeline: "consumer" }) };
  });
  assert.ok(request.url.endsWith("/api/v1/campaigns"));
  assert.equal(JSON.parse(request.options.body).lead_type, "consumer_enquiry");
  assert.equal(JSON.parse(request.options.body).criteria.enquiry_category, "debt_counselling");
  assert.equal(created.pipeline, "consumer");
});

test("dashboard renders separate protected consumer enquiry and business campaign screens", async () => {
  const page = await read("app/page.tsx");
  assert.match(page, /Consumer enquiries/);
  assert.match(page, /Two separate campaign pipelines/);
  assert.match(page, /Contact data remains encrypted/);
  assert.match(page, /Consumer intake is safely disabled/);
  assert.match(page, /marketing_consent/);
  assert.doesNotMatch(page, /full_name|phone_ciphertext|email_ciphertext/);
});

test("OpenStreetMap import posts the selected locality and does not invent verification", async () => {
  let request;
  const result = await importOpenStreetMapBusinesses("http://127.0.0.1:8000", {
    campaign_id: "campaign-1", category: "Construction", locality: "eMalahleni",
    province: "Mpumalanga", latitude: -25.8762, longitude: 29.21,
    radius_m: 10000, limit: 100,
  }, async (url, options) => {
    request = { url, options };
    return { ok: true, json: async () => ({
      source: "OpenStreetMap Business Directory", attribution: "© OpenStreetMap contributors · ODbL 1.0",
      licence: "ODbL", location: "eMalahleni", province: "Mpumalanga",
      category: "Construction", radius_m: 10000, matched: 1, inserted: 1,
      updated: 0, skipped: 0, verification_status: "source_confirmed",
      verification_scope: "Map record only",
    }) };
  });
  assert.ok(request.url.endsWith("/api/v1/leads/import/openstreetmap"));
  assert.equal(request.options.method, "POST");
  assert.equal(JSON.parse(request.options.body).campaign_id, "campaign-1");
  assert.equal(result.verification_status, "source_confirmed");
  assert.equal(result.inserted, 1);
});

test("OpenStreetMap UI labels mapped records as source-confirmed, not CIPC verified", async () => {
  const page = await read("app/page.tsx");
  assert.match(page, /Find free local businesses/);
  assert.match(page, /OpenStreetMap business discovery/);
  assert.match(page, /Source-confirmed/);
  assert.match(page, /not CIPC or trading-status verification/);
  assert.match(page, /ODbL licence and attribution/);
  assert.match(page, /importOpenStreetMapBusinesses/);
  assert.match(page, /Government-awarded suppliers/);
  assert.match(page, /Import awarded companies as leads/);
  assert.match(page, /Check CSD/);
  assert.match(page, /Record CSD\/CIPC check/);
  assert.match(page, /recordManualVerification/);
});

test("free Treasury supplier import batches official releases before extracting awarded companies", async () => {
  const calls = [];
  const result = await importFreeAwardedSupplierLeads("http://127.0.0.1:8000", {
    campaign_id: "campaign-1", start_page: 3, page_count: 2,
    date_from: "2026-10-01", date_to: "2026-11-08", max_releases: 2000,
  }, async (url, options) => {
    calls.push({ url, body: options.body && JSON.parse(options.body) });
    if (url.endsWith("/api/v1/opportunities/import/official/batch")) {
      return { ok: true, json: async () => ({
        source: "National Treasury eTender Transparency Portal", pages_imported: 2,
        releases_received: 200, inserted: 180, updated: 0, unchanged: 0,
        stale_releases: 0, duplicates_in_input: 0, skipped: 20, next_page: 5,
        warning: null, has_more: true,
      }) };
    }
    return { ok: true, json: async () => ({
      source: "National Treasury eTender Transparency Portal", matched_releases: 200,
      unique_awarded_companies: 12, inserted: 10, updated: 2,
      skipped_releases_without_company_awards: 188,
      verification_status: "source_confirmed",
      verification_scope: "Named as a supplier in a published award; CSD status not implied.",
    }) };
  });
  assert.equal(calls.length, 2);
  assert.match(calls[0].url, /opportunities\/import\/official\/batch$/);
  assert.equal(calls[0].body.start_page, 3);
  assert.equal(calls[0].body.page_count, 2);
  assert.match(calls[1].url, /leads\/import\/etender-awarded-suppliers$/);
  assert.equal(calls[1].body.campaign_id, "campaign-1");
  assert.equal(calls[1].body.max_releases, 2000);
  assert.equal(result.batch.next_page, 5);
  assert.equal(result.suppliers.inserted, 10);
  assert.equal(result.suppliers.verification_status, "source_confirmed");
});

test("business lead screen offers one-step free Treasury source import with honest verification scope", async () => {
  const page = await read("app/page.tsx");
  assert.match(page, /Get free real supplier leads/);
  assert.match(page, /importFreeAwardedSupplierLeads/);
  assert.match(page, /Approve Treasury source first/);
  assert.match(page, /not current CSD-verified/);
  assert.match(page, /No paid lead-provider account is required/);
});

test("dashboard data loader reports unavailable or failing API requests", async () => {
  await assert.rejects(
    loadDashboardData("http://127.0.0.1:8000", async () => { throw new Error("offline"); }),
    /offline/,
  );
  await assert.rejects(
    loadDashboardData("http://127.0.0.1:8000", async () => ({ ok: false, status: 503 })),
    /HTTP 503/,
  );
  assert.match(await read("app/page.tsx"), /Retry connection/);
  assert.match(await read("app/page.tsx"), /role="alert"/);
});

test("dashboard API requests have bounded timeouts", async () => {
  await assert.rejects(
    loadDashboardData("http://127.0.0.1:8000", async (_url, options) => {
      assert.ok(options.signal instanceof AbortSignal);
      return new Promise(() => {});
    }, 5),
    /timed out after 5ms/,
  );
});


test("public debt-review enquiry page keeps processing and marketing consent separate", async () => {
  const page = await read("app/enquire/page.tsx");
  assert.match(page, /I am considering debt review/);
  assert.match(page, /I am already under debt review/);
  assert.match(page, /I have applied and am waiting for feedback/);
  assert.match(page, /processing_consent/);
  assert.match(page, /marketing_consent/);
  assert.match(page, /I confirm that I am 18 years or older/);
  assert.match(page, /Do not enter your South African ID number/);
  assert.match(page, /api\/public\/enquiries/);
  assert.doesNotMatch(page, /creditor lists/gi, /x/);
});

test("NCR directory import posts selected keyword and partnership campaign", async () => {
  let request;
  const result = await importNCRDebtCounsellors("https://api.example", {
    campaign_id: "partner-campaign", keyword: "eMalahleni", page: 2, limit: 100,
  }, async (url, options) => {
    request = { url, options };
    return { ok: true, json: async () => ({
      source: "National Credit Regulator Registered Debt Counsellors",
      keyword: "eMalahleni", page: 2, matched: 3, inserted: 3, updated: 0,
      verification_status: "source_confirmed", note: "No contact details stored.",
    }) };
  });
  assert.ok(request.url.endsWith("/api/v1/leads/import/ncr-debt-counsellors"));
  assert.equal(request.options.method, "POST");
  assert.deepEqual(JSON.parse(request.options.body), {
    campaign_id: "partner-campaign", keyword: "eMalahleni", page: 2, limit: 100,
  });
  assert.equal(result.inserted, 3);
  assert.equal(result.verification_status, "source_confirmed");
});

test("NCR partner import is shown separately from consumer debt-review leads", async () => {
  const page = await read("app/page.tsx");
  assert.match(page, /Find registered debt-counsellor partners/);
  assert.match(page, /National Credit Regulator Registered Debt Counsellors/);
  assert.match(page, /These are not consumer debt-review leads/);
  assert.match(page, /importNCRDebtCounsellors/);
  assert.match(page, /public_intake/);
  assert.match(page, /Publish a public voluntary debt-review enquiry form/);
});

test("public enquiry form and API routes are excluded from private workspace Basic Auth", async () => {
  const proxy = await read("proxy.ts");
  assert.match(proxy, /enquire/);
  assert.match(proxy, /api\/public\/enquiries/);
  const route = await read("app/api/public/enquiries/route.ts");
  assert.match(route, /ARLETION_API_KEY/);
  assert.match(route, /ARLETION_API_BASE_URL/);
  assert.match(route, /request\.nextUrl\.origin/);
  assert.match(route, /Too many submissions/);
});
