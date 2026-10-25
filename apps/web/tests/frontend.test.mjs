import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { access } from "node:fs/promises";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import test from "node:test";
import { loadDashboardData } from "../app/dashboard-api.mjs";

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

test("dashboard data loader reads all API summaries", async () => {
  const calls = [];
  const result = await loadDashboardData("http://127.0.0.1:8000", async (url) => {
    calls.push(url);
    const endpoint = url.split("/").at(-1);
    const bodies = {
      campaigns: [],
      leads: [],
      sources: [],
      summary: { campaigns: 0, leads: 0, sources: 0, qualified: 0, demo_mode: true },
      opportunities: { items: [], demo_mode: true, message: "No records" },
    };
    return { ok: true, json: async () => bodies[endpoint] };
  });

  assert.equal(calls.length, 5);
  assert.deepEqual(result.campaigns, []);
  assert.deepEqual(result.leads, []);
  assert.deepEqual(result.sources, []);
  assert.equal(result.summary.demo_mode, true);
  assert.deepEqual(result.opportunities, []);
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
