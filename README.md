# Arletion v0.1 — Lead Intelligence
Free-first, API-first lead discovery for South African business prospects and procurement opportunities.

## Included
- Next.js App Router + TypeScript dashboard starter
- FastAPI API with PostgreSQL-backed campaign, lead, source, source-record and opportunity endpoints
- SQLAlchemy models and Alembic migrations
- Docker Compose
- Source validation register and privacy/architecture notes
- Demo fixtures are not served by default; the API reports a clear database error when persistence is unavailable
- National Treasury eTender OCDS JSON/CSV import support, with official API pagination

## Run locally
The Arletion project root is this directory. Its root npm scripts delegate only to `apps/web`; the frontend also has its own independent `package.json` and npm lockfile. Do not run Arletion commands from `C:\Users\Kapa\Music`, which is the separate Macuvela workspace.

### Frontend (Windows PowerShell)

```powershell
Set-Location "C:\Users\Kapa\Music\Arletion\arletion-v0.1"
npm ci --prefix apps/web
npm run lint
npm run typecheck
npm test
npm run build
$env:ARLETION_API_BASE_URL = "http://127.0.0.1:8000"
$env:ARLETION_API_KEY = "local-demo-key"
$env:ARLETION_BASIC_AUTH_USER = "local-admin"
$env:ARLETION_BASIC_AUTH_PASSWORD = "replace-with-a-strong-local-password"
npm run start:windows -- -Port 3000
```

`npm run dev` starts the development server instead of the production server. The browser calls a same-origin `/api/backend` proxy; the proxy reads `ARLETION_API_BASE_URL` and `ARLETION_API_KEY` on the server, never from a `NEXT_PUBLIC_*` variable. In development, the API base defaults to `http://127.0.0.1:8000`. `start:windows` takes a port, checks for a listener, reports its process when Windows exposes it, and never terminates an existing process. Production mode requires `ARLETION_BASIC_AUTH_USER` and `ARLETION_BASIC_AUTH_PASSWORD`; set both in the server environment, not in client-side code. If the chosen frontend port differs from 3000, add that exact origin to `ARLETION_CORS_ORIGINS` and restart the API.

Production builds use a unique `.next-arletion-build-*` directory and update `apps/web/.arletion-latest-build.json` only after the standalone server, public assets, and dist-directory static chunks are ready. `npm start` runs the selected standalone build. This keeps a new build from overwriting files used by a running local dashboard. The Docker image sets `ARLETION_BUILD_DIR=.next-arletion` because its builder has no active server using that path.

Before starting on port 3000, inspect its owner:

```powershell
$port = 3000
Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue |
  ForEach-Object {
    $listener = $_
    $process = Get-CimInstance Win32_Process -Filter "ProcessId = $($listener.OwningProcess)"
    [PSCustomObject]@{ Port = $port; PID = $listener.OwningProcess; Process = $process.Name; CommandLine = $process.CommandLine }
  } | Format-List
```

If the PID is an existing Arletion server, reuse it. Otherwise stop only a process you have identified as safe to stop, preferably with Ctrl+C in its owning terminal. To use a free alternate port without stopping another application, run `npm run start:windows -- -Port 3001` from either this project root or `apps/web`. The startup helper refuses an occupied port and never kills a process.

### API (separate PowerShell window)

```powershell
Set-Location "C:\Users\Kapa\Music\Arletion\arletion-v0.1"
if (-not (Test-Path .venv)) { py -m venv .venv }
.\.venv\Scripts\python.exe -m pip install -r services\api\requirements.txt
$env:DATABASE_URL = "postgresql+psycopg://arletion:YOUR_LOCAL_PASSWORD@127.0.0.1:5432/arletion"
$env:ARLETION_API_KEY = "local-demo-key"
$env:ARLETION_REQUIRE_API_KEY = "true"
$env:ARLETION_CORS_ORIGINS = "http://localhost:3000,http://127.0.0.1:3000"
Push-Location services\api
..\..\.venv\Scripts\alembic.exe upgrade head
..\..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
Pop-Location
```

Check `http://127.0.0.1:8000/health` and `http://127.0.0.1:8000/docs`. Health returns HTTP 503 and a database diagnostic when `DATABASE_URL` is missing, unreachable or not migrated; the API does not silently fall back to fixtures. If port 8000 is occupied, identify its listener before stopping anything. `ARLETION_CORS_ORIGINS` is a comma-separated allowlist; defaults permit the two local dashboard origins on port 3000. For example, add `http://127.0.0.1:3011,http://localhost:3011` when using that frontend port.

Campaigns, leads and sources can be written through their versioned POST endpoints; campaigns also support PATCH. Opportunity records are upserted by source ID, so repeat imports do not create duplicate rows. The dashboard reads these records from the API.

For PostgreSQL integration tests, create a new, empty database dedicated to tests on a PostgreSQL server you control. The test suite truncates all Arletion tables in that database. Do not point `ARLETION_TEST_DATABASE_URL` at a working or production database. Then run:

