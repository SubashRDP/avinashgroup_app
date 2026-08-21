# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

"""One row per message Sparrow SMS was asked to send.

The core ERPNext `SMS Log` records a date, a message and two counters, and
nothing else — it cannot answer the only questions ever asked about an invoice
SMS: which invoice was it for, which customer, did it actually go, and if not,
why. This doctype is that record.

Written by `sms_dispatch` and by nothing else. Every field is read-only; the
only action on the form is Resend.
"""

import frappe
from frappe import _
from frappe.model.document import Document

# Roles allowed to push a message back at the gateway from the form.
RESEND_ROLES = ("System Manager", "Accounts Manager")

LOG_FIELDS = (
	"status",
	"sent_at",
	"sent_via",
	"reference_doctype",
	"reference_name",
	"company",
	"mobile_no",
	"party_type",
	"party",
	"party_name",
	"raw_mobile_no",
	"recipient_field",
	"message",
	"notification_rule",
	"attempts",
	"message_id",
	"credit_consumed",
	"credit_remaining",
	"error",
	"gateway_response",
)


class SparrowSMSLog(Document):
	pass


def create_log(**fields):
	"""Insert a log row and return its name. Never raises.

	Called from inside the transaction of the document being saved (a Sales
	Invoice submit, normally), so a failure here must not travel: an SMS that
	cannot be logged is still not a reason to fail the invoice.
	"""
	try:
		doc = frappe.new_doc("Sparrow SMS Log")
		# Always stamped, even on a row that never reaches the gateway: the
		# operator's question is "when did this happen", and a blank time
		# column on the failures is exactly the wrong answer.
		doc.sent_at = frappe.utils.now_datetime()
		for key, value in fields.items():
			if key in LOG_FIELDS:
				doc.set(key, value)
		doc.flags.ignore_permissions = True
		# `party` and `reference_name` are Dynamic Links, which Frappe validates
		# on insert. A renamed or deleted customer must not cost us the record of
		# a message that really was sent.
		doc.flags.ignore_links = True
		doc.insert(ignore_permissions=True)
		return doc.name
	except Exception:
		frappe.log_error(
			title="Sparrow SMS: could not write log row",
			message=frappe.get_traceback(),
		)
		return None


def update_log(log, **fields):
	"""Patch a log row in place. Never raises.

	`frappe.db.set_value` rather than a document save: the row is read-only by
	design and this runs after the request's COMMIT, where re-validating a
	document buys nothing.
	"""
	if not log:
		return
	try:
		values = {k: v for k, v in fields.items() if k in LOG_FIELDS}
		if values:
			frappe.db.set_value("Sparrow SMS Log", log, values, update_modified=False)
	except Exception:
		frappe.log_error(
			title=f"Sparrow SMS: could not update log {log}",
			message=frappe.get_traceback(),
		)


@frappe.whitelist()
def resend(log):
	"""Send a logged message again, as a new log row.

	The failed row is left untouched — it is the audit trail, and overwriting it
	would hide that the first attempt ever happened.

	Where the original failed because no number could be resolved, there is
	nothing stored to dial. In that case the number is read off the reference
	document again, so the fix is the obvious one: put the customer's phone
	number in, then press Resend.
	"""
	frappe.only_for(RESEND_ROLES)

	from avinashgroup_app.sparrow_sms.sms_dispatch import send_sms

	doc = frappe.get_doc("Sparrow SMS Log", log)

	if not frappe.db.get_single_value("Sparrow SMS Settings", "enabled"):
		frappe.throw(_("Sparrow SMS is disabled in Sparrow SMS Settings."))

	receiver = doc.mobile_no or doc.raw_mobile_no or _recipient_from_reference(doc)
	if not receiver:
		frappe.throw(
			_("No phone number on this log, and none could be read off {0} either.").format(
				frappe.bold(doc.reference_name or _("the reference document"))
			)
		)

	message = (doc.message or "").strip()
	if not message:
		frappe.throw(_("This log has no message text to resend."))

	ok = send_sms(
		receiver,
		message,
		reference=f"Resend of {doc.name}",
		context={
			"sent_via": "Resend",
			"reference_doctype": doc.reference_doctype,
			"reference_name": doc.reference_name,
			"company": doc.company,
			"party_type": doc.party_type,
			"party": doc.party,
			"party_name": doc.party_name,
			"recipient_field": doc.recipient_field,
			"notification_rule": doc.notification_rule,
		},
	)
	return {"ok": ok, "receiver": receiver}


def _recipient_from_reference(doc):
	"""Re-resolve the recipient off the live reference document.

	Only reachable from Resend, so the cost of loading the document is paid once
	per button press.
	"""
	if not (doc.reference_doctype and doc.reference_name and doc.notification_rule):
		return None
	if not frappe.db.exists(doc.reference_doctype, doc.reference_name):
		return None

	from avinashgroup_app.sparrow_sms.sms_dispatch import _resolve_recipient, _rules_for

	rule_event = frappe.db.get_value("SMS Notification Rule", doc.notification_rule, "event")
	for rule in _rules_for(doc.reference_doctype, rule_event):
		if rule["name"] != doc.notification_rule:
			continue
		return _resolve_recipient(rule, frappe.get_doc(doc.reference_doctype, doc.reference_name))[0]

	return None
