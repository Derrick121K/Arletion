# Debt-review lead acquisition

## Separate lead types

- Business and procurement prospects remain in the organisation lead pipeline.
- Registered debt counsellors discovered from the NCR's public registered directory are stored as 'partnership' leads, categorised as 'Debt counselling partners'.
- Consumers are never scraped or inferred from debt records. They enter only by submitting a voluntary enquiry form.
- Consumer categories include considering debt review, already under review, application pending, debt-review assistance, completed debt review, debt counselling, budget guidance and general enquiries.

## Public consumer form

- Public page: /enquire; privacy notice: /privacy.
- Server route: /api/public/enquiries forwards to the API using server-side ARLETION_API_KEY.
- Backend route: POST /api/v1/public/consumer-enquiries.
- The form requires age confirmation (18+), processing consent, and at least one contact method. Marketing opt-in is optional and separate.
- No ID number, bank detail, credit account, creditor list, salary or detailed debt history is collected.
- Consumer contact data is encrypted at rest and excluded from ordinary list responses.
- A public campaign must be created as a consumer enquiry campaign with criteria.public_intake=true and active status.
- Both ARLETION_CONSUMER_INTAKE_ENABLED=true and ARLETION_PUBLIC_CONSUMER_FORM_ENABLED=true are required, together with storage approval, access approval, encryption, fingerprint and separate contact-access secrets.
- Render keeps the public-form switch off by default.

The Next.js public route has an in-memory, per-process rate limit and a honeypot. This is an initial abuse-control layer, not a distributed rate limiter. Add a shared rate-limit store and/or a challenge provider before production exposure. Do not represent this as bot-proof.

Before public launch, require durable backed-up PostgreSQL, individual staff accounts and role-based access, tested retention deletion, restore checks, incident response, and approval of the privacy notice by the responsible party / Information Officer.

## NCR debt counsellor partners

- Source: https://www.ncr.org.za/register_of_registrants/registered_dc.php
- Only records parsed from the NCR's registered debt counsellor listing are imported.
- Search by name, NCR registration number or town where the NCR search page supports the query; imports are bounded to one page (maximum 100 parsed entries) and one request per minute.
- The source is seeded as review_required and disabled. An operator must review the source and explicitly approve it in Source Registry.
- Stable NCR registration numbers are used for repeat-import matching.
- Only business/partner lead metadata is retained: trading name (or a generic registration label), registration number, registration date, town, status, source URL and observation time. The import does not retain personal phone/email contact fields or the full name where a trading name is unavailable.
- source_confirmed means the directory showed the counsellor in its registered list at import time. It is not legal advice or an endorsement, and status should be rechecked before any referral.
- No outreach, referral or data transfer is automated.

## Testing

- API unit tests cover NCR HTML parsing and category validation.
- PostgreSQL integration tests cover public form gating, encryption, consent separation, NCR source approval, partner lead import and duplicate refresh.
- Frontend tests cover public form controls, public proxy routing and NCR import calls.
- Run API tests with an isolated PostgreSQL test database and run frontend lint, typecheck, tests and build. Do not point tests at production.
