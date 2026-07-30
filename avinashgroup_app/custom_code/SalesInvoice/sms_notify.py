"""Sales Invoice on_submit: SMS the customer via Sparrow SMS.

Non-negotiable rule, same as CBMS/sales_invoice_hooks.py: nothing here may
ever block or fail a Sales Invoice submission. The HTTP call to Sparrow runs
only after the transaction commits (frappe.db.after_commit), capped at a
short timeout, with a background-queue fallback if the direct attempt fails.

If Sparrow SMS Settings > Test Mobile No is set, every Sales Invoice SMS is
redirected there instead of the real customer number, so the whole pipeline
can be tested without messaging actual customers.
"""

import frappe
import requests
from frappe.core.doctype.sms_settings.sms_settings import create_sms_log
from frappe.utils.password import get_decrypted_password

DEFAULT_SPARROW_SMS_URL = "https://api.sparrowsms.com/v2/sms/"
SEND_TIMEOUT = 5


def _resolve_recipient(doc, settings):
	if settings.test_mobile_no:
		return settings.test_mobile_no

	if doc.get("contact_mobile"):
		return doc.contact_mobile

	return frappe.db.get_value("Customer", doc.customer, "mobile_no")


def send_sms(receiver, message, reference=None):
	"""One direct attempt against Sparrow. Never raises."""
	try:
		settings = frappe.get_cached_doc("Sparrow SMS Settings")
		token = get_decrypted_password("Sparrow SMS Settings", "Sparrow SMS Settings", "token")
		api_url = settings.api_url or DEFAULT_SPARROW_SMS_URL
		response = requests.post(
			api_url,
			data={"token": token, "from": settings.sender_identity, "to": receiver, "text": message},
			timeout=SEND_TIMEOUT,
		)
		ok = response.status_code == 200 and response.json().get("response_code") == 200
	except Exception:
		frappe.log_error(
			title=f"Sparrow SMS: send failed for {reference}",
			message=frappe.get_traceback(),
		)
		return False

	create_sms_log(
		{"message": message.encode("utf-8"), "receiver_list": [receiver]},
		[receiver] if ok else [],
	)
	if not ok:
		frappe.log_error(
			title=f"Sparrow SMS: gateway rejected send for {reference}",
			message=response.text,
		)
	return ok


def _first_send_after_commit(receiver, message, sales_invoice):
	if send_sms(receiver, message, reference=sales_invoice):
		return
	try:
		frappe.enqueue(
			"avinashgroup_app.custom_code.SalesInvoice.sms_notify.send_sms",
			queue="default",
			timeout=60,
			receiver=receiver,
			message=message,
			reference=sales_invoice,
		)
	except Exception:
		frappe.log_error(
			title=f"Sparrow SMS: fallback enqueue failed for {sales_invoice}",
			message=frappe.get_traceback(),
		)


def on_submit(doc, method=None):
	try:
		settings = frappe.get_cached_doc("Sparrow SMS Settings")
		if not settings.enabled or doc.is_return:
			return

		receiver = _resolve_recipient(doc, settings)
		if not receiver:
			frappe.log_error(
				title=f"Sparrow SMS: no mobile number for {doc.name}",
				message=f"Customer {doc.customer} has no contact_mobile or mobile_no.",
			)
			return

		message = frappe.render_template(settings.message_template or "", {"doc": doc})
		if not message.strip():
			return

		frappe.db.after_commit.add(lambda: _first_send_after_commit(receiver, message, doc.name))
	except Exception:
		frappe.log_error(
			title=f"Sparrow SMS: failed to queue send for Sales Invoice {doc.name}",
			message=frappe.get_traceback(),
		)
