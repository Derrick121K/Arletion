# Arletion source register

Arletion separates source discovery from verification and marketing permission. A source match does not mean a company is currently trading, CIPC registered, CSD active or available to contact.

| Source | Use | Access and licence | Status in Arletion | Verification scope |
|---|---|---|---|---|
| National Treasury eTender Transparency Portal | Procurement notices, awards and company-form awarded suppliers | Public OCDS REST API and monthly downloads. The portal documents CC BY 4.0 for detailed downloads; the API specification declares its own data terms. Review the applicable API terms for each use. | Official source; operator approval required before import | A company name is confirmed as present in a published release/award. This does not prove current CSD registration, tax status or current trading. |
| OpenStreetMap / Overpass API | Local business discovery by category and radius | OpenStreetMap data is free under ODbL 1.0. Commercial production queries require a self-hosted or paid Overpass endpoint; Arletion does not use the shared public instance. | Seeded as review required and disabled until endpoint configuration and source review | A named map feature was present in OSM at import time. It is not a business-register or trading-status verification. |
| Central Supplier Database (CSD) | Official government supplier registration/status checks | Official portal is available at https://secure.csd.gov.za/. Search and registration report workflows require user access; no public bulk API connector is enabled. | Manual verification link only | Check the supplier's current registration status and the CSD report before marking a supplier officially verified. |
| CIPC APIVerse | Company identity and registration checks | Official API portal at https://developer.cipc.co.za/ uses OAuth; access/pricing and reuse scope must be confirmed with CIPC. | Not connected | Do not mark CIPC verified without a successful authorised registry response or dated manual registry evidence. |
| Client-owned enquiry forms | Voluntary consumer enquiries | Client-controlled | Separate consumer intake; disabled until privacy and storage gates pass | Enquiry processing consent and marketing opt-in are separate states. |

## OpenStreetMap operating limits
- Set `ARLETION_OVERPASS_URL` to a self-hosted or paid HTTPS Overpass endpoint before enabling commercial imports.
- The environment variable is intentionally unset in the free preview. The source is seeded as review-required and disabled; the public shared Overpass service is not called by default.
- The UI limits a search to a 15 km radius and 200 records. The API applies a source cooldown and a request timeout.
- The source link points to the original OSM object (node, way or relation). Arletion retains the OSM object ID, source link, map edit timestamp where supplied, import timestamp, category and attribution.
- Arletion does not import OSM phone/email tags. It stores the public business website domain where present.
- Display attribution: © OpenStreetMap contributors · ODbL 1.0 with a link to https://www.openstreetmap.org/copyright.

## Verification labels
- Unverified: manually entered or otherwise not matched to an attributable source.
- Source-confirmed: a named business/supplier record was found in the cited OSM feature or official eTender OCDS award. This is not equivalent to CIPC/CSD verification.
- Officially verified: reserved for a completed CIPC/CSD check with source, reference and date recorded. No automated official-registry connector is currently enabled.
- Needs review: conflicting, stale or incomplete evidence.

## Connector approval checklist
- [ ] Official owner and documentation identified.
- [ ] Intended access method and reuse rights reviewed.
- [ ] Commercial use and derived-data rules checked.
- [ ] Rate limits, quotas, authentication and costs documented.
- [ ] Sample checked for freshness, completeness and identifiers.
- [ ] Attribution and retention rules implemented.
- [ ] Retry/backoff, monitoring and kill switch tested.
- [ ] Known omissions and quality limitations shown to users.

Public contact details are not, by themselves, permission to send unsolicited electronic marketing.