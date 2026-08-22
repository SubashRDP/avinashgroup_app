"""Tell a customer when their order moves.

One handler for three documents — Sales Order, Delivery Note, Sales Invoice —
raised on submit and addressed to the Portal Users linked to that document's
customer, so a notification only ever reaches the account it belongs to.

Notification Log is the channel because it does not depend on mail: the bell
fills in whether or not the site's Email Account is working, and on
avinasdemo it currently is not. Frappe will additionally e-mail the entry if
the recipient has notification e-mails switched on, which is a per-user
setting and not our business here.

Nothing in here is allowed to interrupt a submit. A customer's invoice must
post whether or not we managed to tell them about it, so every failure is
logged and swallowed.
"""

import frappe
from frappe.utils import fmt_money, formatdate


# subject, and the sentence under it. {name}, {total} and {date} are filled in.
NOTICES = {
	"Sales Order": (
		"Order confirmed",
		"Your order {name} is confirmed. Expected delivery {date}. Total {total}.",
	),
	"Delivery Note": (
		"Out for delivery",
		"Delivery {name} has been raised against your order. Total {total}.",
	),
	"Sales Invoice": (
		"Invoice raised",
		"Invoice {name} of {total} is now on your account, dated {date}.",
	),
}


# Whoever sells for a company is told about that company's documents only. A
# role cannot express this — roles have no company — so the company a user is
# allowed to work in is read from User Permission, which is where this site
# already records it.
SELLING_ROLES = ("Sales User", "Sales Manager", "Accounts User", "Accounts Manager")

STAFF_NOTICES = {
	"Sales Order": ("New order", "{customer} placed order {name} for {total}, wanted {date}."),
	"Delivery Note": ("Delivery raised", "Delivery {name} raised for {customer}, {total}."),
	"Sales Invoice": ("Invoice submitted", "Invoice {name} of {total} submitted for {customer}."),
}


def _company_staff(company):
	"""Enabled users holding a selling role who are permitted to this company.

	A user with no Company permission at all is unrestricted in Frappe and would
	be notified for every company — which is the behaviour being fixed — so only
	users with an explicit permission for THIS company are included.
	"""
	if not company:
		return []

	permitted = frappe.db.sql_list(
		"""SELECT DISTINCT user FROM `tabUser Permission`
		   WHERE allow = 'Company' AND for_value = %s""",
		company,
	)
	if not permitted:
		return []

	return frappe.db.sql_list(
		"""SELECT DISTINCT r.parent
		   FROM `tabHas Role` r
		   INNER JOIN `tabUser` u ON u.name = r.parent
		   WHERE r.parenttype = 'User' AND u.enabled = 1
		   AND r.role IN %(roles)s AND r.parent IN %(users)s""",
		{"roles": SELLING_ROLES, "users": permitted},
	)


def _portal_users(customer):
	"""Every login linked to this customer. A customer with no portal user gets
	no notification — there is nobody to address it to."""
	if not customer:
		return []
	rows = frappe.db.sql(
		"""
		SELECT DISTINCT user FROM `tabPortal User`
		WHERE parenttype = 'Customer' AND parent = %s
		AND user IS NOT NULL AND user != ''
		""",
		customer,
		as_list=True,
	)
	return [r[0] for r in rows]


def _document_date(doc):
	for field in ("delivery_date", "posting_date", "transaction_date"):
		value = doc.get(field)
		if value:
			return formatdate(value)
	return ""


def notify_customer(doc, method=None):
	"""doc_events hook: <doctype> -> on_submit."""
	try:
		notice = NOTICES.get(doc.doctype)
		if not notice:
			return

		recipients = _portal_users(doc.get("customer"))
		if not recipients:
			return

		subject, body = notice
		message = body.format(
			name=doc.name,
			total=fmt_money(doc.get("grand_total") or 0, currency=doc.get("currency")),
			date=_document_date(doc),
		)

		staff = [u for u in _company_staff(doc.get("company")) if u not in recipients]
		staff_subject, staff_body = STAFF_NOTICES.get(doc.doctype, (None, None))

		for user in recipients:
			frappe.get_doc({
				"doctype": "Notification Log",
				"for_user": user,
				"from_user": frappe.session.user,
				"type": "Alert",
				"document_type": doc.doctype,
				"document_name": doc.name,
				"subject": subject,
				"email_content": f"<p>{frappe.utils.escape_html(message)}</p>",
			}).insert(ignore_permissions=True)

		if not staff_subject:
			return

		staff_message = staff_body.format(
			name=doc.name,
			customer=doc.get("customer_name") or doc.get("customer"),
			total=fmt_money(doc.get("grand_total") or 0, currency=doc.get("currency")),
			date=_document_date(doc),
		)
		for user in staff:
			frappe.get_doc({
				"doctype": "Notification Log",
				"for_user": user,
				"from_user": frappe.session.user,
				"type": "Alert",
				"document_type": doc.doctype,
				"document_name": doc.name,
				"subject": f"{staff_subject} - {doc.get('company')}",
				"email_content": f"<p>{frappe.utils.escape_html(staff_message)}</p>",
			}).insert(ignore_permissions=True)

	except Exception:
		# A notification is never worth failing a submitted document for.
		frappe.log_error(
			title="Customer notification failed",
			message=f"{doc.doctype} {doc.name}\n\n{frappe.get_traceback()}",
		)
