# National Treasury eTender import

## Official contract checked

- Portal: <https://data.etenders.gov.za/>
- Data user guide and publication policy: <https://data.etenders.gov.za/Home/LearnMore>
- OpenAPI document: <https://ocds-api.etenders.gov.za/swagger/v1/swagger.json>
- Release endpoint: `GET https://ocds-api.etenders.gov.za/api/OCDSReleases`
- Query fields documented by the official OpenAPI document: `PageNumber`, `PageSize`, `dateFrom`, and `dateTo`. The response is a release package whose `releases` contain `ocid`, `id`, `date`, `tender`, `buyer`, `awards` and `contracts`.
- Relevant tender fields include `title`, `status`, `mainProcurementCategory`, `tenderPeriod.startDate` and `tenderPeriod.endDate`. Amendment history is represented by releases for the contracting process OCID.

The portal says downloadable monthly OCDS releases are available as JSON, CSV and XLSX, dating back to May 2021. Its guide describes an API as paginated and searchable by OCID, release date and buyer. A one-release request was live-tested on 24 October 2026 and returned a JSON `ReleasePackage`. The endpoint returned HTTP 400 with `dateFrom and dateTo fields are required` when both filters were omitted, although neither is marked required in the published query schema. Requests must supply both dates. The API's OpenAPI spec declares an ODC Public Domain Dedication and Licence (PDDL) 1.0 link, while the portal homepage describes its bulk downloads as CC BY 4.0. Keep both source statements in view, preserve the source link and date, and review the exact applicable terms before redistribution. No National Treasury endorsement is implied.

## Coverage and reliability limitations

The portal guide says coverage is limited to procurement data shared with National Treasury; not every municipality or state-owned entity is obliged to share it. Its records cover planning, tendering, awards and contracting stages, and OCDS releases provide change history by OCID. The portal states that data is in public beta and does not guarantee accuracy, completeness or timeliness. Its publication policy also says personal information that has not been consented for publication is excluded; do not use these records to infer personal information.

An imported opportunity is labelled `open` only when the source tender status is `active` and its supplied closing date is after the local date. Active records with no closing date are marked `active_date_unverified`; records closing today are `closing_today`; past dates are `expired`. These derived labels are not legal or bid advice. Verify the issuing buyer's latest notice and attachments before acting. Cancelled, withdrawn and complete source statuses are retained; all other values remain unconfirmed.

## Import and provenance behavior

JSON accepts an OCDS release package, an individual release, or a list of records. CSV accepts a header row with flat fields such as `ocid`, `title`, `buyer_name`, `category`, `publication_date`, `closing_date`, `status`, and `source_url`; common slash/dot forms of OCDS fields are also recognized. The separate monthly CSV package is multi-table; select and transform its tender/release rows into this documented flat CSV form if the archive is not a single release table. Keep the original file and record its download date outside the app when you need a complete archival audit trail.

Rows missing a stable source identifier or title are skipped. OCID is the preferred external ID. Repeated imports upsert by `(source_id, external_id)`, preserving the latest release payload and hash in `source_records`; repeated identical payloads are unchanged, and older amendments are ignored. Original tender document URLs are used when supplied; otherwise the official portal URL is retained as source provenance. No record is added from an example or synthetic fixture.

The API page importer fetches one bounded page (up to 100 releases) per request. Use `date_from`, `date_to` and successive `page_number` values to control import size. Confirm network access and inspect the returned counts before continuing with more pages.
