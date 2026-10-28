"""PDC Register — every submitted post-dated cheque in a date range, with totals per status.

Dates filter on the cheque date (when the money is due), not the posting date,
because the question this answers is "what cheques fall in this period".
"""

import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
	filters = frappe._dict(filters or {})
	rows = get_data(filters)
	return columns(), rows, None, None, summary(rows)


def columns():
	return [
		{"fieldname": "name", "label": _("Cheque"), "fieldtype": "Link", "options": "PDC Cheque", "width": 170},
		{"fieldname": "cheque_type", "label": _("Type"), "fieldtype": "Data", "width": 80},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 90},
		{"fieldname": "party_type", "label": _("Party Type"), "fieldtype": "Data", "width": 80, "hidden": 1},
		{"fieldname": "party", "label": _("Party"), "fieldtype": "Dynamic Link", "options": "party_type", "width": 130},
		{"fieldname": "party_name", "label": _("Party Name"), "fieldtype": "Data", "width": 180},
		{"fieldname": "cheque_no", "label": _("Cheque No"), "fieldtype": "Data", "width": 100},
		{"fieldname": "bank_name", "label": _("Bank"), "fieldtype": "Data", "width": 120},
		{"fieldname": "cheque_date", "label": _("Cheque Date"), "fieldtype": "Date", "width": 100},
		{"fieldname": "posting_date", "label": _("Received / Issued"), "fieldtype": "Date", "width": 100},
		{"fieldname": "amount", "label": _("Amount"), "fieldtype": "Currency", "width": 120},
		{"fieldname": "deposit_date", "label": _("Deposited"), "fieldtype": "Date", "width": 100},
		{"fieldname": "clearance_date", "label": _("Cleared"), "fieldtype": "Date", "width": 100},
		{"fieldname": "bounce_date", "label": _("Bounced"), "fieldtype": "Date", "width": 100},
		{"fieldname": "bounce_reason", "label": _("Bounce Reason"), "fieldtype": "Data", "width": 150},
		{"fieldname": "presentation_count", "label": _("Presented"), "fieldtype": "Int", "width": 80},
		{"fieldname": "company", "label": _("Company"), "fieldtype": "Link", "options": "Company", "width": 150},
	]


def get_data(filters):
	conditions = {"docstatus": 1}
	for field in ("company", "cheque_type", "status", "party_type", "party"):
		if filters.get(field):
			conditions[field] = filters[field]
	if filters.get("from_date") and filters.get("to_date"):
		conditions["cheque_date"] = ["between", [filters.from_date, filters.to_date]]
	return frappe.get_all(
		"PDC Cheque",
		filters=conditions,
		fields=[c["fieldname"] for c in columns()],
		order_by="cheque_date asc, name asc",
	)


def summary(rows):
	totals = {}
	for r in rows:
		totals[r.status] = totals.get(r.status, 0) + flt(r.amount)
	indicator = {"Cleared": "Green", "Bounced": "Red", "In Hand": "Orange", "Issued": "Orange", "Deposited": "Blue"}
	return [
		{"label": _(status), "value": value, "datatype": "Currency", "indicator": indicator.get(status, "Grey")}
		for status, value in sorted(totals.items())
	]
