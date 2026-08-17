from __future__ import annotations

from datetime import timedelta

import frappe
from frappe.utils import now_datetime

from govp_erpnext.client import GovpExchangeClient, GovpExchangeError
from govp_erpnext.core import issuance_payload, retry_delay


PROCESSING_LEASE_MINUTES = 15


def _settings(company):
    settings = frappe.get_doc("GOVP Company Settings", company)
    return settings, settings.get_password("connector_token")


def _fail(job, error):
    job.last_error = str(error)[:1000]
    if getattr(error, "retryable", False) and job.attempts < 8:
        job.status = "Retry"
        job.next_attempt_at = now_datetime() + timedelta(seconds=retry_delay(job.attempts))
    else:
        job.status = "Needs Attention"
    job.save(ignore_permissions=True)


def _recover_stale_jobs():
    stale_before = now_datetime() - timedelta(minutes=PROCESSING_LEASE_MINUTES)
    frappe.db.sql(
        """
        update `tabGOVP Job`
        set status = 'Retry', next_attempt_at = %s,
            last_error = 'Trabajo recuperado tras expirar el bloqueo de procesamiento.'
        where status = 'Processing' and modified < %s
        """,
        (now_datetime(), stale_before),
    )
    frappe.db.commit()


def _claim_job(name):
    claimed_at = now_datetime()
    frappe.db.sql(
        """
        update `tabGOVP Job`
        set status = 'Processing', attempts = coalesce(attempts, 0) + 1,
            modified = %s, modified_by = %s
        where name = %s and status in ('Pending', 'Retry')
          and next_attempt_at <= %s
        """,
        (claimed_at, frappe.session.user, name, claimed_at),
    )
    claimed = frappe.db._cursor.rowcount == 1
    frappe.db.commit()
    return frappe.get_doc("GOVP Job", name) if claimed else None


def _issue(job, client, settings):
    source = frappe.get_doc(job.source_doctype, job.source_name)
    payload = issuance_payload(source.as_dict(), frappe.local.site, settings.validity_days or 365)
    result = client.issue(payload, job.idempotency_key)
    govp = result["govp"]
    frappe.db.set_value(job.source_doctype, job.source_name, {
        "govp_code": govp["code"], "govp_verify_url": govp["verifyUrl"],
        "govp_status": "Valid", "govp_last_error": None,
    }, update_modified=False)
    job.govp_code = govp["code"]


def _verify(job, client):
    result = client.verify(job.reference)
    verification = result["verification"]
    status = str(verification["status"]).lower()
    frappe.db.set_value(job.source_doctype, job.source_name, {
        "govp_verification_status": status,
        "govp_last_error": verification.get("reasonCode") if status not in {"valid", "active"} else None,
    }, update_modified=False)
    job.govp_code = job.reference


def process_due_jobs(limit=50):
    _recover_stale_jobs()
    names = frappe.get_all("GOVP Job", filters={
        "status": ["in", ["Pending", "Retry"]],
        "next_attempt_at": ["<=", now_datetime()],
    }, order_by="creation asc", limit=min(int(limit), 100), pluck="name")
    for name in names:
        job = _claim_job(name)
        if not job:
            continue
        try:
            settings, token = _settings(job.company)
            client = GovpExchangeClient(settings.exchange_url, token)
            if job.action == "Issue":
                _issue(job, client, settings)
            elif job.action == "Verify":
                _verify(job, client)
            else:
                raise GovpExchangeError("Acción reservada para reconciliación humana")
            job.status = "Completed"
            job.last_error = None
            job.save(ignore_permissions=True)
            frappe.db.commit()
        except Exception as error:
            _fail(job, error)
            frappe.db.commit()
