from datetime import date, datetime, timezone
import hmac
import os
from typing import Any, Literal
from uuid import UUID
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from starlette.responses import JSONResponse
from .database import DEFAULT_TENANT_ID, db_health, get_session
from .models import Campaign as CampaignRow, Lead as LeadRow, Opportunity as OpportunityRow, Organization, SourceRecord, SourceRegistry
from .procurement import import_opportunities, parse_import

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
    if required and request.url.path.startswith("/api/v1/"):
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
    geography: str; status: Literal["draft", "active", "paused", "archived"]; lead_count: int = 0
class Lead(BaseModel):
    id: str; organization: str; lead_type: str; location: str; source: str; source_url: str
    status: str; score: int = Field(ge=0, le=100); evidence_note: str; demo: bool = True
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
    campaign_id: UUID
    organization: str = Field(min_length=1, max_length=500)
    lead_type: Literal["business", "procurement", "consumer_enquiry", "partnership"]
    location: str = "South Africa"
    source: str = Field(min_length=1, max_length=300)
    source_url: str = Field(min_length=1, max_length=2000)
    status: str = "new"
    score: int = Field(default=0, ge=0, le=100)
    evidence_note: str = ""
    external_id: str | None = None

class SourceWrite(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    url: str = Field(min_length=1, max_length=2000)
    category: str = "Other"
    status: Literal["planned", "review_required", "enabled", "disabled"] = "review_required"
    note: str = ""

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
@app.get("/api/v1/summary")
def summary(session: Session = Depends(get_session)):
    return {
      "campaigns": session.scalar(select(func.count(CampaignRow.id)).where(CampaignRow.tenant_id == DEFAULT_TENANT_ID)) or 0,
      "leads": session.scalar(select(func.count(LeadRow.id)).where(LeadRow.tenant_id == DEFAULT_TENANT_ID)) or 0,
      "sources": session.scalar(select(func.count(SourceRegistry.id)) ) or 0,
      "qualified": session.scalar(select(func.count(LeadRow.id)).where(LeadRow.tenant_id == DEFAULT_TENANT_ID, LeadRow.score >= 70)) or 0,
      "demo_mode":False,"message":"Workspace records are stored in PostgreSQL."
    }
@app.get("/api/v1/campaigns", response_model=list[Campaign])
def get_campaigns(session: Session = Depends(get_session)):
    rows=session.scalars(select(CampaignRow).where(CampaignRow.tenant_id==DEFAULT_TENANT_ID).order_by(CampaignRow.created_at.desc())).all()
    result=[]
    for row in rows:
        geography=row.geography if isinstance(row.geography,str) else ", ".join(str(value) for value in row.geography.values() if value)
        result.append(Campaign(id=str(row.id),name=row.name,objective=row.objective,lead_type=row.lead_type,geography=geography or "South Africa",status=row.status,lead_count=session.scalar(select(func.count(LeadRow.id)).where(LeadRow.campaign_id==row.id)) or 0))
    return result

@app.post("/api/v1/campaigns", response_model=Campaign, status_code=201)
def create_campaign(payload: CampaignWrite, session: Session = Depends(get_session)):
    row=CampaignRow(tenant_id=DEFAULT_TENANT_ID,name=payload.name,objective=payload.objective,lead_type=payload.lead_type,
                    geography={"label":payload.geography},criteria=payload.criteria,status=payload.status)
    session.add(row); session.commit(); session.refresh(row)
    return Campaign(id=str(row.id),name=row.name,objective=row.objective,lead_type=row.lead_type,geography=payload.geography,status=row.status,lead_count=0)

@app.patch("/api/v1/campaigns/{campaign_id}", response_model=Campaign)
def update_campaign(campaign_id: UUID, payload: CampaignUpdate, session: Session = Depends(get_session)):
    row=session.scalar(select(CampaignRow).where(CampaignRow.id==campaign_id,CampaignRow.tenant_id==DEFAULT_TENANT_ID))
    if row is None: raise HTTPException(status_code=404,detail="Campaign not found.")
    for key,value in payload.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(row,key,{"label":value} if key=="geography" else value)
    session.commit(); session.refresh(row)
    geography=row.geography if isinstance(row.geography,str) else ", ".join(str(value) for value in row.geography.values() if value)
    return Campaign(id=str(row.id),name=row.name,objective=row.objective,lead_type=row.lead_type,geography=geography or "South Africa",status=row.status,lead_count=session.scalar(select(func.count(LeadRow.id)).where(LeadRow.campaign_id==row.id)) or 0)
@app.get("/api/v1/leads", response_model=list[Lead])
def get_leads(q: str | None = Query(default=None), lead_type: str | None = None, session: Session = Depends(get_session)):
    statement=select(LeadRow).where(LeadRow.tenant_id==DEFAULT_TENANT_ID)
    if lead_type: statement=statement.where(LeadRow.lead_type==lead_type)
    result=[]
    for row in session.scalars(statement.order_by(LeadRow.created_at.desc())).all():
        org=session.get(Organization,row.organization_id) if row.organization_id else None
        evidence=session.scalar(select(SourceRecord).where(SourceRecord.external_id==str(row.id)))
        source=session.get(SourceRegistry,evidence.source_id) if evidence else None
        location=", ".join(x for x in [org.locality if org else None,org.municipality if org else None,org.province if org else None] if x) or "South Africa"
        item=Lead(id=str(row.id),organization=org.canonical_name if org else "Unspecified organization",lead_type=row.lead_type,location=location,source=source.name if source else "Source record",source_url=evidence.source_url if evidence else "https://data.etenders.gov.za/",status=row.status,score=row.score,evidence_note=row.qualification_reason or "Source evidence attached.",demo=False)
        if not q or q.casefold() in item.organization.casefold() or q.casefold() in item.location.casefold(): result.append(item)
    return result

@app.post("/api/v1/leads", response_model=Lead, status_code=201)
def create_lead(payload: LeadWrite, session: Session = Depends(get_session)):
    campaign=session.scalar(select(CampaignRow).where(CampaignRow.id==payload.campaign_id,CampaignRow.tenant_id==DEFAULT_TENANT_ID))
    if campaign is None: raise HTTPException(status_code=404,detail="Campaign not found in this workspace.")
    normalized=" ".join(payload.organization.casefold().split())
    org=session.scalar(select(Organization).where(Organization.normalized_name==normalized,Organization.country_code=="ZA"))
    if org is None:
        org=Organization(canonical_name=payload.organization.strip(),normalized_name=normalized,locality=payload.location)
        session.add(org); session.flush()
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
@app.get("/api/v1/sources", response_model=list[Source])
def get_sources(session: Session = Depends(get_session)):
    result=[]
    for row in session.scalars(select(SourceRegistry).order_by(SourceRegistry.name)).all():
        status={"approved":"enabled"}.get(row.permitted_use,row.permitted_use if row.permitted_use in {"planned","review_required","enabled","disabled"} else "planned")
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
    status={"approved":"enabled"}.get(row.permitted_use,row.permitted_use if row.permitted_use in {"planned","review_required","enabled","disabled"} else "planned")
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
