import frappe
from frappe.tests.utils import FrappeTestCase


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
