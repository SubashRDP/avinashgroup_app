"""Backend for the Sales Invoice SMS Test page.

Deliberately stateless: nothing here creates or updates a document. The page
shows customers, the operator edits the phone number and message in the browser,
and each row is sent on its own button. An edited number is used for that send
only — the Customer record is never written to.
"""

import frappe
from frappe import _

DEFAULT_MESSAGE_TEMPLATE = "Dear {{ doc.customer_name }}, thank you for your business - {{ company }}."

# The page previews the message the system would send on Sales Invoice submit, so
# it reads that one rule and nothing else.
RULE_DOCTYPE = "Sales Invoice"
RULE_EVENT = "On Submit"

# Sending is deliberately NOT permission-gated. SMS is a secondary action here:
# it must never be the thing that stops someone doing their job, and the desk is
# reachable only by staff who are already logged in. Access is controlled by the
# page's role list alone. Note this means `send_one` will send whatever number
# and text it is given, so anyone who can reach the desk can reach the gateway.


class _Blank(dict):
	"""Mapping whose missing keys render as empty rather than `None`.

	The rule's template is written against a Sales Invoice, so fields like
	`grand_total` do not exist on a Customer. A plain `frappe._dict` returns
	None for those and Jinja prints the literal "None" into the SMS.
	"""

	def __getattr__(self, key):
		return self.get(key, "")

	def __missing__(self, key):
		return ""


def _rule_template():
	"""Message template from the Sales Invoice On Submit rule.

	`enabled` is deliberately not filtered on: switching the rule off should stop
	the automatic sends without blanking this page.
	"""
	template = frappe.db.get_value(
		"SMS Notification Rule",
		{"document_type": RULE_DOCTYPE, "event": RULE_EVENT},
		"message_template",
	)
	return (template or "").strip() or DEFAULT_MESSAGE_TEMPLATE


@frappe.whitelist()
def get_customers(company, customer_group=None, only_with_mobile=0):
	"""Customers for a company, each with the message the rule would produce."""
	frappe.has_permission("Customer", throw=True)

	filters = {"disabled": 0, "custom_company": company}
	if customer_group:
		filters["customer_group"] = customer_group

	# Every field, so the rule's template has as much to bind to as possible.
	customers = frappe.get_all(
		"Customer",
		filters=filters,
		fields=["*"],
		order_by="customer_name asc",
	)

	address_phones = _address_phones([c.name for c in customers])

	template = _rule_template()
	rows = []
	for customer in customers:
		# Customer.mobile_no is empty on almost every record here; the numbers
		# actually live on the linked Address.
		number = (customer.mobile_no or "").strip() or address_phones.get(customer.name, "")

		if int(only_with_mobile or 0) and not number:
			continue

		rows.append(
			{
				"company": company,
				"customer": customer.name,
				"customer_name": customer.customer_name,
				"mobile_no": number,
				"message": _render(template, customer, company),
			}
		)

	return rows


def _render(template, customer, company):
	try:
		return frappe.render_template(template, {"doc": _Blank(customer), "company": company})
	except Exception:
		# One malformed template must not blank out the whole list.
		frappe.log_error(
			title=f"Sales Invoice SMS Test: template failed for {customer.name}",
			message=frappe.get_traceback(),
		)
		return ""


def _address_phones(customer_names):
	"""Phone number off each customer's Address, primary address preferred.

	Address links to Customer through Dynamic Link, so this cannot be expressed
	as a plain join from Customer.
	"""
	if not customer_names:
		return {}

	rows = frappe.db.sql(
		"""
		SELECT dl.link_name AS customer, a.phone
		FROM `tabDynamic Link` dl
		JOIN `tabAddress` a ON a.name = dl.parent
		WHERE dl.parenttype = 'Address'
			AND dl.link_doctype = 'Customer'
			AND dl.link_name IN %(customers)s
			AND a.phone IS NOT NULL AND a.phone != ''
		ORDER BY a.is_primary_address DESC, a.modified DESC
		""",
		{"customers": customer_names},
		as_dict=True,
	)

	phones = {}
	for row in rows:
		# First row per customer wins, so the ORDER BY above decides.
		phones.setdefault(row.customer, (row.phone or "").strip())
	return phones


@frappe.whitelist()
def send_one(customer, mobile_no, message, company=None):
	"""Send a single row. Nothing is persisted except the Sparrow SMS Log."""
	frappe.has_permission("Customer", throw=True)

	from avinashgroup_app.sparrow_sms.sms_dispatch import normalize_mobile, send_sms

	mobile_no = (mobile_no or "").strip()
	if not mobile_no:
		frappe.throw(_("Enter a phone number first."))
	if not (message or "").strip():
		frappe.throw(_("Enter a message first."))

	if not frappe.db.get_single_value("Sparrow SMS Settings", "enabled"):
		frappe.throw(_("Sparrow SMS is disabled in Sparrow SMS Settings."))

	# Send to the number in the row, which is the number the operator just
	# confirmed in the dialog. Test Mobile No is not consulted: honouring it here
	# meant the confirmation named one number and the message went to another.
	# Normalised so the reported receiver is the one send_sms will dial.
	receiver = normalize_mobile(mobile_no)
	if not receiver:
		frappe.throw(_("{0} contains no digits.").format(mobile_no))

	# The typed number, not the normalised one: send_sms normalises again, and
	# the log's Raw Mobile No then shows what the operator actually entered.
	ok = send_sms(
		mobile_no,
		message,
		reference=f"Sales Invoice SMS Test / {customer}",
		context={
			"sent_via": "SMS Test Page",
			"reference_doctype": "Customer",
			"reference_name": customer,
			"company": company,
			"party_name": frappe.db.get_value("Customer", customer, "customer_name"),
			"message": message,
		},
	)
	return {"ok": ok, "receiver": receiver}
