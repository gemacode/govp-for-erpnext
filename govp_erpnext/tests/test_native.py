from datetime import date

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
from govp_erpnext.jobs import _claim_job, process_due_jobs


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
        settings = frappe.get_doc("GOVP Company Settings", company)
    else:
        settings = frappe.get_doc({"doctype": "GOVP Company Settings", "company": company})
    settings.update({
        "enabled": 1,
        "exchange_url": "https://partners.gemacode.org/api/exchange",
        "connector_token": "native-test-token",
        "validity_days": 365,
        "auto_issue_delivery": 1,
        "auto_verify_receipt": 1,
    })
    return settings.save(ignore_permissions=True) if settings.name else settings.insert(ignore_permissions=True)


def _tree_leaf(doctype, name_field, parent_field, root, leaf):
    if not frappe.db.exists(doctype, root):
        frappe.get_doc({
            "doctype": doctype,
            name_field: root,
            "is_group": 1,
        }).insert(ignore_permissions=True)
    if not frappe.db.exists(doctype, leaf):
        frappe.get_doc({
            "doctype": doctype,
            name_field: leaf,
            parent_field: root,
            "is_group": 0,
        }).insert(ignore_permissions=True)
    return leaf


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

    def test_existing_companies_receive_an_inactive_setup_record(self):
        company = _company("GOVP Setup Draft", "GVSD")
        settings = frappe.get_doc("GOVP Company Settings", company)
        self.assertEqual(settings.enabled, 0)
        self.assertEqual(settings.validity_days, 365)


