import os
import unittest
from unittest.mock import patch

from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient
from sqlalchemy import text
from cryptography.fernet import Fernet

from app.database import engine_for_url, normalize_database_url
from app.main import app
from app.models import Base
from app.procurement import normalize_record, parse_import
from app.business_sources import OSM_ATTRIBUTION, normalize_osm_businesses, overpass_query


def api_request(method: str, path: str, **kwargs):
    with TestClient(app) as client:
        return client.request(method, path, **kwargs)


class ApiUnitTests(unittest.TestCase):
    def test_hosted_postgres_urls_select_psycopg3(self):
        self.assertEqual(
            normalize_database_url("postgres://user:pass@db.example:5432/app"),
            "postgresql+psycopg://user:pass@db.example:5432/app",
        )
        self.assertEqual(
            normalize_database_url("postgresql://user:pass@db.example:5432/app"),
            "postgresql+psycopg://user:pass@db.example:5432/app",
        )
        self.assertEqual(
            normalize_database_url("postgresql+psycopg://user:pass@db.example:5432/app"),
            "postgresql+psycopg://user:pass@db.example:5432/app",
        )

    def test_api_key_protects_data_routes_when_enabled(self):
        with patch.dict(os.environ, {
            "ARLETION_REQUIRE_API_KEY": "true",
            "ARLETION_API_KEY": "test-secret-key",
            "DATABASE_URL": "",
            "ARLETION_TEST_DATABASE_URL": "",
        }):
            denied = api_request("GET", "/api/v1/campaigns")
            self.assertEqual(denied.status_code, 401)
            self.assertEqual(api_request("GET", "/api/v1/leads/search").status_code, 401)
            self.assertEqual(api_request("GET", "/api/v1/leads/categories").status_code, 401)
            self.assertEqual(api_request("GET", "/api/v1/consumer-enquiries").status_code, 401)
            allowed = api_request("GET", "/api/v1/campaigns", headers={"Authorization": "Bearer test-secret-key"})
            # Correct authentication reaches the database dependency, which is intentionally absent in this unit test.
            self.assertEqual(allowed.status_code, 503)
            self.assertIn("DATABASE_URL", allowed.text)

    def test_cors_preflight_reaches_cors_middleware_with_api_key_required(self):
        with patch.dict(os.environ, {
            "ARLETION_REQUIRE_API_KEY": "true",
            "ARLETION_API_KEY": "test-secret-key",
            "DATABASE_URL": "",
            "ARLETION_TEST_DATABASE_URL": "",
        }):
            response = api_request("OPTIONS", "/api/v1/campaigns", headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "authorization",
            })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("access-control-allow-origin"), "http://localhost:3000")

    def test_liveness_does_not_claim_database_readiness(self):
        with patch.dict(os.environ, {"DATABASE_URL": "", "ARLETION_TEST_DATABASE_URL": ""}):
            live = api_request("GET", "/live")
            ready = api_request("GET", "/health")
        self.assertEqual(live.status_code, 200)
        self.assertEqual(ready.status_code, 503)

    def test_health_reports_missing_database_instead_of_claiming_success(self):
        with patch.dict(os.environ, {"DATABASE_URL": "", "ARLETION_TEST_DATABASE_URL": ""}):
            response = api_request("GET", "/health")
        self.assertEqual(response.status_code, 503)
        self.assertIn("DATABASE_URL is not configured", response.json()["detail"]["database"]["detail"])

    def test_health_reports_unreachable_database_clearly(self):
        with patch.dict(os.environ, {"DATABASE_URL": "postgresql+psycopg://invalid:invalid@127.0.0.1:1/missing", "ARLETION_TEST_DATABASE_URL": ""}):
            response = api_request("GET", "/health")
        self.assertEqual(response.status_code, 503)
        self.assertIn("connected", response.json()["detail"]["database"])

    def test_database_backed_routes_return_actionable_error_without_database(self):
        with patch.dict(os.environ, {"DATABASE_URL": "", "ARLETION_TEST_DATABASE_URL": ""}):
            response = api_request("GET", "/api/v1/campaigns")
        self.assertEqual(response.status_code, 503)
        self.assertIn("DATABASE_URL", response.json()["detail"])

    def test_cors_uses_explicit_origin_allowlist(self):
        cors = next(middleware for middleware in app.user_middleware if middleware.cls is CORSMiddleware)
        allowed_origins = cors.kwargs["allow_origins"]
        self.assertIn("http://127.0.0.1:3000", allowed_origins)
        self.assertIn("http://localhost:3000", allowed_origins)
        self.assertNotIn("https://unapproved.example", allowed_origins)
        response = api_request("OPTIONS", "/api/v1/campaigns", headers={
            "Origin": "http://localhost:3000", "Access-Control-Request-Method": "GET"
        })
        self.assertEqual(response.headers.get("access-control-allow-origin"), "http://localhost:3000")
        denied = api_request("GET", "/live", headers={"Origin": "https://unapproved.example"})
        self.assertNotIn("access-control-allow-origin", denied.headers)
        self.assertEqual(denied.status_code, 200)

    def test_documented_json_and_flat_csv_import_formats(self):
        package = {"releases": [{"ocid": "ocds-9t57fa-1", "id": "release-1", "date": "2030-01-01T10:00:00Z", "tender": {"title": "Road maintenance", "status": "active", "tenderPeriod": {"startDate": "2030-01-01", "endDate": "2030-02-01"}}, "buyer": {"name": "Public works"}}]}
        parsed = parse_import(__import__("json").dumps(package), "json")
        row = normalize_record(parsed[0])
        self.assertEqual(row["external_id"], "ocds-9t57fa-1")
        self.assertEqual(row["buyer_name"], "Public works")
        self.assertEqual(row["status"], "open")
        csv_row = parse_import("ocid,title,buyer_name,closing_date,status,source_url\nocds-9t57fa-2,Bridge repair,Transport,2030-02-01,active,https://data.etenders.gov.za/", "csv")
        self.assertEqual(normalize_record(csv_row[0])["title"], "Bridge repair")

    def test_open_status_is_never_inferred_without_future_closing_date(self):
        item = normalize_record({"ocid": "ocds-9t57fa-3", "tender": {"title": "Notice", "status": "active"}})
        self.assertEqual(item["status"], "active_date_unverified")

    def test_bad_format_and_invalid_source_records_are_rejected_or_skipped(self):
        with self.assertRaises(ValueError):
            parse_import("{}", "xml")
        self.assertIsNone(normalize_record({"title": "no stable ID"}))
        unsafe_url = normalize_record({"ocid": "ocds-unsafe", "source_url": "javascript:alert(1)", "title": "Unsafe link"})
        self.assertEqual(unsafe_url["source_url"], "https://data.etenders.gov.za/")


