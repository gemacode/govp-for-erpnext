from __future__ import annotations

import frappe

from govp_erpnext.core import idempotency_key


def _enabled(company, field):
    return bool(frappe.db.get_value("GOVP Company Settings", company, field))


def _create_job(doc, action, reference=None):
    key = idempotency_key(frappe.local.site, doc.company, doc.doctype, doc.name)
    if frappe.db.exists("GOVP Job", {"idempotency_key": key, "action": action}):
        return
    frappe.get_doc({
        "doctype": "GOVP Job",
        "company": doc.company,
        "source_doctype": doc.doctype,
        "source_name": doc.name,
        "action": action,
        "reference": reference,
        "idempotency_key": key,
        "status": "Pending",
    }).insert(ignore_permissions=True)
    frappe.enqueue("govp_erpnext.jobs.process_due_jobs", queue="short", enqueue_after_commit=True)


def on_delivery_note_submit(doc, method=None):
    if _enabled(doc.company, "enabled") and _enabled(doc.company, "auto_issue_delivery"):
        _create_job(doc, "Issue")


def on_purchase_receipt_submit(doc, method=None):
    reference = getattr(doc, "govp_reference", None)
    if reference and _enabled(doc.company, "enabled") and _enabled(doc.company, "auto_verify_receipt"):
        _create_job(doc, "Verify", reference)


def on_delivery_note_cancel(doc, method=None):
    # Cancellation never silently revokes legal evidence. It creates an auditable
    # exception for an authorised user to reconcile in GOVP Exchange.
    if getattr(doc, "govp_code", None):
        frappe.get_doc({
            "doctype": "GOVP Job", "company": doc.company,
            "source_doctype": doc.doctype, "source_name": doc.name,
            "action": "Reconcile", "reference": doc.govp_code,
            "idempotency_key": idempotency_key(frappe.local.site, doc.company, doc.doctype, doc.name) + ":cancel",
            "status": "Needs Attention",
            "last_error": "Delivery Note cancelada: revisar revocación o sustitución en GOVP Exchange.",
        }).insert(ignore_permissions=True)
