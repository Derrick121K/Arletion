# Privacy and security launch gates
- Treat discovery, qualification, verification and marketing permission as separate states.
- Minimise personal information; record source, purpose, observation date and permitted use.
- Do not treat public visibility as marketing consent.
- Check suppression and withdrawal before applicable outreach.
- Keep sensitive client data tenant-isolated and out of general logs/analytics.
- Never expose provider secrets or database credentials in browser code.
- Use scoped, revocable API credentials.
- Test cross-tenant access and export authorisation.
- Define retention, correction, deletion, incident response and recovery.
- Review POPIA, direct-marketing rules and sector requirements before production.

## Dual lead pipelines — additional safeguards
- Business/procurement records remain in the organisation/evidence pipeline. Consumer enquiries use the separate `consumer_enquiries` table and dedicated API routes.
- Consumer name, phone and email are Fernet-encrypted before database writes. Contact deduplication uses a keyed HMAC fingerprint; raw contact details are not used as database search keys.
- Consumer list responses contain only protected metadata. Decryption requires a separate `X-Arletion-Consumer-Access` credential; never place that credential in browser code.
- Permission to respond to a submitted enquiry and permission for electronic direct marketing are separate records. Marketing permission is opt-in only and can be withdrawn; a suppression record is created on withdrawal.
- Do not collect South African ID numbers, bank details, creditor/account lists, account balances, employer details, or narrative debt histories in the lead form. Transfer such case information only to an appropriately secured, authorised debt-counselling case-management process.
- Consumer intake defaults to disabled. Enabling requires durable backed-up storage, a valid Fernet key, a keyed fingerprint secret, a separate contact-access secret, a retention period, and operational access controls.
- Consumer enquiry data has a configurable retention expiry (30–365 days, default 90). A scheduled purge/deletion job and evidence of restore testing remain launch gates; an expiry timestamp alone does not delete data.
- The current preview still uses a shared Basic Auth gate and a shared API key, not individual staff accounts or role-based authorisation. Keep consumer intake disabled until those access controls are replaced.
- No outreach, automated calls, WhatsApp messages, email or SMS is sent by Arletion. A captured enquiry is not marketing permission.

## South African direct-marketing controls
- Apply POPIA section 69 and the Information Regulator's current direct-marketing guidance to unsolicited electronic marketing.
- Keep the Form 4 consent evidence, notice version, time, channel and purpose. Do not use pre-ticked consent or bundle enquiry handling with marketing permission.
- Monitor the National Consumer Commission's National Consumer Opt-Out Registry rollout. Confirm registration and list-cleansing obligations with counsel/the NCC before a campaign is activated; Arletion has no registry integration yet.
- Have the responsible party / Information Officer confirm the lawful basis, privacy notice, retention period, operator agreements, cross-border processing, complaint process and incident response before intake opens.