class PostgreSQLIntegrationTests(unittest.TestCase):
    database_url = os.getenv("ARLETION_TEST_DATABASE_URL")

    @classmethod
    def setUpClass(cls):
        if not cls.database_url:
            raise unittest.SkipTest("Set ARLETION_TEST_DATABASE_URL to an isolated PostgreSQL test database.")
        cls.engine = engine_for_url(cls.database_url)
        Base.metadata.create_all(cls.engine)

    def setUp(self):
        with self.engine.begin() as connection:
            # Keep migration-seeded reference rows; clear tenant-owned/test data.
            connection.execute(text("TRUNCATE TABLE audit_events, suppression_records, consent_records, evidence_items, consumer_enquiries, leads, opportunities, source_records, campaigns, organizations RESTART IDENTITY CASCADE"))
            connection.execute(text("DELETE FROM source_registry WHERE id NOT IN ('00000000-0000-0000-0000-000000000002', '00000000-0000-0000-0000-000000000003')"))
            connection.execute(text("UPDATE source_registry SET permitted_use = 'review_required', enabled = FALSE, last_error = NULL WHERE id = '00000000-0000-0000-0000-000000000002'"))
            connection.execute(text("UPDATE source_registry SET permitted_use = 'approved', enabled = TRUE, last_error = NULL, last_synced_at = NULL WHERE id = '00000000-0000-0000-0000-000000000003'"))

    def test_source_can_be_explicitly_approved_after_manual_review(self):
        response = api_request(
            "POST",
            "/api/v1/sources",
            json={
                "name": "National Treasury eTender Transparency Portal",
                "url": "https://data.etenders.gov.za/",
                "category": "procurement_ocds",
                "status": "enabled",
                "note": "Reviewed source access and reuse terms for this test.",
            },
        )
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(response.json()["status"], "enabled")
        persisted = {
            source["name"]: source
            for source in api_request("GET", "/api/v1/sources").json()
        }["National Treasury eTender Transparency Portal"]
        self.assertEqual(persisted["status"], "enabled")

    def test_official_import_is_blocked_until_source_is_approved(self):
        response = api_request(
            "POST",
            "/api/v1/opportunities/import/official",
            json={"page_number": 1, "page_size": 1, "date_from": "2024-01-01", "date_to": "2024-01-02"},
        )
        self.assertEqual(response.status_code, 409, response.text)
        self.assertIn("not approved", response.json()["detail"].lower())

    def test_health_and_campaign_lead_source_crud_are_database_backed(self):
        self.assertEqual(api_request("GET", "/health").status_code, 200)
        default_sources = api_request("GET", "/api/v1/sources").json()
        self.assertTrue(any(source["name"] == "National Treasury eTender Transparency Portal" for source in default_sources))
        created = api_request("POST", "/api/v1/campaigns", json={"name": "Test leads", "objective": "Integration", "lead_type": "business"})
        self.assertEqual(created.status_code, 201, created.text)
        campaign = created.json()
        changed = api_request("PATCH", f"/api/v1/campaigns/{campaign['id']}", json={"status": "active"})
        self.assertEqual(changed.json()["status"], "active")
        body = {"campaign_id": campaign["id"], "organization": "Example Ltd", "lead_type": "business", "location": "Mbombela", "source": "Approved test source", "source_url": "https://source.example/record/1", "score": 75, "evidence_note": "Source record 1", "external_id": "external-1"}
        lead1 = api_request("POST", "/api/v1/leads", json=body)
        lead2 = api_request("POST", "/api/v1/leads", json=body)
        self.assertEqual(lead1.status_code, 201, lead1.text)
        self.assertEqual(lead1.json()["id"], lead2.json()["id"])
        self.assertEqual(len(api_request("GET", "/api/v1/leads?q=Mbombela").json()), 1)
        source_body = {"name": "Integration source", "url": "https://source.example", "category": "Test", "status": "review_required"}
        source1 = api_request("POST", "/api/v1/sources", json=source_body)
        source2 = api_request("POST", "/api/v1/sources", json=source_body)
        self.assertEqual(source1.json()["id"], source2.json()["id"])

    def test_lead_categories_filters_and_pagination_are_database_backed(self):
        campaign = api_request("POST", "/api/v1/campaigns", json={
            "name": "Category filter test", "objective": "Verify lead filters", "lead_type": "business"
        }).json()
        common = {
            "campaign_id": campaign["id"], "lead_type": "business",
            "location": "eMalahleni", "province": "Mpumalanga", "municipality": "eMalahleni", "source": "Approved test source",
            "source_url": "https://source.example/records", "status": "new",
        }
        first = api_request("POST", "/api/v1/leads", json={
            **common, "organization": "Mpumalanga Builders", "category": "Construction",
            "evidence_note": "Published business directory record",
        })
        second = api_request("POST", "/api/v1/leads", json={
            **common, "organization": "Lowveld Retail", "category": "Retail",
            "evidence_note": "Published business directory record",
        })
        third = api_request("POST", "/api/v1/leads", json={
            **common, "organization": "Witbank Civil Works", "category": "Construction",
            "evidence_note": "Published business directory record",
        })
        self.assertEqual([first.status_code, second.status_code, third.status_code], [201, 201, 201])

        filtered = api_request("GET", "/api/v1/leads/search", params={
            "category": "construction", "province": "mpumalanga", "lead_type": "business",
            "page": 1, "page_size": 1,
        })
        self.assertEqual(filtered.status_code, 200, filtered.text)
        self.assertEqual(filtered.json()["total"], 2)
        self.assertEqual(filtered.json()["page"], 1)
        self.assertEqual(filtered.json()["page_size"], 1)
        self.assertEqual(len(filtered.json()["items"]), 1)
        self.assertEqual(filtered.json()["items"][0]["category"], "Construction")
        self.assertEqual(filtered.json()["items"][0]["province"], "Mpumalanga")

        next_page = api_request("GET", "/api/v1/leads/search", params={
            "category": "Construction", "page": 2, "page_size": 1,
        }).json()
        self.assertEqual(next_page["total"], 2)
        self.assertEqual(len(next_page["items"]), 1)
        self.assertNotEqual(filtered.json()["items"][0]["id"], next_page["items"][0]["id"])
        self.assertEqual(api_request("GET", "/api/v1/leads/categories").json(), ["Construction", "Retail"])

    def test_lead_search_bounds_invalid_filters_and_urls(self):
        too_many = api_request("GET", "/api/v1/leads/search", params={"page_size": 101})
        self.assertEqual(too_many.status_code, 422)
        long_query = api_request("GET", "/api/v1/leads/search", params={"q": "x" * 121})
        self.assertEqual(long_query.status_code, 422)
        campaign = api_request("POST", "/api/v1/campaigns", json={
            "name": "Validation test", "objective": "Validate fields", "lead_type": "business"
        }).json()
        invalid_url = api_request("POST", "/api/v1/leads", json={
            "campaign_id": campaign["id"], "organization": "Unsafe URL Ltd",
            "lead_type": "business", "source": "Test source", "source_url": "javascript:alert(1)",
        })
        self.assertEqual(invalid_url.status_code, 422)
        invalid_status = api_request("POST", "/api/v1/leads", json={
            "campaign_id": campaign["id"], "organization": "Bad Status Ltd",
            "lead_type": "business", "source": "Test source",
            "source_url": "https://source.example/1", "status": "hacked",
        })
        self.assertEqual(invalid_status.status_code, 422)

    def test_openstreetmap_query_is_category_scoped_and_bounded(self):
        query = overpass_query("Construction", -25.8762, 29.21, 10000, 100)
        self.assertIn("around:10000,-25.876200,29.210000", query)
        self.assertIn('"shop"~"^(building_materials|hardware|trade|doityourself)$",i', query)
        self.assertIn('"craft"~"', query)
        self.assertTrue(query.endswith("out center tags meta 100;"))
        with self.assertRaises(ValueError):
            overpass_query("Unknown", -25.8762, 29.21, 10000, 100)

    def test_openstreetmap_normalizer_keeps_only_named_business_evidence(self):
        rows = normalize_osm_businesses({
            "elements": [
                {
                    "type": "node", "id": 123, "lat": -25.8762, "lon": 29.21,
                    "timestamp": "2026-11-08T09:00:00Z",
                    "tags": {
                        "name": "Witbank Building Supplies", "shop": "building_materials",
                        "website": "https://www.example.co.za/contact",
                        "contact:phone": "+27130000000", "contact:email": "owner@example.test",
                        "addr:suburb": "CBD",
                    },
                },
                {"type": "node", "id": 124, "tags": {"shop": "hardware"}},
                {"type": "way", "id": 123, "tags": {"name": "Witbank Building Supplies", "shop": "hardware"}},
            ]
        }, "Building materials", "eMalahleni", "Mpumalanga")
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["external_id"], "node/123")
        self.assertEqual(rows[0]["source_url"], "https://www.openstreetmap.org/node/123")
        self.assertEqual(rows[0]["website_domain"], "www.example.co.za")
        self.assertEqual(rows[0]["locality"], "CBD")
        self.assertEqual(rows[0]["province"], "Mpumalanga")
        self.assertEqual(rows[0]["tags"], {"shop": "building_materials", "addr:suburb": "CBD"})
        self.assertNotIn("contact:phone", rows[0]["tags"])
        self.assertNotIn("contact:email", rows[0]["tags"])
        self.assertEqual(OSM_ATTRIBUTION, "© OpenStreetMap contributors · ODbL 1.0")

    def test_openstreetmap_import_creates_source_confirmed_leads_and_updates_existing_rows(self):
        campaign = api_request("POST", "/api/v1/campaigns", json={
            "name": "eMalahleni building suppliers", "objective": "Find local building suppliers",
            "lead_type": "business", "geography": "eMalahleni, Mpumalanga",
        })
        self.assertEqual(campaign.status_code, 201, campaign.text)
        business = {
            "external_id": "node/123456", "name": "Witbank Building Supplies",
            "category": "Building materials", "locality": "eMalahleni", "province": "Mpumalanga",
            "website_domain": "www.example.co.za", "latitude": -25.8762, "longitude": 29.21,
            "source_url": "https://www.openstreetmap.org/node/123456",
            "source_updated_at": None,
            "tags": {"shop": "building_materials"},
        }
        body = {
            "campaign_id": campaign.json()["id"], "category": "Building materials",
            "locality": "eMalahleni", "province": "Mpumalanga",
            "latitude": -25.8762, "longitude": 29.21, "radius_m": 10000, "limit": 50,
        }
        with patch("app.main.fetch_osm_businesses", return_value=[business]) as fetch:
            first = api_request("POST", "/api/v1/leads/import/openstreetmap", json=body)
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(first.json()["inserted"], 1)
        self.assertEqual(first.json()["verification_status"], "source_confirmed")
        self.assertIn("not CIPC registration", first.json()["verification_scope"])
        fetch.assert_called_once_with("Building materials", -25.8762, 29.21, 10000, "eMalahleni", "Mpumalanga", 50)

        leads = api_request("GET", "/api/v1/leads/search", params={
            "category": "Building materials", "verification_status": "source_confirmed",
        })
        self.assertEqual(leads.status_code, 200, leads.text)
        self.assertEqual(leads.json()["total"], 1)
        item = leads.json()["items"][0]
        self.assertEqual(item["organization"], "Witbank Building Supplies")
        self.assertEqual(item["source"], "OpenStreetMap Business Directory")
        self.assertEqual(item["source_url"], "https://www.openstreetmap.org/node/123456")
        self.assertEqual(item["verification_status"], "source_confirmed")
        self.assertEqual(item["verification_source"], "OpenStreetMap")
        self.assertEqual(item["website_url"], "https://www.example.co.za")
        self.assertNotIn("phone", item)
        self.assertNotIn("email", item)

        with self.engine.begin() as connection:
            connection.execute(text(
                "UPDATE source_registry SET last_synced_at = NULL WHERE name = 'OpenStreetMap Business Directory'"
            ))
        with patch("app.main.fetch_osm_businesses", return_value=[business]):
            second = api_request("POST", "/api/v1/leads/import/openstreetmap", json=body)
        self.assertEqual(second.status_code, 200, second.text)
        self.assertEqual(second.json()["inserted"], 0)
        self.assertEqual(second.json()["updated"], 1)
        self.assertEqual(api_request("GET", "/api/v1/leads/search", params={
            "category": "Building materials", "verification_status": "source_confirmed",
        }).json()["total"], 1)

    def test_openstreetmap_import_blocks_wrong_campaign_and_applies_rate_limit(self):
        procurement = api_request("POST", "/api/v1/campaigns", json={
            "name": "Tender opportunities", "objective": "Procurement", "lead_type": "procurement",
        }).json()
        body = {
            "campaign_id": procurement["id"], "category": "Construction",
            "latitude": -25.8762, "longitude": 29.21,
        }
        wrong = api_request("POST", "/api/v1/leads/import/openstreetmap", json=body)
        self.assertEqual(wrong.status_code, 409)

        business = api_request("POST", "/api/v1/campaigns", json={
            "name": "Construction businesses", "objective": "Business outreach", "lead_type": "business",
        }).json()
        body["campaign_id"] = business["id"]
        with patch("app.main.fetch_osm_businesses", return_value=[]):
            first = api_request("POST", "/api/v1/leads/import/openstreetmap", json=body)
            limited = api_request("POST", "/api/v1/leads/import/openstreetmap", json=body)
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(first.json()["matched"], 0)
        self.assertEqual(limited.status_code, 429)

    def test_consumer_intake_is_disabled_until_storage_and_encryption_are_approved(self):
        with patch.dict(os.environ, {
            "ARLETION_CONSUMER_INTAKE_ENABLED": "false",
            "ARLETION_CONSUMER_STORAGE_APPROVED": "false",
            "ARLETION_CONSUMER_RBAC_APPROVED": "false",
            "ARLETION_PII_ENCRYPTION_KEY": "",
            "ARLETION_CONTACT_HASH_KEY": "",
            "ARLETION_CONSUMER_ACCESS_KEY": "",
        }):
            status = api_request("GET", "/api/v1/consumer-enquiries/status")
            listing = api_request("GET", "/api/v1/consumer-enquiries")
        self.assertEqual(status.status_code, 200)
        self.assertFalse(status.json()["enabled"])
        self.assertFalse(status.json()["public_form"])
        self.assertEqual(listing.status_code, 503)
        self.assertIn("disabled", listing.json()["detail"].lower())

    def test_consumer_enquiries_use_separate_encrypted_records_and_separate_marketing_consent(self):
        campaign = api_request("POST", "/api/v1/campaigns", json={
            "name": "Debt counselling enquiries", "objective": "Respond to voluntary requests",
            "lead_type": "consumer_enquiry", "status": "active",
        })
        self.assertEqual(campaign.status_code, 201, campaign.text)
        self.assertEqual(campaign.json()["pipeline"], "consumer")
        wrong_pipeline = api_request("POST", "/api/v1/leads", json={
            "campaign_id": campaign.json()["id"], "organization": "Consumer Pipeline Leakage",
            "lead_type": "business", "source": "Test source",
            "source_url": "https://source.example/consumer-campaign",
        })
        self.assertEqual(wrong_pipeline.status_code, 409)
        settings = {
            "ARLETION_CONSUMER_INTAKE_ENABLED": "true",
            "ARLETION_CONSUMER_STORAGE_APPROVED": "true",
            "ARLETION_CONSUMER_RBAC_APPROVED": "true",
            "ARLETION_PII_ENCRYPTION_KEY": Fernet.generate_key().decode(),
            "ARLETION_CONTACT_HASH_KEY": "test-contact-hash-key-that-is-at-least-32-bytes",
            "ARLETION_CONSUMER_ACCESS_KEY": "separate-consumer-contact-secret",
            "ARLETION_CONSUMER_RETENTION_DAYS": "90",
        }
        body = {
            "campaign_id": campaign.json()["id"], "full_name": "Mpho Testperson",
            "phone": "+27821234567", "email": "mpho@example.test",
            "province": "Mpumalanga", "locality": "eMalahleni",
            "preferred_channel": "whatsapp", "category": "debt_counselling",
            "source": "client_website_form", "processing_consent": True,
            "marketing_consent": True, "notice_version": "consumer-v1",
        }
        with patch.dict(os.environ, settings):
            created = api_request("POST", "/api/v1/consumer-enquiries", json=body)
            self.assertEqual(created.status_code, 201, created.text)
            item = created.json()
            self.assertTrue(item["contact_protected"])
            self.assertTrue(item["has_phone"])
            self.assertTrue(item["has_email"])
            self.assertTrue(item["marketing_consent"])
            self.assertNotIn("full_name", item)
            self.assertNotIn("phone", item)
            self.assertNotIn("email", item)

            listed = api_request("GET", "/api/v1/consumer-enquiries", params={"category": "debt_counselling"})
            self.assertEqual(listed.status_code, 200, listed.text)
            self.assertEqual(listed.json()["total"], 1)
            self.assertEqual(listed.json()["items"][0]["category"], "debt_counselling")

            denied = api_request("GET", f"/api/v1/consumer-enquiries/{item['id']}/contact")
            self.assertEqual(denied.status_code, 403)
            contact = api_request("GET", f"/api/v1/consumer-enquiries/{item['id']}/contact", headers={
                "X-Arletion-Consumer-Access": settings["ARLETION_CONSUMER_ACCESS_KEY"],
            })
            self.assertEqual(contact.status_code, 200)
            self.assertEqual(contact.json(), {
                "full_name": "Mpho Testperson", "phone": "+27821234567", "email": "mpho@example.test",
            })

            duplicate = api_request("POST", "/api/v1/consumer-enquiries", json=body)
            self.assertEqual(duplicate.status_code, 409)
            withdrawn = api_request("POST", f"/api/v1/consumer-enquiries/{item['id']}/withdraw-marketing", headers={
                "X-Arletion-Consumer-Access": settings["ARLETION_CONSUMER_ACCESS_KEY"],
            })
            self.assertEqual(withdrawn.status_code, 200)
            self.assertFalse(withdrawn.json()["marketing_consent"])
            self.assertTrue(withdrawn.json()["suppressed"])
            api_request("POST", f"/api/v1/consumer-enquiries/{item['id']}/withdraw-marketing", headers={
                "X-Arletion-Consumer-Access": settings["ARLETION_CONSUMER_ACCESS_KEY"],
            })

            campaigns = api_request("GET", "/api/v1/campaigns?pipeline=consumer").json()
            self.assertEqual(len(campaigns), 1)
            self.assertEqual(campaigns[0]["lead_count"], 1)
            self.assertEqual(api_request("GET", "/api/v1/campaigns?pipeline=business_procurement").json(), [])
            self.assertEqual(api_request("GET", "/api/v1/leads/search").json()["total"], 0)

        with self.engine.connect() as connection:
            encrypted = connection.execute(text(
                "SELECT name_ciphertext, phone_ciphertext, email_ciphertext FROM consumer_enquiries"
            )).one()
            consent_rows = connection.execute(text(
                "SELECT purpose, consent_status FROM consent_records ORDER BY purpose"
            )).all()
        self.assertNotIn("Mpho Testperson", encrypted.name_ciphertext)
        self.assertNotIn("+27821234567", encrypted.phone_ciphertext)
        self.assertNotIn("mpho@example.test", encrypted.email_ciphertext)
        self.assertIn(("electronic_direct_marketing", "withdrawn"), consent_rows)
        self.assertIn(("respond_to_consumer_enquiry", "granted"), consent_rows)
        with self.engine.connect() as connection:
            suppression_count = connection.execute(text("SELECT count(*) FROM suppression_records")).scalar_one()
        self.assertEqual(suppression_count, 1)

    def test_consumer_enquiry_requires_explicit_processing_consent_and_active_consumer_campaign(self):
        invalid = api_request("POST", "/api/v1/consumer-enquiries", json={
            "campaign_id": "00000000-0000-0000-0000-000000000001",
            "full_name": "Test Person", "phone": "+27821234567",
            "preferred_channel": "whatsapp", "processing_consent": False,
            "notice_version": "v1",
        })
        self.assertEqual(invalid.status_code, 422)

        business = api_request("POST", "/api/v1/campaigns", json={
            "name": "Business campaign", "objective": "Business only", "lead_type": "business",
        }).json()
        settings = {
            "ARLETION_CONSUMER_INTAKE_ENABLED": "true",
            "ARLETION_CONSUMER_STORAGE_APPROVED": "true",
            "ARLETION_CONSUMER_RBAC_APPROVED": "true",
            "ARLETION_PII_ENCRYPTION_KEY": Fernet.generate_key().decode(),
            "ARLETION_CONTACT_HASH_KEY": "test-contact-hash-key-that-is-at-least-32-bytes",
            "ARLETION_CONSUMER_ACCESS_KEY": "separate-consumer-contact-secret",
        }
        with patch.dict(os.environ, settings):
            wrong_campaign = api_request("POST", "/api/v1/consumer-enquiries", json={
                "campaign_id": business["id"], "full_name": "Test Person",
                "phone": "+27821234567", "preferred_channel": "whatsapp",
                "processing_consent": True, "notice_version": "v1",
            })
        self.assertEqual(wrong_campaign.status_code, 404)

    def test_official_release_import_is_repeatable_and_amendments_update_by_ocid(self):
        first = {"ocid": "ocds-9t57fa-integration", "id": "release-1", "date": "2030-01-01T10:00:00Z", "tender": {"title": "Road resurfacing", "status": "active", "tenderPeriod": {"startDate": "2030-01-01", "endDate": "2030-06-01"}, "documents": [{"url": "https://data.etenders.gov.za/notice/one"}]}, "buyer": {"name": "Road agency"}}
        amended = {**first, "id": "release-2", "date": "2030-02-01T10:00:00Z", "tender": {**first["tender"], "title": "Road resurfacing amended", "tenderPeriod": {"startDate": "2030-01-01", "endDate": "2030-07-01"}}}
        body = {"format": "json", "content": __import__("json").dumps({"releases": [first]})}
        first_result = api_request("POST", "/api/v1/opportunities/import", json=body)
        repeat_result = api_request("POST", "/api/v1/opportunities/import", json=body)
        self.assertEqual(first_result.status_code, 200, first_result.text)
        self.assertEqual(first_result.json()["inserted"], 1)
        self.assertEqual(repeat_result.json()["unchanged"], 1)
        amended_result = api_request("POST", "/api/v1/opportunities/import", json={"format": "json", "content": __import__("json").dumps({"releases": [first, amended]})})
        self.assertEqual(amended_result.status_code, 200, amended_result.text)
        records = api_request("GET", "/api/v1/opportunities").json()["items"]
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["title"], "Road resurfacing amended")
        self.assertEqual(records[0]["source_url"], "https://data.etenders.gov.za/notice/one")
        self.assertEqual(records[0]["status"], "open")
        with self.engine.connect() as connection:
            release_count = connection.execute(text("SELECT count(*) FROM source_records WHERE record_type = 'ocds_release'")).scalar_one()
        self.assertEqual(release_count, 2, "both original and amended releases retain provenance")

    def test_bad_import_reports_422_without_partial_rows(self):
        response = api_request("POST", "/api/v1/opportunities/import", json={"format": "invalid", "content": "{}"})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(api_request("GET", "/api/v1/opportunities").json()["items"], [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