class TestGovpErpnextLifecycle(FrappeTestCase):
    def setUp(self):
        super().setUp()
        self.company_a = _company("GOVP Native A", "GVNA")
        self.company_b = _company("GOVP Native B", "GVNB")
        if not frappe.defaults.get_global_default("company"):
            frappe.defaults.set_global_default("company", self.company_a)
        _settings(self.company_a)
        _settings(self.company_b)
        frappe.db.delete("GOVP Job", {"company": ["in", [self.company_a, self.company_b, "_Test Company"]]})

    def test_issue_jobs_are_idempotent_and_company_scoped(self):
        with patch("frappe.enqueue"):
            on_delivery_note_submit(_source(self.company_a))
            on_delivery_note_submit(_source(self.company_a))
            on_delivery_note_submit(_source(self.company_b))
        jobs = frappe.get_all("GOVP Job", filters={"action": "Issue"}, fields=["company", "idempotency_key"])
        selected = [job for job in jobs if job.company in {self.company_a, self.company_b}]
        self.assertEqual(len(selected), 2)
        self.assertEqual({job.company for job in selected}, {self.company_a, self.company_b})
        self.assertEqual(len({job.idempotency_key for job in selected}), 2)

    def test_purchase_receipt_creates_verification_job(self):
        with patch("frappe.enqueue"):
            on_purchase_receipt_submit(_source(self.company_a, reference="GOVP-NATIVE-001"))
        job = frappe.get_last_doc("GOVP Job", {"company": self.company_a, "action": "Verify", "reference": "GOVP-NATIVE-001"})
        self.assertEqual(job.reference, "GOVP-NATIVE-001")
        self.assertEqual(job.status, "Pending")

    def test_real_delivery_and_receipt_documents_fire_hooks(self):
        from erpnext import get_default_company

        company = get_default_company()
        _settings(company)
        warehouse = frappe.db.get_value("Warehouse", {"company": company, "is_group": 0}, "name")
        customer_group = _tree_leaf(
            "Customer Group", "customer_group_name", "parent_customer_group",
            "All GOVP Customer Groups", "GOVP Native Customers",
        )
        territory = _tree_leaf(
            "Territory", "territory_name", "parent_territory",
            "All GOVP Territories", "GOVP Native Territory",
        )
        supplier_group = _tree_leaf(
            "Supplier Group", "supplier_group_name", "parent_supplier_group",
            "All GOVP Supplier Groups", "GOVP Native Suppliers",
        )
        item_group = _tree_leaf(
            "Item Group", "item_group_name", "parent_item_group",
            "All GOVP Item Groups", "GOVP Native Services",
        )
        if not frappe.db.exists("UOM", "GOVP Unit"):
            frappe.get_doc({
                "doctype": "UOM",
                "uom_name": "GOVP Unit",
                "must_be_whole_number": 1,
                "enabled": 1,
            }).insert(ignore_permissions=True)
        current_year = frappe.utils.getdate().year
        fiscal_year = f"GOVP Native {current_year}"
        if not frappe.db.exists("Fiscal Year", fiscal_year):
            frappe.get_doc({
                "doctype": "Fiscal Year",
                "year": fiscal_year,
                "year_start_date": date(current_year, 1, 1),
                "year_end_date": date(current_year, 12, 31),
                "disabled": 0,
            }).insert(ignore_permissions=True)
        for price_list, buying, selling in (
            ("GOVP Native Buying", 1, 0),
            ("GOVP Native Selling", 0, 1),
        ):
            if not frappe.db.exists("Price List", price_list):
                frappe.get_doc({
                    "doctype": "Price List",
                    "price_list_name": price_list,
                    "currency": "EUR",
                    "buying": buying,
                    "selling": selling,
                    "enabled": 1,
                }).insert(ignore_permissions=True)

        if not frappe.db.exists("Customer", "GOVP Native Customer"):
            frappe.get_doc({
                "doctype": "Customer",
                "customer_name": "GOVP Native Customer",
                "customer_type": "Company",
                "customer_group": customer_group,
                "territory": territory,
            }).insert(ignore_permissions=True)
        if not frappe.db.exists("Supplier", "GOVP Native Supplier"):
            frappe.get_doc({
                "doctype": "Supplier",
                "supplier_name": "GOVP Native Supplier",
                "supplier_group": supplier_group,
            }).insert(ignore_permissions=True)
        if not frappe.db.exists("Item", "GOVP-NATIVE-SERVICE"):
            frappe.get_doc({
                "doctype": "Item",
                "item_code": "GOVP-NATIVE-SERVICE",
                "item_name": "GOVP Native Service",
                "item_group": item_group,
                "stock_uom": "GOVP Unit",
                "is_stock_item": 0,
            }).insert(ignore_permissions=True)

        delivery = frappe.get_doc({
            "doctype": "Delivery Note",
            "company": company,
            "customer": "GOVP Native Customer",
            "selling_price_list": "GOVP Native Selling",
            "price_list_currency": "EUR",
            "plc_conversion_rate": 1,
            "items": [{
                "item_code": "GOVP-NATIVE-SERVICE",
                "qty": 2,
                "rate": 10,
                "warehouse": warehouse,
            }],
        }).insert(ignore_permissions=True)
        with patch("frappe.enqueue"):
            delivery.submit()
        issue = frappe.get_last_doc("GOVP Job", {
            "source_doctype": "Delivery Note",
            "source_name": delivery.name,
            "action": "Issue",
        })
        self.assertEqual(issue.company, delivery.company)
        self.assertEqual(issue.status, "Pending")

        receipt = frappe.get_doc({
            "doctype": "Purchase Receipt",
            "company": company,
            "supplier": "GOVP Native Supplier",
            "govp_reference": "GOVP-NATIVE-RECEIPT",
            "buying_price_list": "GOVP Native Buying",
            "price_list_currency": "EUR",
            "plc_conversion_rate": 1,
            "items": [{
                "item_code": "GOVP-NATIVE-SERVICE",
                "qty": 3,
                "rate": 8,
                "warehouse": warehouse,
            }],
        }).insert(ignore_permissions=True)
        with patch("frappe.enqueue"):
            receipt.submit()
        verify = frappe.get_last_doc("GOVP Job", {
            "source_doctype": "Purchase Receipt",
            "source_name": receipt.name,
            "action": "Verify",
        })
        self.assertEqual(verify.reference, "GOVP-NATIVE-RECEIPT")
        self.assertEqual(verify.status, "Pending")

    def test_verification_job_retries_then_completes_without_duplication(self):
        with patch("frappe.enqueue"):
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

    def test_only_one_worker_can_claim_a_job(self):
        with patch("frappe.enqueue"):
            on_purchase_receipt_submit(_source(self.company_a, reference="GOVP-NATIVE-CLAIM"))
        job = frappe.get_last_doc("GOVP Job", {"company": self.company_a, "reference": "GOVP-NATIVE-CLAIM"})
        self.assertIsNotNone(_claim_job(job.name))
        self.assertIsNone(_claim_job(job.name))

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