```powershell
$env:DATABASE_URL = "postgresql+psycopg://TEST_USER:TEST_PASSWORD@127.0.0.1:5432/arletion_test"
$env:ARLETION_TEST_DATABASE_URL = $env:DATABASE_URL
Push-Location services\api
..\..\.venv\Scripts\alembic.exe upgrade head
..\..\.venv\Scripts\alembic.exe current
..\..\.venv\Scripts\alembic.exe upgrade head
..\..\.venv\Scripts\python.exe -m unittest discover -s tests -v
Pop-Location
```

The second migration command checks repeat execution. `/live` is a process liveness endpoint; `/health` is readiness and checks PostgreSQL connectivity, all required tables, and the expected Alembic revision.

### National Treasury eTender import

Read [the connector notes](docs/etender-import.md) before importing. The official endpoint and query contract are documented in Treasury's OpenAPI spec. Start with a small page and verify each record against its original notice. To import one API page from the running Arletion API, call `POST /api/v1/opportunities/import/official` with JSON such as `{"page_number":1,"page_size":25,"date_from":"2024-01-01","date_to":"2024-01-31"}`. The API currently rejects requests without both date filters even though the published schema does not mark them as required. For a locally downloaded OCDS JSON package or CSV, use `POST /api/v1/opportunities/import` with `{"format":"json","content":"..."}` or `{"format":"csv","content":"..."}`. The CLI accepts the same files without sending them through the API: `python -m app.import_cli path\to\release.json --format json` from `services\api`.

Treasury's published dataset is not a complete national tender register. Its publication guide says it includes records shared with National Treasury and warns that accuracy, completeness and timeliness are not guaranteed; never infer an open tender without a supplied active status and a future closing date.

### Docker Compose

Prerequisites: Docker Desktop with its Linux engine running. Copy `.env.example` to `.env`, change the local database password, then run `docker compose up --build`.

Dashboard: http://localhost:3000  
API docs: http://localhost:8000/docs

This is a development starter, not production-ready. A single local workspace tenant is currently used by the API; authentication, tenant authorization, connector approval, backups and security tests are still required before public deployment or real consumer data. Docker Engine must be running to verify Compose services.

## First source-validation task
Read `docs/source-register.md`; validate the National Treasury eTender data guide and access terms; download a small sample; inspect identifiers, status fields, update behaviour and coverage limitations. Only then implement a connector.

## Brand
The supplied brand artwork is in `apps/web/public/`: `arletion-icon.png` is used for the app icon, `arletion-logo.png` for the dashboard sidebar, with the original emblem and logo variants retained as `arletion-emblem.png`, `arletion-logo-variant.png`, and `arletion-mainlogo.png`.
Maroon `#5B0F1A`, red `#D62828`, gold `#D4AF37`, white `#FFFFFF`, black `#0B0B0B`, midnight purple `#1A0B2E`.
Tagline: **Find • Qualify • Unlock • Grow**.
#


## Protected Render preview deployment

A private-preview Blueprint is provided in render.yaml. It creates the web frontend, FastAPI service and PostgreSQL database, generates a server-side API key, protects the dashboard with HTTP Basic authentication, and requires the API key for all /api/v1/* requests. The web server proxies dashboard API requests server-side; no API key is exposed to browser JavaScript.

**This is a private preview, not production hosting.** The Blueprint uses Render Free services and a Free Postgres database. Render documents that free web services can spin down and that free Postgres databases expire after 30 days, have no backups and are unsuitable for production. Do not store client leads, consumer enquiries or other sensitive data in this preview database. See https://render.com/docs/free.

### Deploy the preview

1. Push or merge the reviewed deployment branch to the repository branch you intend to deploy.
2. Sign in to https://dashboard.render.com/ and connect the GitHub account that owns Derrick121K/Arletion.
3. Choose New → Blueprint, select this repository and review render.yaml.
4. Confirm the free database's 30-day expiry warning before creating resources.
5. When prompted for ARLETION_BASIC_AUTH_USER and ARLETION_BASIC_AUTH_PASSWORD, enter strong unique credentials and save them in Render's secret configuration. Never commit them.
6. Create the services and wait for both the API /health check and frontend /healthz check to pass.
7. Open the frontend URL; the browser should prompt for Basic Auth. Confirm /healthz returns 200, the browser cannot access the dashboard without credentials, and the dashboard loads through the server-side API proxy.
8. Verify that direct API calls to /api/v1/* without the generated bearer key return 401.
9. Keep the database empty during this preview. Before production, move to a durable PostgreSQL plan/provider with backups, implement real user accounts and tenant-level authorization, and run the security/restore checks.

The API health route /live is liveness only. /health checks the database schema and migration revision. Frontend /healthz is a process health check and does not claim that the API/database is ready.

### Deployment architecture

- arletion-web: Next.js frontend, Basic Auth gate and server-side API proxy.
- arletion-api: FastAPI service, database migrations at startup and bearer API-key protection.
- arletion-db: PostgreSQL, connected through Render's private network.
- .github/workflows/ci.yml: builds/tests the frontend and runs API integration tests against a disposable PostgreSQL service on GitHub Actions.

The deployment Blueprint is intentionally a preview guardrail. Basic Auth is a shared workspace gate, not a substitute for real individual accounts, tenant membership, session management, CSRF protections for browser mutation flows, or production authorization review.
