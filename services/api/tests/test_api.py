import os
import unittest
from unittest.mock import patch

from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.database import engine_for_url, normalize_database_url
from app.main import app
from app.models import Base
from app.procurement import normalize_record, parse_import


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
            connection.execute(text("TRUNCATE TABLE audit_events, suppression_records, consent_records, evidence_items, leads, opportunities, source_records, source_registry, campaigns, organizations, tenants RESTART IDENTITY CASCADE"))

    def test_health_and_campaign_lead_source_crud_are_database_backed(self):
        self.assertEqual(api_request("GET", "/health").status_code, 200)
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
