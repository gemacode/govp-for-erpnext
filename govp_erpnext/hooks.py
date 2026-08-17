app_name = "govp_erpnext"
app_title = "GOVP for ERPNext"
app_publisher = "Gemacode"
app_description = "Emisión y comprobación GOVP sin código desde ERPNext"
app_email = "opensource@gemacode.org"
app_license = "Apache-2.0"
required_apps = ["erpnext"]

doc_events = {
    "Delivery Note": {
        "on_submit": "govp_erpnext.handlers.on_delivery_note_submit",
        "on_cancel": "govp_erpnext.handlers.on_delivery_note_cancel",
    },
    "Purchase Receipt": {
        "on_submit": "govp_erpnext.handlers.on_purchase_receipt_submit",
    },
}

scheduler_events = {
    "cron": {
        "*/5 * * * *": ["govp_erpnext.jobs.process_due_jobs"],
    },
}

after_install = "govp_erpnext.install.after_install"
after_migrate = "govp_erpnext.install.after_migrate"
before_uninstall = "govp_erpnext.install.before_uninstall"

doctype_js = {
    "GOVP Company Settings": "public/js/govp_company_settings.js",
}
