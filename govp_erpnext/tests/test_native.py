import frappe
from frappe.tests.utils import FrappeTestCase
from unittest.mock import patch

from govp_erpnext.client import GovpExchangeError
from govp_erpnext.handlers import (
    on_delivery_note_cancel,
    on_delivery_note_submit,
    on_purchase_receipt_submit,
)
from govp_erpnext.install import after_install, before_uninstall
from govp_erpnext.jobs import process_due_jobs


def _company(name, abbreviation):
    if not frappe.db.exists("Warehouse Type", "Transit"):
        frappe.get_doc({"doctype": "Warehouse Type", "name": "Transit"}).insert(ignore_permissions=True)
    if not frappe.db.exists("Company", name):
        frappe.get_doc({
            "doctype": "Company",
            "company_name": name,
            "abbr": abbreviation,
            "default_currency": "EUR",
            "country": "Spain",
        }).insert(ignore_permissions=True)
    return name


def _settings(company):
    if frappe.db.exists("GOVP Company Settings", company):
        return frappe.get_doc("GOVP Company Settings", company)
    return frappe.get_doc({
        "doctype": "GOVP Company Settings",
        "company": company,
        "enabled": 1,
        "exchange_url": "https://partners.gemacode.org/api/exchange",
        "connector_token": "native-test-token",
        "validity_days": 365,
        "auto_issue_delivery": 1,
        "auto_verify_receipt": 1,
    }).insert(ignore_permissions=True)


def _source(company, reference=None, code=None):
    return frappe._dict({
        "doctype": "Company",
        "name": company,
        "company": company,
        "govp_reference": reference,
        "govp_code": code,
    })


class TestGovpErpnextInstallation(FrappeTestCase):
    def test_doctypes_and_company_isolation_exist(self):
        self.assertTrue(frappe.db.table_exists("GOVP Company Settings"))
        self.assertTrue(frappe.db.table_exists("GOVP Job"))
        self.assertTrue(frappe.get_meta("GOVP Job").has_field("company"))

    def test_owned_fields_are_installed(self):
        delivery = frappe.get_meta("Delivery Note")
        receipt = frappe.get_meta("Purchase Receipt")
        self.assertTrue(delivery.has_field("govp_code"))
        self.assertTrue(delivery.has_field("govp_verify_url"))
        self.assertTrue(receipt.has_field("govp_reference"))
        self.assertTrue(receipt.has_field("govp_verification_status"))

    def test_connector_token_is_a_password_field(self):
        token = frappe.get_meta("GOVP Company Settings").get_field("connector_token")
        self.assertEqual(token.fieldtype, "Password")


class TestGovpErpnextLifecycle(FrappeTestCase):
    def setUp(self):
        super().setUp()
        self.company_a = _company("GOVP Native A", "GVNA")
        self.company_b = _company("GOVP Native B", "GVNB")
        _settings(self.company_a)
        _settings(self.company_b)
        frappe.db.delete("GOVP Job", {"company": ["in", [self.company_a, self.company_b]]})

    def test_issue_jobs_are_idempotent_and_company_scoped(self):
        on_delivery_note_submit(_source(self.company_a))
        on_delivery_note_submit(_source(self.company_a))
        on_delivery_note_submit(_source(self.company_b))
        jobs = frappe.get_all("GOVP Job", filters={"action": "Issue"}, fields=["company", "idempotency_key"])
        selected = [job for job in jobs if job.company in {self.company_a, self.company_b}]
        self.assertEqual(len(selected), 2)
        self.assertEqual({job.company for job in selected}, {self.company_a, self.company_b})
        self.assertEqual(len({job.idempotency_key for job in selected}), 2)

    def test_purchase_receipt_creates_verification_job(self):
        on_purchase_receipt_submit(_source(self.company_a, reference="GOVP-NATIVE-001"))
        job = frappe.get_last_doc("GOVP Job", {"company": self.company_a, "action": "Verify", "reference": "GOVP-NATIVE-001"})
        self.assertEqual(job.reference, "GOVP-NATIVE-001")
        self.assertEqual(job.status, "Pending")

    def test_verification_job_retries_then_completes_without_duplication(self):
        on_purchase_receipt_submit(_source(self.company_a, reference="GOVP-NATIVE-RETRY"))

        class RetryClient:
            def __init__(self, *args, **kwargs):
                pass

            def verify(self, reference):
                raise GovpExchangeError("transient", retryable=True)

        with patch("govp_erpnext.jobs.GovpExchangeClient", RetryClient), patch.object(frappe.db, "set_value"):
            process_due_jobs()
        job = frappe.get_last_doc("GOVP Job", {"company": self.company_a, "action": "Verify", "reference": "GOVP-NATIVE-RETRY"})
        self.assertEqual(job.status, "Retry")
        self.assertEqual(job.attempts, 1)

        frappe.db.set_value("GOVP Job", job.name, "next_attempt_at", frappe.utils.now_datetime())

        class SuccessClient:
            def __init__(self, *args, **kwargs):
                pass

            def verify(self, reference):
                return {"verification": {"status": "valid"}}

        with patch("govp_erpnext.jobs.GovpExchangeClient", SuccessClient), patch.object(frappe.db, "set_value"):
            process_due_jobs()
        job.reload()
        self.assertEqual(job.status, "Completed")
        self.assertEqual(job.attempts, 2)
        self.assertEqual(job.govp_code, "GOVP-NATIVE-RETRY")
        self.assertEqual(frappe.db.count("GOVP Job", {"company": self.company_a, "action": "Verify", "reference": "GOVP-NATIVE-RETRY"}), 1)

    def test_cancel_creates_human_reconciliation(self):
        on_delivery_note_cancel(_source(self.company_a, code="GOVP-NATIVE-CANCEL"))
        job = frappe.get_last_doc("GOVP Job", {"company": self.company_a, "action": "Reconcile"})
        self.assertEqual(job.status, "Needs Attention")
        self.assertEqual(job.reference, "GOVP-NATIVE-CANCEL")
        self.assertIn("cancelada", job.last_error)

    def test_uninstall_removes_owned_fields_and_reinstall_restores_them(self):
        before_uninstall()
        self.assertFalse(frappe.db.exists("Custom Field", "Delivery Note-govp_code"))
        self.assertFalse(frappe.db.exists("Custom Field", "Purchase Receipt-govp_reference"))
        after_install()
        self.assertTrue(frappe.db.exists("Custom Field", "Delivery Note-govp_code"))
        self.assertTrue(frappe.db.exists("Custom Field", "Purchase Receipt-govp_reference"))
