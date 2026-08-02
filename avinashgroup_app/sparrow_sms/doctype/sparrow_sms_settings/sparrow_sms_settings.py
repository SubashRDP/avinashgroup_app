# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class SparrowSMSSettings(Document):
	pass


@frappe.whitelist()
def send_test_sms():
	"""Send a one-off test SMS to Test Mobile No, to verify Sparrow SMS
	credentials/connectivity on their own, independent of any Sales Invoice."""
	settings = frappe.get_cached_doc("Sparrow SMS Settings")
	if not settings.test_mobile_no:
		frappe.throw(_("Set a Test Mobile No first."))
	if not settings.token:
		frappe.throw(_("Set a Token first."))

	from avinashgroup_app.sparrow_sms.sms_dispatch import send_sms

	message = "This is a test message from Sparrow SMS settings."
	ok = send_sms(settings.test_mobile_no, message, reference="Sparrow SMS Settings test")
	if ok:
		frappe.msgprint(_("Test SMS sent to {0}.").format(settings.test_mobile_no))
	else:
		frappe.msgprint(_("Send failed — check Error Log for details."), indicator="red")
