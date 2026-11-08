# Free lead sources and verification controls

## 1. National Treasury eTender / OCDS
- The official portal publishes a public paginated OCDS JSON API and monthly downloadable CSV, JSON and Excel data.
- Detailed bulk procurement data is licensed CC BY 4.0; retain attribution and provenance. Verify the API's own applicable terms before commercial use.
- The publisher states the dataset is a subset of procurement data shared with National Treasury and is currently in public beta. It is not a complete national tender or supplier register.
- Arletion can import multiple pages per run (up to 4 × 100 releases) and resume from the returned next page. The user can repeat the next batch over a selected date range.
- Supplier leads are extracted from published awards only when the supplier name clearly indicates a company legal form. Natural-person names are not turned into business prospects.
- A company named as a supplier in a published award is labelled `source_confirmed`, not CSD-verified, currently trading or contactable.

Official pages:
- https://data.etenders.gov.za/
- https://data.etenders.gov.za/Home/LearnMore
- https://ocds-api.etenders.gov.za/swagger/index.html

## 2. OpenStreetMap data
- OSM map data is available under ODbL 1.0 and requires attribution.
- The shared public Overpass service is for small workloads. Its published usage policy recommends self-hosted or paid services for commercial workloads. Arletion must not send commercial production queries to that shared public server.
- Configure `ARLETION_OVERPASS_URL` to a self-hosted or paid HTTPS endpoint before the connector is enabled. The free hosted preview intentionally leaves this variable unset and seeds the source as review-required/disabled.
- An OSM feature means a named business-like map object was present at import time. It does not prove the business is operating, CIPC-registered, CSD-active or contactable.
- Import keeps object ID, source link, category, source timestamp and attribution. It excludes phone/email tags and contributor usernames.
- Local discovery is deliberately bounded to 15 km and 200 records per run.

## 3. Official supplier verification
- The CSD is the government's authoritative supplier database; the public portal directs supplier access through a login.
- Arletion does not bypass CSD login, scrape a private session or claim CSD status from an award listing.
- An operator can record a manual CSD/CIPC check using an official evidence URL, reference and check timestamp. Positive checks become `officially_verified`; negative or uncertain checks become `needs_review`. Each action creates an audit event.
- CSD portal: https://secure.csd.gov.za/
- CIPC developer portal: https://developer.cipc.co.za/

## 4. Lead qualification and outreach
- `source_confirmed` records may be useful discovery prospects, but the source evidence is not an endorsement or marketing permission.
- Check current registration and trading status before treating a supplier as procurement-ready.
- Do not infer contact consent from a public website or source listing. No automated email, SMS, calls or WhatsApp outreach is enabled.
- Do not collect or import consumer debt details in the business pipeline.

