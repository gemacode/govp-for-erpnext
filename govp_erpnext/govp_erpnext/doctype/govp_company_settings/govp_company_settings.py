import frappe
from frappe.model.document import Document

from govp_erpnext.core import validate_exchange_url


class GOVPCompanySettings(Document):
    def autoname(self):
        self.name = self.company

    def validate(self):
        self.exchange_url = validate_exchange_url(self.exchange_url)
        if not 1 <= int(self.validity_days or 0) <= 3650:
            frappe.throw("La validez debe estar entre 1 y 3650 días")
