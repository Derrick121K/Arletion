from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Numeric, SmallInteger, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import JSON


JSON_VALUE = JSON().with_variant(JSONB, "postgresql")


class Base(DeclarativeBase):
    pass


class Tenant(Base):
    __tablename__ = "tenants"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    __table_args__ = (CheckConstraint("status IN ('active','suspended','closed')", name="tenant_status_check"),)


class Campaign(Base):
    __tablename__ = "campaigns"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    objective: Mapped[str] = mapped_column(Text, nullable=False)
    lead_type: Mapped[str] = mapped_column(Text, nullable=False)
    geography: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False, default=dict)
    criteria: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False, default=dict)
    scoring_config: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False, default=dict)
    workflow_config: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    __table_args__ = (
        CheckConstraint("lead_type IN ('business','procurement','consumer_enquiry','partnership')", name="campaign_lead_type_check"),
        CheckConstraint("status IN ('draft','active','paused','archived')", name="campaign_status_check"),
    )


class SourceRegistry(Base):
    __tablename__ = "source_registry"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    base_url: Mapped[str] = mapped_column(Text, nullable=False)
    source_type: Mapped[str] = mapped_column(Text, nullable=False)
    licence_reference: Mapped[str | None] = mapped_column(Text)
    permitted_use: Mapped[str] = mapped_column(Text, nullable=False, default="pending_review")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    rate_limit_config: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False, default=dict)
    retention_config: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False, default=dict)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SourceRecord(Base):
    __tablename__ = "source_records"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    source_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("source_registry.id"), nullable=False)
    external_id: Mapped[str | None] = mapped_column(Text)
    record_type: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    source_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    payload_hash: Mapped[str | None] = mapped_column(Text)
    raw_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON_VALUE)
    __table_args__ = (UniqueConstraint("source_id", "external_id", name="source_records_source_external_uq"),)


class Organization(Base):
    __tablename__ = "organizations"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    canonical_name: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_name: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    website_domain: Mapped[str | None] = mapped_column(Text, index=True)
    business_category: Mapped[str | None] = mapped_column(Text)
    country_code: Mapped[str] = mapped_column(String(2), nullable=False, default="ZA")
    province: Mapped[str | None] = mapped_column(Text)
    municipality: Mapped[str | None] = mapped_column(Text)
    locality: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Lead(Base):
    __tablename__ = "leads"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    campaign_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False)
    organization_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("organizations.id"))
    lead_type: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="new")
    score: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    score_breakdown: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False, default=dict)
    qualification_reason: Mapped[str | None] = mapped_column(Text)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    next_follow_up_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    __table_args__ = (
        CheckConstraint("score BETWEEN 0 AND 100", name="lead_score_check"),
        UniqueConstraint("tenant_id", "campaign_id", "organization_id", name="leads_tenant_campaign_organization_uq"),
        Index("leads_tenant_status_score_idx", "tenant_id", "status", "score"),
    )


class Opportunity(Base):
    __tablename__ = "opportunities"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    source_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("source_registry.id"))
    external_id: Mapped[str | None] = mapped_column(Text)
    ocid: Mapped[str | None] = mapped_column(Text)
    buyer_name: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(Text)
    province: Mapped[str | None] = mapped_column(Text)
    publication_date: Mapped[date | None] = mapped_column(Date)
    closing_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="unknown")
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    last_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    __table_args__ = (UniqueConstraint("source_id", "external_id", name="opportunities_source_external_uq"),)


class EvidenceItem(Base):
    __tablename__ = "evidence_items"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"))
    source_record_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("source_records.id", ondelete="CASCADE"))
    field_name: Mapped[str] = mapped_column(Text, nullable=False)
    field_value: Mapped[str | None] = mapped_column(Text)
    evidence_url: Mapped[str] = mapped_column(Text, nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    verification_status: Mapped[str] = mapped_column(Text, nullable=False, default="unknown")
    confidence: Mapped[float | None] = mapped_column(Numeric(4, 3))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ConsentRecord(Base):
    __tablename__ = "consent_records"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    subject_reference: Mapped[str] = mapped_column(Text, nullable=False)
    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    channel: Mapped[str] = mapped_column(Text, nullable=False)
    consent_status: Mapped[str] = mapped_column(Text, nullable=False)
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notice_version: Mapped[str | None] = mapped_column(Text)
    evidence_reference: Mapped[str | None] = mapped_column(Text)
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SuppressionRecord(Base):
    __tablename__ = "suppression_records"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    subject_reference: Mapped[str] = mapped_column(Text, nullable=False)
    channel: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    status: Mapped[str] = mapped_column(Text, nullable=False, default="active")


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("tenants.id"))
    actor_user_id: Mapped[str | None] = mapped_column(Text)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    entity_type: Mapped[str] = mapped_column(Text, nullable=False)
    entity_id: Mapped[str | None] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    request_id: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSON_VALUE, nullable=False, default=dict)
