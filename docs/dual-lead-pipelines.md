# Arletion dual lead pipelines

## Pipeline 1 — Business and procurement
- Uses the existing organisation, source-evidence, lead and official OCDS procurement opportunity models.
- Business categories include construction, building materials, transport and logistics, IT/software, training/education, cleaning/facilities, security, agriculture, manufacturing, retail/wholesale and professional services.
- Procurement notices remain opportunities, not presumed sales leads or personal marketing lists.
- Only approved source access methods may collect business evidence. Public availability does not automatically grant marketing permission.

## Pipeline 2 — Consumer debt-counselling enquiries
- Separate campaign type: `consumer_enquiry`.
- Enquiry categories are deliberately broad: debt counselling, debt-review information, budget guidance and general.
- Only minimal contact and routing data are collected: name, phone and/or email, broad locality/province, preferred response channel, enquiry category, source and consent evidence.
- No ID numbers, account numbers, creditor lists, balances, payslips, bank information, credit reports or detailed debt narratives are accepted in the lead intake model.
- Name, phone and email are Fernet-encrypted. A keyed HMAC fingerprint supports duplicate detection without storing a plain contact lookup key.
- List responses exclude all decrypted contact values. A separate server-side consumer-contact credential is required to decrypt a specific enquiry.
- A distinct required consent records permission to process/respond to the enquiry. Electronic direct marketing is a separate opt-in. Withdrawal records a suppression entry and revokes the marketing grant.
- Consumer intake is disabled by default. The public consumer form is not implemented and no public write route is enabled.

## Activation requirements
1. Move away from Render Free Postgres to durable managed Postgres with tested automated backups and restore.
2. Configure `ARLETION_PII_ENCRYPTION_KEY` (Fernet key), `ARLETION_CONTACT_HASH_KEY` (32+ random characters), and `ARLETION_CONSUMER_ACCESS_KEY` as server-only secrets. Establish key rotation and recovery procedures before receiving any records.
3. Replace the shared preview login/API credential with individual user accounts, roles and audited access to consumer contact decryption.
4. Verify the privacy notice, responsible-party/operator allocation, purpose and retention schedule, direct-marketing consent copy and data-subject request workflow with the Information Officer/legal adviser.
5. Implement the scheduled expiry/purge job and verify backup retention/deletion rules.
6. Complete NCC National Consumer Opt-Out Registry registration/list-cleansing checks before any outbound direct marketing. Arletion currently has no registry connector.
7. Implement and test an anti-abuse public form (CSRF, rate limits, CAPTCHA/bot protection, request size limits, monitoring and incident response) before enabling public submission.
8. Connect Google/Meta lead forms only with client-approved credentials and field mapping. WhatsApp messaging remains disabled until a supported provider, opt-in, templates and opt-out handling are configured.

## Current environment
The hosted Render preview intentionally sets:
- `ARLETION_CONSUMER_INTAKE_ENABLED=false`
- `ARLETION_CONSUMER_STORAGE_APPROVED=false`
- `ARLETION_CONSUMER_RETENTION_DAYS=90`

The free Postgres database is temporary and has no backups. The consumer intake code must not be activated in this environment. Its records remain isolated and encrypted in the schema, but the activation flag is the required guard.
