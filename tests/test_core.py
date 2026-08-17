import json
import pathlib
import re
import sys
import tomllib
import unittest
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from govp_erpnext.core import canonical_lines, evidence_digest, idempotency_key, issuance_payload, retry_delay, validate_exchange_url


PUBLIC = lambda host, port, type=None: [(2, 1, 6, "", ("93.184.216.34", port))]
PRIVATE = lambda host, port, type=None: [(2, 1, 6, "", ("127.0.0.1", port))]


class CoreTest(unittest.TestCase):
    def setUp(self):
        self.items = [
            {"item_code":"B", "qty":"2.00", "uom":"Nos", "warehouse":"Stores", "serial_no":"S2\nS1"},
            {"item_code":"A", "qty":1, "uom":"Kg", "warehouse":"Main", "batch_no":"LOT-1"},
        ]

    def test_lines_are_canonical_and_serials_sorted(self):
        rows = canonical_lines(self.items)
        self.assertEqual(rows[0]["item"], "A")
        self.assertEqual(rows[1]["serials"], ["S1", "S2"])
        self.assertEqual(rows[1]["quantity"], "2")

    def test_digest_is_order_independent(self):
        self.assertEqual(evidence_digest(self.items), evidence_digest(list(reversed(self.items))))
        self.assertEqual(len(evidence_digest(self.items)), 64)

    def test_digest_changes_with_business_data(self):
        changed = json.loads(json.dumps(self.items)); changed[0]["qty"] = 3
        self.assertNotEqual(evidence_digest(self.items), evidence_digest(changed))

    def test_idempotency_is_stable(self):
        one = idempotency_key("site", "Company A", "Delivery Note", "DN-1")
        self.assertEqual(one, idempotency_key("site", "Company A", "Delivery Note", "DN-1"))
        self.assertLessEqual(len(one), 160)

    def test_idempotency_separates_company(self):
        self.assertNotEqual(idempotency_key("site", "A", "Delivery Note", "DN-1"), idempotency_key("site", "B", "Delivery Note", "DN-1"))

    def test_payload_minimizes_personal_data(self):
        document = {"name":"DN-1", "company":"ACME", "customer_name":"Persona", "contact_email":"secret@example.test", "items":self.items}
        result = issuance_payload(document, "site", 30, datetime(2026, 1, 1, tzinfo=timezone.utc))
        encoded = json.dumps(result)
        self.assertNotIn("Persona", encoded)
        self.assertNotIn("secret@", encoded)
        self.assertEqual(result["source"]["platform"], "erpnext")
        self.assertEqual(result["validUntil"], "2026-01-31T00:00:00Z")

    def test_https_public_url_is_accepted(self):
        self.assertEqual(validate_exchange_url("https://exchange.example/api/", PUBLIC), "https://exchange.example/api")

    def test_http_is_rejected(self):
        with self.assertRaises(ValueError): validate_exchange_url("http://exchange.example", PUBLIC)

    def test_embedded_credentials_are_rejected(self):
        with self.assertRaises(ValueError): validate_exchange_url("https://user:pass@exchange.example", PUBLIC)

    def test_localhost_is_rejected(self):
        with self.assertRaises(ValueError): validate_exchange_url("https://localhost", PUBLIC)

    def test_private_resolution_is_rejected(self):
        with self.assertRaises(ValueError): validate_exchange_url("https://exchange.example", PRIVATE)

    def test_retry_is_bounded(self):
        self.assertEqual(retry_delay(1), 30)
        self.assertEqual(retry_delay(2), 60)
        self.assertEqual(retry_delay(99), 21600)


class StructureTest(unittest.TestCase):
    def test_distribution_name_matches_frappe_app_name(self):
        with (ROOT / "pyproject.toml").open("rb") as handle:
            project = tomllib.load(handle)["project"]
        self.assertEqual(project["name"], "govp_erpnext")

    def test_release_version_is_consistent(self):
        with (ROOT / "pyproject.toml").open("rb") as handle:
            version = tomllib.load(handle)["project"]["version"]
        package = (ROOT / "govp_erpnext/__init__.py").read_text()
        client = (ROOT / "govp_erpnext/client.py").read_text()
        self.assertIn(f'__version__ = "{version}"', package)
        self.assertIsNotNone(re.search(rf"GOVP-for-ERPNext/{re.escape(version)}\b", client))

    def test_hooks_cover_delivery_receipt_and_scheduler(self):
        hooks = (ROOT / "govp_erpnext/hooks.py").read_text()
        for fragment in ["Delivery Note", "Purchase Receipt", "on_submit", "*/5 * * * *", "required_apps"]:
            self.assertIn(fragment, hooks)

    def test_secret_is_password(self):
        settings = json.loads((ROOT / "govp_erpnext/govp_erpnext/doctype/govp_company_settings/govp_company_settings.json").read_text())
        token = next(field for field in settings["fields"] if field["fieldname"] == "connector_token")
        self.assertEqual(token["fieldtype"], "Password")

    def test_job_is_company_scoped_and_idempotent(self):
        job = json.loads((ROOT / "govp_erpnext/govp_erpnext/doctype/govp_job/govp_job.json").read_text())
        fields = {field["fieldname"]: field for field in job["fields"]}
        self.assertEqual(fields["company"]["options"], "Company")
        self.assertEqual(fields["idempotency_key"]["unique"], 1)

    def test_uninstall_removes_only_owned_fields(self):
        source = (ROOT / "govp_erpnext/install.py").read_text()
        self.assertIn('frappe.delete_doc("Custom Field", name', source)
        self.assertNotIn("delete_site", source)

    def test_exchange_contract_paths_are_explicit(self):
        source = (ROOT / "govp_erpnext/client.py").read_text()
        for fragment in ["/connectors/me", "/connectors/issue", "/govps/", "Idempotency-Key"]:
            self.assertIn(fragment, source)


if __name__ == "__main__":
    unittest.main()
