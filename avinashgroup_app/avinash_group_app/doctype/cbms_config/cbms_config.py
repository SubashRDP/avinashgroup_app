# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class CBMSConfig(Document):
	def validate(self):
		duplicate = frappe.db.exists(
			"CBMS Config", {"company": self.company, "name": ["!=", self.name]}
		)
		if duplicate:
			frappe.throw(_("CBMS Config already exists for company {0}").format(self.company))


@frappe.whitelist()
def sync_failed_now(cbms_config_name):
	"""Manually re-queue every unsynced CBMS Bill / CBMS Bill Return for one company."""
	from avinashgroup_app.custom_code.CBMS.scheduler import queue_failed_for_company

	config = frappe.get_doc("CBMS Config", cbms_config_name)
	return queue_failed_for_company(config)
