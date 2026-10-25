# Architecture decisions — Arletion v0.1
- API-first: dashboard is a client of versioned FastAPI endpoints.
- PostgreSQL is the intended durable system of record.
- Connector adapters are independent and replaceable.
- Campaigns store lead type, geography, criteria, scoring and workflow configuration.
- Shared canonical organisations are separate from tenant-specific lead state and notes.
- Source evidence and observation timestamps are first-class records.
- Starter uses explicitly labelled demo fixtures only.
- No live scraping, marketing automation or consumer-data ingestion is enabled.

Before production: implement authentication, tenant enforcement, migration management, connector review, secrets handling, rate limiting, backups, monitoring, consent/suppression and deletion workflows.
