# Implementation plan
1. Source validation: inspect eTender sample/schema and access terms; assess OSM extract/licence; confirm CIPC API access.
2. Core platform: authentication, tenant memberships, campaign CRUD, evidence, lead list/detail, audit and exports.
3. Connectors: eTender first, then approved business discovery and enrichment. Use idempotent imports and preserve source history.
4. Qualification: configurable scoring, explanation, review, assignment, activity tracking and reporting.
5. Client pilot: configure separate client workflows. ELEVATE begins with voluntary enquiries and partnership discovery, not inferred financial-distress profiling.
6. Production readiness: tenant isolation, retention, backups, monitoring, quotas and deployment hardening.
