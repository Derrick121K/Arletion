from __future__ import annotations

import csv
import hashlib
import io
import json
from datetime import date, datetime, timezone
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from .database import ETENDERS_SOURCE_ID
from .models import Opportunity, SourceRecord, SourceRegistry

ETENDERS_PORTAL = "https://data.etenders.gov.za/"
ETENDERS_API = "https://ocds-api.etenders.gov.za/api/OCDSReleases"


def parse_date(value: Any) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _releases(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        if isinstance(payload.get("releases"), list):
            return [item for item in payload["releases"] if isinstance(item, dict)]
        if isinstance(payload.get("items"), list):
            return [item for item in payload["items"] if isinstance(item, dict)]
        if isinstance(payload.get("ocid"), str) or isinstance(payload.get("title"), str):
            return [payload]
        raise ValueError("JSON must be an OCDS release/package or a list of opportunity records.")
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    raise ValueError("Import payload must be a JSON object or array.")


def _field(record: dict[str, Any], *names: str) -> Any:
    for name in names:
        value = record.get(name)
        if value not in (None, ""):
            return value
    return None


def parse_import(content: str, file_format: str) -> list[dict[str, Any]]:
    if file_format == "json":
        return _releases(json.loads(content))
    if file_format == "csv":
        reader = csv.DictReader(io.StringIO(content))
        if not reader.fieldnames:
            raise ValueError("CSV must include a header row.")
        rows = [dict(row) for row in reader]
        if not rows:
            raise ValueError("CSV contains no opportunity rows.")
        return rows
    raise ValueError("format must be either 'json' or 'csv'.")


def normalize_record(record: dict[str, Any]) -> dict[str, Any] | None:
    tender = record.get("tender") if isinstance(record.get("tender"), dict) else {}
    buyer = record.get("buyer") if isinstance(record.get("buyer"), dict) else {}
    procuring_entity = tender.get("procuringEntity") if isinstance(tender.get("procuringEntity"), dict) else {}
    classification = tender.get("classification") if isinstance(tender.get("classification"), dict) else {}
    tender_period = tender.get("tenderPeriod") if isinstance(tender.get("tenderPeriod"), dict) else {}

    ocid = _field(record, "ocid", "OCID")
    external_id = str(ocid or _field(record, "external_id", "externalId", "id") or "").strip()
    title = tender.get("title") or _field(record, "title", "Title", "tender/title", "tender.title")
    if not external_id or not title:
        return None

    closing_date = parse_date(tender_period.get("endDate") or _field(record, "closing_date", "closingDate", "tender/tenderPeriod/endDate", "tender.tenderPeriod.endDate"))
    publication_date = parse_date(record.get("date") or tender_period.get("startDate") or _field(record, "publication_date", "publicationDate", "tender/tenderPeriod/startDate", "tender.tenderPeriod.startDate"))
    release_date = None
    if record.get("date"):
        try:
            release_date = datetime.fromisoformat(str(record["date"]).replace("Z", "+00:00"))
            if release_date.tzinfo is None:
                release_date = release_date.replace(tzinfo=timezone.utc)
        except ValueError:
            release_date = None

    documents = tender.get("documents") if isinstance(tender.get("documents"), list) else []
    original_url = _field(record, "source_url", "sourceUrl", "url", "tender/documents/0/url")
    if not original_url:
        original_url = next((d.get("url") for d in documents if isinstance(d, dict) and d.get("url")), ETENDERS_PORTAL)

    source_status = str(tender.get("status") or _field(record, "status", "tender/status", "tender.status") or "").lower()
    awards = record.get("awards") if isinstance(record.get("awards"), list) else []
    contracts = record.get("contracts") if isinstance(record.get("contracts"), list) else []
    if source_status in {"complete", "cancelled", "withdrawn"}:
        status = source_status
    elif closing_date and closing_date < date.today():
        status = "expired"
    elif source_status == "active":
        if closing_date is None:
            status = "active_date_unverified"
        elif closing_date == date.today():
            status = "closing_today"
        else:
            status = "open"
    elif awards or contracts:
        status = "awarded" if awards else "contracted"
    else:
        status = source_status or "unknown"

    return {
        "external_id": external_id,
        "release_id": str(_field(record, "id", "release_id") or external_id).strip(),
        "source_record_id": f"{external_id}#{str(_field(record, 'id', 'release_id') or external_id).strip()}",
        "ocid": str(ocid) if ocid else None,
        "title": str(title).strip(),
        "description": tender.get("description") or _field(record, "description", "tender/description", "tender.description"),
        "buyer_name": buyer.get("name") or procuring_entity.get("name") or _field(record, "buyer_name", "buyer/name", "buyer.name", "buyer"),
        "category": classification.get("description") or tender.get("mainProcurementCategory") or _field(record, "category", "tender/mainProcurementCategory", "tender.mainProcurementCategory"),
        "province": record.get("province") or record.get("region"),
        "publication_date": publication_date,
        "closing_date": closing_date,
        "status": status,
        "source_url": str(original_url),
        "source_updated_at": release_date,
        "raw_payload": record,
    }


def import_opportunities(session: Session, records: Iterable[dict[str, Any]]) -> dict[str, int]:
    source = session.get(SourceRegistry, ETENDERS_SOURCE_ID)
    if source is None:
        source = session.scalar(select(SourceRegistry).where(SourceRegistry.name == "National Treasury eTender Transparency Portal"))
    if source is None:
        raise RuntimeError("The eTender source registry row is missing. Run the initial migration and seed the API once.")
    normalized: dict[str, dict[str, Any]] = {}
    releases: dict[str, dict[str, Any]] = {}
    skipped = 0
    duplicates = 0
    for record in records:
        item = normalize_record(record)
        if item is None:
            skipped += 1
            continue
        releases[item["source_record_id"]] = item
        previous = normalized.get(item["external_id"])
        if previous is not None:
            duplicates += 1
            old_date = previous["source_updated_at"]
            new_date = item["source_updated_at"]
            if old_date and new_date and new_date < old_date:
                continue
        normalized[item["external_id"]] = item

    inserted = updated = unchanged = stale = 0
    for source_record_id, item in releases.items():
        content_hash = hashlib.sha256(json.dumps(item["raw_payload"], sort_keys=True, default=str, ensure_ascii=False).encode()).hexdigest()
        prior = session.scalar(select(SourceRecord).where(SourceRecord.source_id == source.id, SourceRecord.external_id == source_record_id))
        if prior is not None and prior.payload_hash == content_hash:
            continue
        release_values = {
            "source_id": source.id,
            "external_id": source_record_id,
            "record_type": "ocds_release",
            "source_url": item["source_url"],
            "source_updated_at": item["source_updated_at"],
            "payload_hash": content_hash,
            "raw_payload": item["raw_payload"],
        }
        release_statement = insert(SourceRecord).values(**release_values).on_conflict_do_update(
            constraint="source_records_source_external_uq",
            set_={key: value for key, value in release_values.items() if key not in {"source_id", "external_id"}},
        )
        session.execute(release_statement)

    for external_id, item in normalized.items():
        existing = session.scalar(select(Opportunity).where(Opportunity.source_id == source.id, Opportunity.external_id == external_id))
        latest_record = None
        if item["ocid"]:
            latest_record = session.scalar(
                select(SourceRecord)
                .where(SourceRecord.source_id == source.id, SourceRecord.record_type == "ocds_release", SourceRecord.raw_payload["ocid"].as_string() == item["ocid"])
                .order_by(SourceRecord.source_updated_at.desc().nullslast(), SourceRecord.observed_at.desc())
            )
        if existing is None:
            inserted += 1
        else:
            if existing.ocid and item["ocid"] and existing.ocid != item["ocid"]:
                raise ValueError(f"Source identifier collision for {external_id!r}: the existing OCID does not match.")
            old_release = latest_record.source_updated_at if latest_record else None
            if old_release and item["source_updated_at"] and item["source_updated_at"] < old_release:
                stale += 1
                continue
        opportunity_values = {key: value for key, value in item.items() if key not in {"raw_payload", "source_updated_at", "release_id", "source_record_id"}}
            if latest_record and latest_record.external_id == item["source_record_id"] and latest_record.payload_hash == hashlib.sha256(json.dumps(item["raw_payload"], sort_keys=True, default=str, ensure_ascii=False).encode()).hexdigest():
                if all(getattr(existing, key) == value for key, value in opportunity_values.items()):
                    unchanged += 1
                    continue
            updated += 1
        if existing is not None:
            opportunity_values["id"] = existing.id
        statement = insert(Opportunity).values(source_id=source.id, **opportunity_values)
        statement = statement.on_conflict_do_update(
            constraint="opportunities_source_external_uq",
            set_={key: value for key, value in item.items() if key not in {"external_id", "raw_payload", "source_updated_at", "release_id", "source_record_id"}},
        )
        session.execute(statement)

    source.last_synced_at = datetime.now(timezone.utc)
    source.last_error = None
    session.commit()
    return {"inserted": inserted, "updated": updated, "unchanged": unchanged, "stale_releases": stale,
            "duplicates_in_input": duplicates, "skipped": skipped}
