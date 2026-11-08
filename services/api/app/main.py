from datetime import date, datetime, timezone
import hmac
import os
import re
from datetime import timedelta
from typing import Any, Literal
from urllib.parse import urlsplit
from uuid import UUID
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session
from starlette.responses import JSONResponse
from .database import DEFAULT_TENANT_ID, ETENDERS_SOURCE_ID, db_health, get_session
from .models import Campaign as CampaignRow, ConsentRecord, ConsumerEnquiry as ConsumerEnquiryRow, Lead as LeadRow, Opportunity as OpportunityRow, Organization, SourceRecord, SourceRegistry, SuppressionRecord
from .privacy import consumer_storage_ready, contact_fingerprint, decrypt_contact, encrypt_contact, valid_consumer_access
from .procurement import extract_awarded_business_suppliers, import_opportunities, parse_import
from .business_sources import OSM_ATTRIBUTION, OSM_SOURCE, fetch_osm_businesses

app = FastAPI(title="Arletion API", version="0.2.0", description="PostgreSQL-backed Arletion workspace and official OCDS import.")
cors_origins = [origin.strip().rstrip("/") for origin in os.getenv(
    "ARLETION_CORS_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000",
).split(",") if origin.strip()]
app.add_middleware(CORSMiddleware, allow_origins=cors_origins, allow_credentials=False,
                   allow_methods=["GET", "POST", "PATCH", "OPTIONS"], allow_headers=["Content-Type", "Authorization"])


@app.middleware("http")
async def require_api_key_in_protected_deployments(request, call_next):
    """Require a server-side bearer key for data APIs in configured deployments."""
    required = os.getenv("ARLETION_REQUIRE_API_KEY", "false").strip().lower() == "true"
    if required and request.method != "OPTIONS" and request.url.path.startswith("/api/v1/"):
        expected = os.getenv("ARLETION_API_KEY", "")
        if not expected:
            return JSONResponse(
                {"detail": "API authentication is not configured on this service."},
                status_code=503,
                headers={"Cache-Control": "no-store"},
            )
        authorization = request.headers.get("authorization", "")
        supplied = authorization[7:] if authorization.startswith("Bearer ") else ""
        if not supplied or not hmac.compare_digest(supplied, expected):
            return JSONResponse(
                {"detail": "A valid Arletion API credential is required."},
                status_code=401,
                headers={
                    "WWW-Authenticate": 'Bearer realm="Arletion API"',
                    "Cache-Control": "no-store",
                },
            )
    return await call_next(request)

class Campaign(BaseModel):
    id: str; name: str; objective: str
    lead_type: Literal["business", "procurement", "consumer_enquiry", "partnership"]
    pipeline: Literal["business_procurement", "consumer"]
    geography: str; status: Literal["draft", "active", "paused", "archived"]; lead_count: int = 0
class Lead(BaseModel):
    id: str; organization: str; lead_type: str; category: str | None = None; location: str
    province: str | None = None; website_url: str | None = None
    source: str; source_url: str; status: str
    verification_status: Literal["unverified", "source_confirmed", "officially_verified", "needs_review"] = "unverified"
    verification_source: str | None = None; verified_at: datetime | None = None
    source_updated_at: datetime | None = None
    score: int = Field(ge=0, le=100); evidence_note: str; demo: bool = True

class LeadPage(BaseModel):
    items: list[Lead]
    categories: list[str]
    page: int
    page_size: int
    total: int
class ConsumerEnquiryWrite(BaseModel):
    campaign_id: UUID
    full_name: str = Field(min_length=2, max_length=160)
    phone: str | None = Field(default=None, max_length=32)
    email: str | None = Field(default=None, max_length=254)
    province: str | None = Field(default=None, max_length=100)
    locality: str | None = Field(default=None, max_length=120)
    preferred_channel: Literal["phone", "email", "whatsapp"]
    category: Literal["debt_counselling", "debt_review_information", "budget_guidance", "general"] = "general"
    source: str = Field(default="website_form", min_length=2, max_length=120)
    processing_consent: bool
    marketing_consent: bool = False
    notice_version: str = Field(min_length=1, max_length=40)

    @model_validator(mode="after")
    def validate_contact_and_permissions(self):
        self.full_name = self.full_name.strip()
        if not self.phone and not self.email:
            raise ValueError("Provide a phone number or email address.")
        if self.phone and not re.fullmatch(r"[+0-9() .-]{7,32}", self.phone.strip()):
            raise ValueError("Provide a valid phone number.")
        if self.email and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", self.email.strip()):
            raise ValueError("Provide a valid email address.")
        if self.preferred_channel == "email" and not self.email:
            raise ValueError("An email address is required for the selected contact channel.")
        if self.preferred_channel in {"phone", "whatsapp"} and not self.phone:
            raise ValueError("A phone number is required for the selected contact channel.")
        if not self.processing_consent:
            raise ValueError("Consent to process this enquiry is required.")
        return self

class ConsumerEnquiryItem(BaseModel):
    id: str
    campaign_id: str
    contact_protected: bool = True
    has_phone: bool
    has_email: bool
    category: str
    province: str | None
    locality: str | None
    preferred_channel: str
    source: str
    status: str
    processing_consent_at: datetime
    marketing_consent: bool
    marketing_consent_at: datetime | None
    created_at: datetime
    retention_expires_at: datetime

class ConsumerEnquiryPage(BaseModel):
    items: list[ConsumerEnquiryItem]
    page: int
    page_size: int
    total: int


class Source(BaseModel):
    id: str; name: str; category: str; url: str
    status: Literal["planned", "review_required", "enabled", "disabled"]; note: str

