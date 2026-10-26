# Deployment runbook — Arletion private preview

## Scope

The Render Blueprint in the repository is for a guarded preview, not a production launch. It deploys:
- Next.js web service (arletion-web)
- FastAPI API (arletion-api)
- PostgreSQL (arletion-db)

The UI uses HTTP Basic Auth at the Next.js proxy layer. The proxy forwards requests server-side and reads the API key only from server-side environment variables. The API requires a bearer key for all /api/v1/* routes when ARLETION_REQUIRE_API_KEY=true.

## Before deploying

1. Confirm the current branch CI passes.
2. Connect the GitHub repository to Render.
3. Create a Blueprint from render.yaml.
4. Supply strong unique values for ARLETION_BASIC_AUTH_USER and ARLETION_BASIC_AUTH_PASSWORD.
5. Confirm Render generates an API key on the API service and the web service references that key.
6. Confirm the database uses the private Render connection string; do not paste it into GitHub.
7. Confirm the public web URL is not assumed to be accessible without Basic Auth.

## Free-preview limitations

The Blueprint uses Render Free services to minimise initial cost. Render's current free-tier documentation says free web services can spin down and free Postgres databases:
- expire 30 days after creation,
- have a 1 GB storage limit,
- do not have backups, and
- are intended for previews/hobby testing rather than production.

Source: https://render.com/docs/free

Do not add real client leads, personal data, consumer enquiries or secrets to this preview. Before any production use, move to a durable database plan/provider with backups and recovery testing. Confirm current provider limits and costs before deployment.

## Deployment verification

After Render creates services, verify all of the following:

- Web /healthz returns HTTP 200.
- API /live returns HTTP 200.
- API /health returns HTTP 200 only after database connectivity and the expected migration revision are verified.
- The dashboard requires Basic Auth credentials.
- The browser calls the same-origin /api/backend proxy.
- Direct API request to /api/v1/summary without a bearer key returns HTTP 401.
- A request through the authenticated web proxy receives data from the API.
- A sample opportunity imported from an official source is persisted and still visible after API restart.
- No API key, database URL or Basic Auth password appears in frontend JavaScript, source maps, logs or Git history.

## Required before production

The current platform still uses a single default workspace tenant and lacks individual user accounts, tenant-membership authorisation and complete consent/suppression workflows. HTTP Basic Auth is a shared preview gate only. Do not store customer data or expose this build as a multi-client production service until those controls are implemented, tested, and reviewed.
