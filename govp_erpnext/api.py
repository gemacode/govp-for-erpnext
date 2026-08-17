import frappe

from govp_erpnext.client import GovpExchangeClient


@frappe.whitelist()
def test_connection(company):
    frappe.only_for("System Manager")
    settings = frappe.get_doc("GOVP Company Settings", company)
    result = GovpExchangeClient(settings.exchange_url, settings.get_password("connector_token")).inspect()
    return {"ok": True, "connector": result.get("connector", result)}