class CampaignWrite(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    objective: str = Field(min_length=1)
    lead_type: Literal["business", "procurement", "consumer_enquiry", "partnership"]
    geography: str = "South Africa"
    status: Literal["draft", "active", "paused", "archived"] = "draft"
    criteria: dict[str, Any] = Field(default_factory=dict)

class CampaignUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=300)
    objective: str | None = None
    lead_type: Literal["business", "procurement", "consumer_enquiry", "partnership"] | None = None
    geography: str | None = None
    status: Literal["draft", "active", "paused", "archived"] | None = None
    criteria: dict[str, Any] | None = None

class LeadWrite(BaseModel):
    """Business and procurement lead writer; consumers use the protected enquiry table."""
    campaign_id: UUID
    organization: str = Field(min_length=1, max_length=500)
    lead_type: Literal["business", "procurement", "partnership"]
    category: str | None = Field(default=None, max_length=120)
    location: str = Field(default="South Africa", max_length=180)
    province: str | None = Field(default=None, max_length=100)
    municipality: str | None = Field(default=None, max_length=120)
    source: str = Field(min_length=1, max_length=300)
    source_url: str = Field(min_length=8, max_length=2000)
    status: Literal["new", "contacted", "qualified", "converted", "disqualified", "suppressed"] = "new"
    score: int = Field(default=0, ge=0, le=100)
    evidence_note: str = Field(default="", max_length=2000)
    external_id: str | None = Field(default=None, max_length=300)

    @model_validator(mode="after")
    def validate_source_url(self):
        parsed = urlsplit(self.source_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("source_url must be an absolute HTTP or HTTPS URL")
        return self

class OpenStreetMapImportWrite(BaseModel):
    campaign_id: UUID
    category: Literal[
        "Construction", "Building materials", "Transport and logistics", "IT and software",
        "Training and education", "Cleaning and facilities", "Security services", "Agriculture",
        "Manufacturing", "Retail and wholesale", "Professional services",
    ]
    locality: str = Field(default="eMalahleni", min_length=2, max_length=120)
    province: str = Field(default="Mpumalanga", min_length=2, max_length=100)
    latitude: float = Field(default=-25.8762, ge=-90, le=90)
    longitude: float = Field(default=29.21, ge=-180, le=180)
    radius_m: int = Field(default=10000, ge=1000, le=15000)
    limit: int = Field(default=100, ge=1, le=200)


class EtenderAwardSupplierImportWrite(BaseModel):
    campaign_id: UUID
    max_releases: int = Field(default=500, ge=1, le=2000)


class SourceWrite(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    url: str = Field(min_length=8, max_length=2000)
    category: str = Field(default="Other", max_length=120)
    status: Literal["planned", "review_required", "enabled", "disabled"] = "review_required"
    note: str = Field(default="", max_length=2000)

    @model_validator(mode="after")
    def validate_source_url(self):
        parsed = urlsplit(self.url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("url must be an absolute HTTP or HTTPS URL")
        return self

class OfficialImportWrite(BaseModel):
    page_number: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=100)
    date_from: date
    date_to: date

    @model_validator(mode="after")
    def date_range_is_ordered(self):
        if self.date_to < self.date_from:
            raise ValueError("date_to must not be earlier than date_from")
        return self

@app.get("/health")
def health():
    database = db_health()
    if database["connected"]:
        return {"status":"ok", "service":"arletion-api", "version":"0.2.0", "mode":"postgresql", "database":database, "timestamp":datetime.now(timezone.utc).isoformat()}
    raise HTTPException(status_code=503, detail={"status":"unavailable", "service":"arletion-api", "database":database})

@app.get("/live")
def live():
    return {"status":"ok", "service":"arletion-api", "timestamp":datetime.now(timezone.utc).isoformat()}
def _consumer_ready() -> None:
    if not consumer_storage_ready():
        raise HTTPException(503, "Consumer intake is disabled until durable storage, encryption, retention and access controls are configured.")
    try:
        encrypt_contact("configuration-check")
        contact_fingerprint("configuration-check", None)
    except RuntimeError as error:
        raise HTTPException(503, str(error)) from error


def _consumer_access(supplied: str | None) -> None:
    if not valid_consumer_access(supplied):
        raise HTTPException(403, "A separate consumer-contact access credential is required.")


def _consumer_item(row: ConsumerEnquiryRow) -> ConsumerEnquiryItem:
    return ConsumerEnquiryItem(
        id=str(row.id), campaign_id=str(row.campaign_id), category=row.category,
        has_phone=bool(row.phone_ciphertext), has_email=bool(row.email_ciphertext),
        province=row.province, locality=row.locality, preferred_channel=row.preferred_channel,
        source=row.source, status=row.status, processing_consent_at=row.processing_consent_at,
        marketing_consent=row.marketing_consent, marketing_consent_at=row.marketing_consent_at,
        created_at=row.created_at, retention_expires_at=row.retention_expires_at,
    )


@app.get("/api/v1/summary")
def summary(session: Session = Depends(get_session)):
    return {
      "campaigns": session.scalar(select(func.count(CampaignRow.id)).where(CampaignRow.tenant_id == DEFAULT_TENANT_ID)) or 0,
      "business_leads": session.scalar(select(func.count(LeadRow.id)).where(LeadRow.tenant_id == DEFAULT_TENANT_ID, LeadRow.lead_type != "consumer_enquiry")) or 0,
      "consumer_enquiries": session.scalar(select(func.count(ConsumerEnquiryRow.id)).where(ConsumerEnquiryRow.tenant_id == DEFAULT_TENANT_ID)) or 0,
      "leads": session.scalar(select(func.count(LeadRow.id)).where(LeadRow.tenant_id == DEFAULT_TENANT_ID)) or 0,
      "sources": session.scalar(select(func.count(SourceRegistry.id)) ) or 0,
      "qualified": session.scalar(select(func.count(LeadRow.id)).where(LeadRow.tenant_id == DEFAULT_TENANT_ID, LeadRow.score >= 70)) or 0,
      "demo_mode":False,"message":"Workspace records are stored in PostgreSQL."
    }
def _campaign_item(row: CampaignRow, session: Session) -> Campaign:
    geography = row.geography if isinstance(row.geography, str) else ", ".join(str(value) for value in row.geography.values() if value)
    count_query = select(func.count(ConsumerEnquiryRow.id)).where(ConsumerEnquiryRow.campaign_id == row.id) if row.lead_type == "consumer_enquiry" else select(func.count(LeadRow.id)).where(LeadRow.campaign_id == row.id)
    return Campaign(
        id=str(row.id), name=row.name, objective=row.objective, lead_type=row.lead_type,
        pipeline="consumer" if row.lead_type == "consumer_enquiry" else "business_procurement",
        geography=geography or "South Africa", status=row.status, lead_count=session.scalar(count_query) or 0,
    )


@app.get("/api/v1/campaigns", response_model=list[Campaign])
def get_campaigns(
    pipeline: Literal["business_procurement", "consumer"] | None = None,
    session: Session = Depends(get_session),
):
    statement = select(CampaignRow).where(CampaignRow.tenant_id == DEFAULT_TENANT_ID)
    if pipeline == "consumer":
        statement = statement.where(CampaignRow.lead_type == "consumer_enquiry")
    elif pipeline == "business_procurement":
        statement = statement.where(CampaignRow.lead_type != "consumer_enquiry")
    return [_campaign_item(row, session) for row in session.scalars(statement.order_by(CampaignRow.created_at.desc())).all()]


@app.post("/api/v1/campaigns", response_model=Campaign, status_code=201)
def create_campaign(payload: CampaignWrite, session: Session = Depends(get_session)):
    row = CampaignRow(
        tenant_id=DEFAULT_TENANT_ID, name=payload.name.strip(), objective=payload.objective.strip(),
        lead_type=payload.lead_type, geography={"label": payload.geography},
        criteria=payload.criteria, status=payload.status,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return _campaign_item(row, session)


@app.patch("/api/v1/campaigns/{campaign_id}", response_model=Campaign)
def update_campaign(campaign_id: UUID, payload: CampaignUpdate, session: Session = Depends(get_session)):
    row = session.scalar(select(CampaignRow).where(CampaignRow.id == campaign_id, CampaignRow.tenant_id == DEFAULT_TENANT_ID))
    if row is None:
        raise HTTPException(status_code=404, detail="Campaign not found.")
    for key, value in payload.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(row, key, {"label": value} if key == "geography" else value)
    session.commit()
    session.refresh(row)
    return _campaign_item(row, session)


@app.get("/api/v1/leads", response_model=list[Lead])
def get_leads(q: str | None = Query(default=None, max_length=120), lead_type: str | None = None, session: Session = Depends(get_session)):
    statement=select(LeadRow).where(LeadRow.tenant_id==DEFAULT_TENANT_ID, LeadRow.lead_type != "consumer_enquiry")
    if lead_type: statement=statement.where(LeadRow.lead_type==lead_type)
    result=[]
    for row in session.scalars(statement.order_by(LeadRow.created_at.desc())).all():
        org=session.get(Organization,row.organization_id) if row.organization_id else None
        evidence=session.scalar(select(SourceRecord).where(SourceRecord.external_id==str(row.id)))
        source=session.get(SourceRegistry,evidence.source_id) if evidence else None
        location=", ".join(x for x in [org.locality if org else None,org.municipality if org else None,org.province if org else None] if x) or "South Africa"
        item=Lead(id=str(row.id),organization=org.canonical_name if org else "Unspecified organization",lead_type=row.lead_type,category=org.business_category if org else None,location=location,province=org.province if org else None,website_url=f"https://{org.website_domain}" if org and org.website_domain else None,source=source.name if source else "Source record",source_url=evidence.source_url if evidence else "https://data.etenders.gov.za/",status=row.status,verification_status=row.verification_status,verification_source=row.verification_source,verified_at=row.verified_at,source_updated_at=evidence.source_updated_at if evidence else None,score=row.score,evidence_note=row.qualification_reason or "Source evidence attached.",demo=False)
        if not q or q.casefold() in item.organization.casefold() or q.casefold() in item.location.casefold(): result.append(item)
    return result


@app.get("/api/v1/leads/search", response_model=LeadPage)
def search_leads(
    q: str | None = Query(default=None, max_length=120),
    lead_type: Literal["business", "procurement", "partnership"] | None = None,
    category: str | None = Query(default=None, max_length=120),
    status: Literal["new", "contacted", "qualified", "converted", "disqualified", "suppressed"] | None = None,
    province: str | None = Query(default=None, max_length=100),
    verification_status: Literal["unverified", "source_confirmed", "officially_verified", "needs_review"] | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    session: Session = Depends(get_session),
):
    """Filter leads in PostgreSQL and return a bounded page plus real category facets."""
    statement = select(LeadRow, Organization).outerjoin(
        Organization, LeadRow.organization_id == Organization.id
    ).where(LeadRow.tenant_id == DEFAULT_TENANT_ID)
    if lead_type:
        statement = statement.where(LeadRow.lead_type == lead_type)
    if category:
        statement = statement.where(func.lower(Organization.business_category) == category.strip().lower())
    if status:
        statement = statement.where(LeadRow.status == status)
    if province:
        statement = statement.where(func.lower(Organization.province) == province.strip().lower())
    if verification_status:
        statement = statement.where(LeadRow.verification_status == verification_status)
    if q:
        term = f"%{q.strip()}%"
        statement = statement.where(
            or_(
                Organization.canonical_name.ilike(term),
                Organization.locality.ilike(term),
                Organization.municipality.ilike(term),
                Organization.province.ilike(term),
            )
        )
    total = session.scalar(select(func.count()).select_from(statement.subquery())) or 0
    rows = session.execute(
        statement.order_by(LeadRow.created_at.desc(), LeadRow.id)
        .offset((page - 1) * page_size).limit(page_size)
    ).all()
    items = []
    for row, org in rows:
        evidence = session.scalar(select(SourceRecord).where(
            SourceRecord.record_type == "lead_evidence",
            SourceRecord.external_id == str(row.id),
        ))
        source = session.get(SourceRegistry, evidence.source_id) if evidence else None
        location = ", ".join(value for value in [
            org.locality if org else None,
            org.municipality if org else None,
            org.province if org else None,
        ] if value) or "South Africa"
        items.append(Lead(
            id=str(row.id),
            organization=org.canonical_name if org else "Unspecified organization",
            lead_type=row.lead_type,
            category=org.business_category if org else None,
            location=location,
            province=org.province if org else None,
            website_url=f"https://{org.website_domain}" if org and org.website_domain else None,
            source=source.name if source else "Source record",
            source_url=evidence.source_url if evidence else "https://data.etenders.gov.za/",
            status=row.status,
            verification_status=row.verification_status,
            verification_source=row.verification_source,
            verified_at=row.verified_at,
            source_updated_at=evidence.source_updated_at if evidence else None,
            score=row.score,
            evidence_note=row.qualification_reason or "Source evidence attached.",
            demo=False,
        ))
    categories = session.scalars(
        select(Organization.business_category).join(
            LeadRow, LeadRow.organization_id == Organization.id
        ).where(
            LeadRow.tenant_id == DEFAULT_TENANT_ID,
            Organization.business_category.is_not(None),
            Organization.business_category != "",
        ).distinct().order_by(Organization.business_category)
    ).all()
    return LeadPage(items=items, categories=list(categories), page=page, page_size=page_size, total=total)


@app.get("/api/v1/leads/categories", response_model=list[str])
def lead_categories(session: Session = Depends(get_session)):
    return session.scalars(
        select(Organization.business_category).join(
            LeadRow, LeadRow.organization_id == Organization.id
        ).where(
            LeadRow.tenant_id == DEFAULT_TENANT_ID,
            Organization.business_category.is_not(None),
            Organization.business_category != "",
        ).distinct().order_by(Organization.business_category)
    ).all()


@app.post("/api/v1/leads/import/openstreetmap")
def import_openstreetmap_businesses(payload: OpenStreetMapImportWrite, session: Session = Depends(get_session)):
    source = session.scalar(select(SourceRegistry).where(SourceRegistry.name == OSM_SOURCE))
    if source is None or not source.enabled or source.permitted_use != "approved":
        raise HTTPException(status_code=409, detail="The OpenStreetMap source is not approved in the source registry.")
    now = datetime.now(timezone.utc)
    if source.last_synced_at and (now - source.last_synced_at).total_seconds() < 60:
        raise HTTPException(status_code=429, detail="OpenStreetMap search is rate-limited to one import per minute. Retry shortly.")
    campaign = session.scalar(select(CampaignRow).where(
        CampaignRow.id == payload.campaign_id,
        CampaignRow.tenant_id == DEFAULT_TENANT_ID,
    ))
    if campaign is None:
        raise HTTPException(status_code=404, detail="Business campaign not found.")
    if campaign.lead_type not in {"business", "partnership"}:
        raise HTTPException(status_code=409, detail="OpenStreetMap listings can only be imported into a business or partnership campaign.")
    try:
        businesses = fetch_osm_businesses(
            payload.category, payload.latitude, payload.longitude, payload.radius_m,
            payload.locality, payload.province, payload.limit,
        )
    except RuntimeError as error:
        source.last_error = str(error)
        session.commit()
        raise HTTPException(status_code=503, detail=str(error)) from error

    inserted = updated = skipped = 0
    for item in businesses:
        external_id = item["external_id"]
        source_record = session.scalar(select(SourceRecord).where(
            SourceRecord.source_id == source.id,
            SourceRecord.external_id == external_id,
        ))
        organization = None
        if source_record and source_record.raw_payload:
            try:
                organization = session.get(Organization, UUID(source_record.raw_payload.get("organization_id", "")))
            except (ValueError, TypeError):
                organization = None
        normalized = f"{' '.join(item['name'].casefold().split())}::osm::{external_id}"
        if organization is None:
            organization = session.scalar(select(Organization).where(
                Organization.normalized_name == normalized,
                Organization.country_code == "ZA",
            ))
        if organization is None:
            organization = Organization(
                canonical_name=item["name"], normalized_name=normalized, country_code="ZA",
                business_category=payload.category, province=item["province"],
                municipality=payload.locality, locality=item["locality"],
                website_domain=item["website_domain"],
            )
            session.add(organization)
            session.flush()
        else:
            organization.business_category = payload.category
            organization.province = item["province"] or organization.province
            organization.municipality = payload.locality or organization.municipality
            organization.locality = item["locality"] or organization.locality
            organization.website_domain = item["website_domain"] or organization.website_domain

        lead = session.scalar(select(LeadRow).where(
            LeadRow.tenant_id == DEFAULT_TENANT_ID,
            LeadRow.campaign_id == campaign.id,
            LeadRow.organization_id == organization.id,
        ))
        evidence_note = "Named business feature present in OpenStreetMap; CIPC registration and current trading status are not implied."
        if lead is None:
            lead = LeadRow(
                tenant_id=DEFAULT_TENANT_ID, campaign_id=campaign.id,
                organization_id=organization.id, lead_type=campaign.lead_type,
                status="new", score=30, qualification_reason=evidence_note,
                verification_status="source_confirmed",
                verification_source="OpenStreetMap",
                verified_at=now,
            )
            session.add(lead)
            session.flush()
            inserted += 1
        else:
            lead.last_seen_at = now
            lead.verification_status = "source_confirmed"
            lead.verification_source = "OpenStreetMap"
            lead.verified_at = now
            lead.qualification_reason = evidence_note
            updated += 1

        evidence = session.scalar(select(SourceRecord).where(
            SourceRecord.source_id == source.id,
            SourceRecord.external_id == str(lead.id),
        ))
        evidence_payload = {
            "lead_id": str(lead.id), "osm_external_id": external_id,
            "organization_id": str(organization.id), "category": payload.category,
            "tags": item["tags"], "website_domain": item["website_domain"],
            "attribution": OSM_ATTRIBUTION,
        }
        if evidence is None:
            session.add(SourceRecord(
                source_id=source.id, external_id=str(lead.id), record_type="lead_evidence",
                source_url=item["source_url"], source_updated_at=item["source_updated_at"],
                raw_payload=evidence_payload,
            ))
        else:
            evidence.source_url = item["source_url"]
            evidence.source_updated_at = item["source_updated_at"]
            evidence.raw_payload = evidence_payload

        if source_record is None:
            session.add(SourceRecord(
                source_id=source.id, external_id=external_id, record_type="osm_business",
                source_url=item["source_url"], source_updated_at=item["source_updated_at"],
                raw_payload={"organization_id": str(organization.id), "tags": item["tags"]},
            ))
        else:
            source_record.source_url = item["source_url"]
            source_record.source_updated_at = item["source_updated_at"]
            source_record.raw_payload = {"organization_id": str(organization.id), "tags": item["tags"]}

    source.last_synced_at = now
    source.last_error = None
    session.commit()
    return {
        "source": OSM_SOURCE, "attribution": OSM_ATTRIBUTION,
        "licence": "Open Database License (ODbL) 1.0",
        "location": payload.locality, "province": payload.province,
        "category": payload.category, "radius_m": payload.radius_m,
        "matched": len(businesses), "inserted": inserted, "updated": updated, "skipped": skipped,
        "verification_status": "source_confirmed",
        "verification_scope": "Present as a named business feature in OpenStreetMap at import time; not CIPC registration or proof of current trading.",
    }


@app.get("/api/v1/consumer-enquiries/status")
def consumer_intake_status():
    return {
        "enabled": consumer_storage_ready(),
        "storage_approved": os.getenv("ARLETION_CONSUMER_STORAGE_APPROVED", "false").lower() == "true",
        "staff_access_approved": os.getenv("ARLETION_CONSUMER_RBAC_APPROVED", "false").lower() == "true",
        "encryption_configured": bool(os.getenv("ARLETION_PII_ENCRYPTION_KEY")),
        "deduplication_key_configured": len(os.getenv("ARLETION_CONTACT_HASH_KEY", "")) >= 32,
        "separate_contact_access_configured": bool(os.getenv("ARLETION_CONSUMER_ACCESS_KEY")),
        "public_form": False,
        "note": "Contact capture remains disabled until all storage and security controls are explicitly enabled.",
    }


@app.get("/api/v1/consumer-enquiries", response_model=ConsumerEnquiryPage)
def get_consumer_enquiries(
    status: Literal["new", "contacted", "qualified", "converted", "disqualified", "suppressed"] | None = None,
    category: Literal["debt_counselling", "debt_review_information", "budget_guidance", "general"] | None = None,
    province: str | None = Query(default=None, max_length=100),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    session: Session = Depends(get_session),
):
    _consumer_ready()
    statement = select(ConsumerEnquiryRow).where(ConsumerEnquiryRow.tenant_id == DEFAULT_TENANT_ID)
    if status:
        statement = statement.where(ConsumerEnquiryRow.status == status)
    if category:
        statement = statement.where(ConsumerEnquiryRow.category == category)
    if province:
        statement = statement.where(func.lower(ConsumerEnquiryRow.province) == province.strip().lower())
    total = session.scalar(select(func.count()).select_from(statement.subquery())) or 0
    rows = session.scalars(statement.order_by(ConsumerEnquiryRow.created_at.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    return ConsumerEnquiryPage(items=[_consumer_item(row) for row in rows], page=page, page_size=page_size, total=total)


@app.post("/api/v1/consumer-enquiries", response_model=ConsumerEnquiryItem, status_code=201)
def create_consumer_enquiry(payload: ConsumerEnquiryWrite, session: Session = Depends(get_session)):
    _consumer_ready()
    campaign = session.scalar(select(CampaignRow).where(
        CampaignRow.id == payload.campaign_id,
        CampaignRow.tenant_id == DEFAULT_TENANT_ID,
        CampaignRow.lead_type == "consumer_enquiry",
        CampaignRow.status == "active",
    ))
    if campaign is None:
        raise HTTPException(status_code=404, detail="An active consumer-enquiry campaign is required.")
    fingerprint = contact_fingerprint(payload.phone, payload.email)
    duplicate = session.scalar(select(ConsumerEnquiryRow.id).where(
        ConsumerEnquiryRow.tenant_id == DEFAULT_TENANT_ID,
        ConsumerEnquiryRow.campaign_id == campaign.id,
        ConsumerEnquiryRow.contact_fingerprint == fingerprint,
    ))
    if duplicate:
        raise HTTPException(status_code=409, detail="An enquiry from this contact already exists in this campaign.")
    try:
        retention_days = int(os.getenv("ARLETION_CONSUMER_RETENTION_DAYS", "90"))
    except ValueError:
        raise HTTPException(status_code=503, detail="Consumer retention configuration is invalid.") from None
    if not 30 <= retention_days <= 365:
        raise HTTPException(status_code=503, detail="ARLETION_CONSUMER_RETENTION_DAYS must be between 30 and 365.")
    now = datetime.now(timezone.utc)
    try:
        row = ConsumerEnquiryRow(
            tenant_id=DEFAULT_TENANT_ID, campaign_id=campaign.id, contact_fingerprint=fingerprint,
            name_ciphertext=encrypt_contact(payload.full_name.strip()),
            phone_ciphertext=encrypt_contact(payload.phone.strip()) if payload.phone else None,
            email_ciphertext=encrypt_contact(payload.email.strip().lower()) if payload.email else None,
            province=payload.province.strip() if payload.province else None,
            locality=payload.locality.strip() if payload.locality else None,
            category=payload.category, preferred_channel=payload.preferred_channel, source=payload.source.strip(),
            processing_consent_at=now, marketing_consent=payload.marketing_consent,
            marketing_consent_at=now if payload.marketing_consent else None,
            notice_version=payload.notice_version.strip(),
            retention_expires_at=now + timedelta(days=retention_days),
        )
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    session.add(row)
    session.flush()
    session.add(ConsentRecord(
        tenant_id=DEFAULT_TENANT_ID, subject_reference=fingerprint,
        purpose="respond_to_consumer_enquiry", channel=payload.preferred_channel,
        consent_status="granted", captured_at=now, notice_version=payload.notice_version,
        evidence_reference=f"consumer-enquiry:{row.id}:processing",
    ))
    if payload.marketing_consent:
        session.add(ConsentRecord(
            tenant_id=DEFAULT_TENANT_ID, subject_reference=fingerprint,
            purpose="electronic_direct_marketing", channel=payload.preferred_channel,
            consent_status="granted", captured_at=now, notice_version=payload.notice_version,
            evidence_reference=f"consumer-enquiry:{row.id}:marketing-opt-in",
        ))
    session.commit()
    session.refresh(row)
    return _consumer_item(row)


@app.get("/api/v1/consumer-enquiries/{enquiry_id}/contact")
def get_consumer_contact(
    enquiry_id: UUID,
    x_arletion_consumer_access: str | None = Header(default=None),
    session: Session = Depends(get_session),
):
    _consumer_ready()
    _consumer_access(x_arletion_consumer_access)
    row = session.scalar(select(ConsumerEnquiryRow).where(
        ConsumerEnquiryRow.id == enquiry_id, ConsumerEnquiryRow.tenant_id == DEFAULT_TENANT_ID
    ))
    if row is None:
        raise HTTPException(status_code=404, detail="Consumer enquiry not found.")
    try:
        return {
            "full_name": decrypt_contact(row.name_ciphertext),
            "phone": decrypt_contact(row.phone_ciphertext) if row.phone_ciphertext else None,
            "email": decrypt_contact(row.email_ciphertext) if row.email_ciphertext else None,
        }
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@app.post("/api/v1/consumer-enquiries/{enquiry_id}/withdraw-marketing")
def withdraw_consumer_marketing(
    enquiry_id: UUID,
    x_arletion_consumer_access: str | None = Header(default=None),
    session: Session = Depends(get_session),
):
    _consumer_ready()
    _consumer_access(x_arletion_consumer_access)
    row = session.scalar(select(ConsumerEnquiryRow).where(
        ConsumerEnquiryRow.id == enquiry_id, ConsumerEnquiryRow.tenant_id == DEFAULT_TENANT_ID
    ))
    if row is None:
        raise HTTPException(status_code=404, detail="Consumer enquiry not found.")
    row.marketing_consent = False
    row.marketing_consent_at = None
    records = session.scalars(select(ConsentRecord).where(
        ConsentRecord.tenant_id == DEFAULT_TENANT_ID,
        ConsentRecord.subject_reference == row.contact_fingerprint,
        ConsentRecord.purpose == "electronic_direct_marketing",
        ConsentRecord.consent_status == "granted",
    )).all()
    now = datetime.now(timezone.utc)
    for record in records:
        record.consent_status = "withdrawn"
        record.withdrawn_at = now
    suppression = session.scalar(select(SuppressionRecord).where(
        SuppressionRecord.tenant_id == DEFAULT_TENANT_ID,
        SuppressionRecord.subject_reference == row.contact_fingerprint,
        SuppressionRecord.channel == row.preferred_channel,
        SuppressionRecord.status == "active",
    ))
    if suppression is None:
        session.add(SuppressionRecord(
            tenant_id=DEFAULT_TENANT_ID, subject_reference=row.contact_fingerprint,
            channel=row.preferred_channel, reason="Consumer withdrew electronic marketing consent",
            status="active",
        ))
    session.commit()
    return {"id": str(row.id), "marketing_consent": False, "suppressed": True}


@app.post("/api/v1/leads", response_model=Lead, status_code=201)
def create_lead(payload: LeadWrite, session: Session = Depends(get_session)):
    campaign=session.scalar(select(CampaignRow).where(CampaignRow.id==payload.campaign_id,CampaignRow.tenant_id==DEFAULT_TENANT_ID))
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found in this workspace.")
    if campaign.lead_type == "consumer_enquiry" or campaign.lead_type != payload.lead_type:
        raise HTTPException(status_code=409, detail="Business leads must use a matching business/procurement campaign.")
    normalized=" ".join(payload.organization.casefold().split())
    org=session.scalar(select(Organization).where(Organization.normalized_name==normalized,Organization.country_code=="ZA"))
    if org is None:
        org=Organization(canonical_name=payload.organization.strip(),normalized_name=normalized,locality=payload.location,province=payload.province,municipality=payload.municipality,business_category=payload.category)
        session.add(org); session.flush()
    else:
        if payload.category:
            org.business_category=payload.category.strip()
        if payload.location and payload.location != "South Africa":
            org.locality=payload.location.strip()
        if payload.province:
            org.province=payload.province.strip()
        if payload.municipality:
            org.municipality=payload.municipality.strip()
    row=session.scalar(select(LeadRow).where(LeadRow.tenant_id==DEFAULT_TENANT_ID,LeadRow.campaign_id==campaign.id,LeadRow.organization_id==org.id))
    if row is None:
        row=LeadRow(tenant_id=DEFAULT_TENANT_ID,campaign_id=campaign.id,organization_id=org.id,lead_type=payload.lead_type,status=payload.status,score=payload.score,qualification_reason=payload.evidence_note)
        session.add(row); session.flush()
    else:
        row.last_seen_at=datetime.now(timezone.utc); row.status=payload.status; row.score=payload.score; row.qualification_reason=payload.evidence_note
    source=session.scalar(select(SourceRegistry).where(SourceRegistry.name==payload.source))
    if source is None:
        source=SourceRegistry(name=payload.source,base_url=payload.source_url,source_type="lead_evidence",permitted_use="review_required",enabled=False)
        session.add(source); session.flush()
    external_id=str(row.id)
    evidence=session.scalar(select(SourceRecord).where(SourceRecord.source_id==source.id,SourceRecord.external_id==external_id))
    if evidence is None:
        session.add(SourceRecord(source_id=source.id,external_id=external_id,record_type="lead_evidence",source_url=payload.source_url,raw_payload={"lead_id":str(row.id),"source_external_id":payload.external_id,"evidence_note":payload.evidence_note}))
    else:
        evidence.source_url=payload.source_url; evidence.raw_payload={"lead_id":str(row.id),"source_external_id":payload.external_id,"evidence_note":payload.evidence_note}
    session.commit(); session.refresh(row)
    return get_leads(q=payload.organization,lead_type=None,session=session)[0]
@app.post("/api/v1/leads/import/etender-awarded-suppliers")
def import_etender_awarded_suppliers(payload: EtenderAwardSupplierImportWrite, session: Session = Depends(get_session)):
    source = session.get(SourceRegistry, ETENDERS_SOURCE_ID) or session.scalar(
        select(SourceRegistry).where(SourceRegistry.name == "National Treasury eTender Transparency Portal")
    )
    if source is None or not source.enabled or source.permitted_use != "approved":
        raise HTTPException(status_code=409, detail="Approve the official National Treasury eTender source before importing awarded suppliers.")
    campaign = session.scalar(select(CampaignRow).where(
        CampaignRow.id == payload.campaign_id,
        CampaignRow.tenant_id == DEFAULT_TENANT_ID,
    ))
    if campaign is None:
        raise HTTPException(status_code=404, detail="Business or procurement campaign not found.")
    if campaign.lead_type not in {"business", "procurement", "partnership"}:
        raise HTTPException(status_code=409, detail="Awarded suppliers must use a business, procurement or partnership campaign.")
    releases = session.scalars(
        select(SourceRecord).where(
            SourceRecord.source_id == source.id,
            SourceRecord.record_type == "ocds_release",
        ).order_by(SourceRecord.source_updated_at.desc().nullslast(), SourceRecord.observed_at.desc())
        .limit(payload.max_releases)
    ).all()
    suppliers = {}
    skipped = 0
    for release in releases:
        raw = release.raw_payload if isinstance(release.raw_payload, dict) else {}
        items = extract_awarded_business_suppliers(raw, release.source_url, release.source_updated_at)
        if not items:
            skipped += 1
        for item in items:
            # Prefer the most recently published award evidence for a supplier.
            prior = suppliers.get(item["supplier_key"].casefold())
            if prior is None or (item["source_updated_at"] and (
                prior["source_updated_at"] is None or item["source_updated_at"] > prior["source_updated_at"]
            )):
                suppliers[item["supplier_key"].casefold()] = item

    now = datetime.now(timezone.utc)
    inserted = updated = 0
    for item in suppliers.values():
        normalized = f"{' '.join(item['name'].casefold().split())}::etender::{item['supplier_key'].casefold()}"
        organization = session.scalar(select(Organization).where(
            Organization.normalized_name == normalized,
            Organization.country_code == "ZA",
        ))
        if organization is None:
            organization = Organization(
                canonical_name=item["name"], normalized_name=normalized, country_code="ZA",
                business_category=item["category"],
            )
            session.add(organization)
            session.flush()
        elif item["category"] and item["category"] != "Government supplier":
            organization.business_category = item["category"]

        lead = session.scalar(select(LeadRow).where(
            LeadRow.tenant_id == DEFAULT_TENANT_ID,
            LeadRow.campaign_id == campaign.id,
            LeadRow.organization_id == organization.id,
        ))
        reason = (
            f"Named as an award supplier in National Treasury OCDS release {item['ocid']} "
            f"(award {item['award_id'] or 'ID not supplied'}). Confirm current CSD status before outreach."
        )
        if lead is None:
            lead = LeadRow(
                tenant_id=DEFAULT_TENANT_ID, campaign_id=campaign.id,
                organization_id=organization.id, lead_type=campaign.lead_type,
                status="new", score=55, qualification_reason=reason,
                verification_status="source_confirmed",
                verification_source="National Treasury eTender OCDS award",
                verified_at=now,
            )
            session.add(lead)
            session.flush()
            inserted += 1
        else:
            lead.last_seen_at = now
            lead.verification_status = "source_confirmed"
            lead.verification_source = "National Treasury eTender OCDS award"
            lead.verified_at = now
            lead.qualification_reason = reason
            updated += 1

        evidence = session.scalar(select(SourceRecord).where(
            SourceRecord.source_id == source.id,
            SourceRecord.external_id == str(lead.id),
            SourceRecord.record_type == "lead_evidence",
        ))
        evidence_payload = {
            "lead_id": str(lead.id),
            "supplier_identifier": item["supplier_key"],
            "ocid": item["ocid"],
            "award_id": item["award_id"],
            "tender_title": item["tender_title"],
            "source_evidence": item["source_evidence"],
        }
        if evidence is None:
            session.add(SourceRecord(
                source_id=source.id, external_id=str(lead.id), record_type="lead_evidence",
                source_url=item["source_url"], source_updated_at=item["source_updated_at"],
                raw_payload=evidence_payload,
            ))
        else:
            evidence.source_url = item["source_url"]
            evidence.source_updated_at = item["source_updated_at"]
            evidence.raw_payload = evidence_payload

    session.commit()
    return {
        "source": "National Treasury eTender Transparency Portal",
        "matched_releases": len(releases),
        "unique_awarded_companies": len(suppliers),
        "inserted": inserted,
        "updated": updated,
        "skipped_releases_without_company_awards": skipped,
        "verification_status": "source_confirmed",
        "verification_scope": "Named as a company-form supplier in a published OCDS award; current CSD registration, tax status and trading activity are not implied.",
    }


@app.get("/api/v1/sources", response_model=list[Source])
def get_sources(session: Session = Depends(get_session)):
    result=[]
    for row in session.scalars(select(SourceRegistry).order_by(SourceRegistry.name)).all():
        status=("enabled" if row.enabled and row.permitted_use=="approved" else "disabled" if row.permitted_use=="approved" else row.permitted_use if row.permitted_use in {"planned","review_required","enabled","disabled"} else "planned")
        result.append(Source(id=str(row.id),name=row.name,category=row.source_type,url=row.base_url,status=status,note=row.last_error or ("Approved for reviewed imports." if row.enabled else "Review terms and coverage before enabling imports.")))
    return result

@app.post("/api/v1/sources", response_model=Source, status_code=201)
def create_source(payload: SourceWrite, session: Session = Depends(get_session)):
    row=session.scalar(select(SourceRegistry).where(SourceRegistry.name==payload.name))
    if row is None:
        row=SourceRegistry(name=payload.name,base_url=payload.url,source_type=payload.category,
                           permitted_use="approved" if payload.status=="enabled" else payload.status,enabled=payload.status=="enabled",last_error=payload.note or None)
        session.add(row)
    else:
        row.base_url=payload.url; row.source_type=payload.category; row.permitted_use="approved" if payload.status=="enabled" else payload.status
        row.enabled=payload.status=="enabled"; row.last_error=payload.note or None
    session.commit(); session.refresh(row)
    status=("enabled" if row.enabled and row.permitted_use=="approved" else "disabled" if row.permitted_use=="approved" else row.permitted_use if row.permitted_use in {"planned","review_required","enabled","disabled"} else "planned")
    return Source(id=str(row.id),name=row.name,category=row.source_type,url=row.base_url,status=status,note=row.last_error or "Review terms and coverage before enabling imports.")
@app.get("/api/v1/opportunities")
def get_opportunities(session: Session = Depends(get_session)):
    rows=session.scalars(select(OpportunityRow).order_by(OpportunityRow.closing_date.asc().nullslast(),OpportunityRow.title)).all()
    items=[{"id":str(row.id),"external_id":row.external_id,"ocid":row.ocid,"buyer_name":row.buyer_name,"title":row.title,"description":row.description,"category":row.category,"province":row.province,"publication_date":row.publication_date.isoformat() if row.publication_date else None,"closing_date":row.closing_date.isoformat() if row.closing_date else None,"status":row.status,"source_url":row.source_url,"provenance":"National Treasury eTender Transparency Portal"} for row in rows]
    return {"items":items,"demo_mode":False,"message":"Imported public procurement records. Verify current tender documents and buyer updates before acting." if items else "No procurement records imported yet."}

@app.post("/api/v1/opportunities", status_code=201)
def create_opportunity(payload: dict[str, Any], session: Session = Depends(get_session)):
    try:
        result=import_opportunities(session,[payload])
    except (ValueError,RuntimeError) as error:
        raise HTTPException(status_code=422,detail=str(error)) from error
    if result["skipped"]:
        raise HTTPException(status_code=422,detail="Opportunity needs a stable source id (prefer OCID) and a title.")
    items=get_opportunities(session)["items"]
    external_id=str(payload.get("ocid") or payload.get("external_id") or payload.get("id") or "")
    return next((item for item in items if item["external_id"]==external_id),result)

@app.post("/api/v1/opportunities/import")
def import_opportunity_file(payload: dict[str, Any], session: Session = Depends(get_session)):
    try:
        records=parse_import(str(payload.get("content", "")),str(payload.get("format", "")))
        return {**import_opportunities(session,records),"source":"National Treasury eTender Transparency Portal"}
    except (ValueError,RuntimeError) as error:
        raise HTTPException(status_code=422,detail=str(error)) from error

@app.post("/api/v1/opportunities/import/official")
def import_official_opportunities(payload: OfficialImportWrite, session: Session = Depends(get_session)):
    source = session.scalar(select(SourceRegistry).where(
        SourceRegistry.name == "National Treasury eTender Transparency Portal"
    ))
    if source is None or not source.enabled or source.permitted_use != "approved":
        raise HTTPException(
            status_code=409,
            detail="The official eTender connector is not approved. Review its documented access and reuse terms in Source Registry, then explicitly approve and enable it before importing.",
        )
    import json, urllib.error, urllib.parse, urllib.request
    params={"PageNumber":payload.page_number,"PageSize":payload.page_size}
    params["dateFrom"]=payload.date_from.isoformat()
    params["dateTo"]=payload.date_to.isoformat()
    url="https://ocds-api.etenders.gov.za/api/OCDSReleases?"+urllib.parse.urlencode(params)
    request=urllib.request.Request(url,headers={"Accept":"application/json","User-Agent":"Arletion/0.1 (public OCDS import)"})
    try:
        with urllib.request.urlopen(request,timeout=20) as response: raw=response.read(20_000_001)
        if len(raw)>20_000_000: raise HTTPException(status_code=502,detail="Official API response exceeded the 20 MB limit; reduce page_size.")
        records=parse_import(raw.decode("utf-8-sig"),"json")
        return {**import_opportunities(session,records),"source":"National Treasury eTender Transparency Portal","page":payload.page_number}
    except urllib.error.HTTPError as error:
        raise HTTPException(status_code=502,detail=f"Official eTender API returned HTTP {error.code}.") from error
    except (urllib.error.URLError,TimeoutError) as error:
        raise HTTPException(status_code=502,detail=f"Official eTender API is unreachable: {error.__class__.__name__}.") from error
    except (UnicodeDecodeError,ValueError) as error:
        raise HTTPException(status_code=502,detail=f"Official eTender API response did not match the published OCDS JSON contract: {error}.") from error
