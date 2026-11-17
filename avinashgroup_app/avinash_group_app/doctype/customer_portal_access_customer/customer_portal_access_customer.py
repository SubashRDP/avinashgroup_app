# Copyright (c) 2026, Avinash Group and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class CustomerPortalAccessCustomer(Document):
	"""One customer this portal login can act for — see Customer Portal Access."""
