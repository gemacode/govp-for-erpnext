import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


FIELDS = {
    "Delivery Note": [
        {"fieldname": "govp_section", "label": "GOVP Exchange", "fieldtype": "Section Break", "insert_after": "terms"},
        {"fieldname": "govp_code", "label": "GOVP", "fieldtype": "Data", "read_only": 1, "no_copy": 1, "insert_after": "govp_section"},
        {"fieldname": "govp_verify_url", "label": "URL de comprobación", "fieldtype": "Data", "read_only": 1, "no_copy": 1, "insert_after": "govp_code"},
        {"fieldname": "govp_status", "label": "Estado GOVP", "fieldtype": "Data", "read_only": 1, "no_copy": 1, "insert_after": "govp_verify_url"},
        {"fieldname": "govp_last_error", "label": "Incidencia GOVP", "fieldtype": "Small Text", "read_only": 1, "no_copy": 1, "insert_after": "govp_status"},
    ],
    "Purchase Receipt": [
        {"fieldname": "govp_section", "label": "GOVP Exchange", "fieldtype": "Section Break", "insert_after": "terms"},
        {"fieldname": "govp_reference", "label": "GOVP del proveedor", "fieldtype": "Data", "no_copy": 1, "insert_after": "govp_section"},
        {"fieldname": "govp_verification_status", "label": "Comprobación GOVP", "fieldtype": "Data", "read_only": 1, "no_copy": 1, "insert_after": "govp_reference"},
        {"fieldname": "govp_last_error", "label": "Incidencia GOVP", "fieldtype": "Small Text", "read_only": 1, "no_copy": 1, "insert_after": "govp_verification_status"},
    ],
}


def after_install():
    create_custom_fields(FIELDS, update=True)
    ensure_all_company_settings()


def after_migrate():
    create_custom_fields(FIELDS, update=True)
    ensure_all_company_settings()


def ensure_company_settings(doc, method=None):
    company = doc if isinstance(doc, str) else getattr(doc, "name", None)
    if not company or not frappe.db.table_exists("GOVP Company Settings"):
        return None
    if frappe.db.exists("GOVP Company Settings", company):
        return frappe.get_doc("GOVP Company Settings", company)
    return frappe.get_doc({
        "doctype": "GOVP Company Settings",
        "company": company,
        "enabled": 0,
        "exchange_url": "https://partners.gemacode.org/api/exchange",
        "validity_days": 365,
        "auto_issue_delivery": 1,
        "auto_verify_receipt": 1,
    }).insert(ignore_permissions=True)


def ensure_all_company_settings():
    if not frappe.db.table_exists("GOVP Company Settings"):
        return
    for company in frappe.get_all("Company", pluck="name"):
        ensure_company_settings(company)


def before_uninstall():
    names = [f"{doctype}-{field['fieldname']}" for doctype, fields in FIELDS.items() for field in fields]
    for name in names:
        if frappe.db.exists("Custom Field", name):
            frappe.delete_doc("Custom Field", name, force=True, ignore_permissions=True)
