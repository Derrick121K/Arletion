# Tally free webhook import

Arletion accepts voluntary debt-review enquiry submissions from a Tally form. Tally describes its webhook integration as free for all users. A webhook forwards a submission; it does not find people or create enquiries by itself.

## Endpoint

POST https://arletion-api.onrender.com/api/v1/webhooks/tally

The endpoint expects a Tally JSON webhook with:
- eventType = FORM_RESPONSE
- data.formId matching ARLETION_TALLY_FORM_ID
- a unique eventId
- a Tally-Signature header generated with the same signing secret configured in Render

The API verifies Tally's Base64 SHA-256 HMAC signature using ARLETION_TALLY_WEBHOOK_SECRET, compares it in constant time, checks the form ID, verifies the campaign and source approval gates, and deduplicates retries by eventId. It also deduplicates the same contact within the consumer campaign.

## Tally form questions and labels

Use these exact labels so Arletion can map the submitted values:
- Full name (required)
- Phone number (required when Phone or WhatsApp is the preferred channel)
- Email address (required when Email is the preferred channel)
- Province
- Town / locality
- Preferred contact channel (Phone, WhatsApp or Email)
- Debt-review situation (Considering debt review, Already under debt review, Application pending, Debt-review assistance, Completed debt review, Debt counselling, Budget guidance, or General enquiry)
- I confirm I am 18 years or older (required checkbox with an affirmative option)
- I consent to Arletion processing my details to respond to this enquiry (required checkbox with affirmative option)
- I agree to receive optional marketing messages (optional checkbox; unchecked by default)

Do not collect South African ID numbers, bank details, credit account numbers, creditor lists, salaries, passwords or detailed financial history in the Tally form. Do not ask whether a person is currently under debt review unless the person is voluntarily self-declaring it as part of their enquiry.

## Render API environment

Configure these values in the arletion-api service:
- ARLETION_TALLY_WEBHOOK_ENABLED=true
- ARLETION_TALLY_WEBHOOK_SECRET=<the same secret entered in Tally>
- ARLETION_TALLY_FORM_ID=<Tally form ID>
- ARLETION_TALLY_CAMPAIGN_ID=<active Arletion consumer enquiry campaign UUID>
- Existing consumer storage, encryption, consent, and retention settings must already pass Arletion's consumer storage checks.

In the Arletion Source Registry, review Tally's current processor terms and privacy obligations, then explicitly enable "Tally Voluntary Consumer Enquiry Webhook". The source is seeded disabled and review-required.

## Campaign configuration

Create an active Consumer debt enquiries campaign with the "Accept Tally webhook submissions" option enabled. Copy its campaign UUID into ARLETION_TALLY_CAMPAIGN_ID. Do not enable Tally imports until the form field labels, privacy notice, storage, staff access and processor arrangements have been reviewed.

## Behaviour

- Invalid/missing signatures are rejected with 401.
- Wrong form IDs and non-FORM_RESPONSE events are rejected.
- Missing age confirmation or processing consent is rejected.
- Tally webhook retries for the same event ID return an accepted duplicate result and do not create another enquiry.
- A repeated contact within the campaign is accepted as a duplicate without creating another enquiry.
- Consumer contact details are encrypted by the existing consumer intake path. The webhook event audit record stores event metadata, a body hash and the category only, not name, email or phone.
- Marketing permission is only recorded when the optional marketing checkbox is explicitly selected. It is not inferred from processing consent.
- The importer sends no messages, referrals or outreach.

## Manual test

1. Create the Tally form with the exact labels above.
2. Publish the form and add a webhook pointed at the endpoint.
3. Add a signing secret in Tally and set the same value in Render.
4. Enable the Tally source after reviewing processor terms.
5. Create and configure an active Arletion consumer campaign.
6. Submit a test enquiry using your own details and consent.
7. Confirm one protected enquiry appears in Consumer enquiries, then use Tally's delivery log or retry to confirm Arletion reports a duplicate event rather than adding another row.
