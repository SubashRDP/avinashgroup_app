# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

"""CBMS Activity Report — the audit trail of every exchange with IRD's CBMS.

One row per CBMS Sync Log entry, in the same format as the Invoice Activity
Report (AD date, BS date, time, user):

  Queued -> the CBMS Bill / Bill Return was created on invoice submit
  Synced -> an HTTP attempt IRD accepted (response code shown in Details)
  Failed -> an HTTP attempt IRD rejected, or an exception during send
  Held   -> a return waiting because its original bill is not Synced yet
"""

import frappe
from frappe import _

from avinashgroup_app.custom_code.CBMS.utils import bs_date_str


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if not frappe.has_permission("CBMS Sync Log", "read"):
		frappe.throw(_("Not permitted to read CBMS Sync Log."), frappe.PermissionError)
	return _columns(), _rows(filters)


def _conditions(filters):
	conditions = []
	if filters.get("company"):
		conditions.append("log.company = %(company)s")
	if filters.get("sales_invoice"):
		conditions.append("log.sales_invoice = %(sales_invoice)s")
	if filters.get("operation"):
		conditions.append("log.operation = %(operation)s")
	if filters.get("from_date"):
		conditions.append("log.creation >= concat(%(from_date)s, ' 00:00:00')")
	if filters.get("to_date"):
		conditions.append("log.creation <= concat(%(to_date)s, ' 23:59:59')")
	return (" and " + " and ".join(conditions)) if conditions else ""


def _rows(filters):
	logs = frappe.db.sql(
		"""
		select
			log.invoice_number,
			log.sales_invoice,
			log.creation,
			log.operation,
			log.owner,
			log.direction,
			log.triggered_from,
			log.response_code,
			log.details
		from `tabCBMS Sync Log` log
		where 1 = 1 {conditions}
		order by log.creation desc
		""".format(conditions=_conditions(filters)),
		filters,
		as_dict=True,
	)

	rows = []
	for log in logs:
		details = log.details or ""
		if log.triggered_from == "Retry":
			details = f"{details} (retry)" if details else _("(retry)")
		rows.append(
			{
				"invoice_number": log.invoice_number or log.sales_invoice,
				"date": log.creation.date(),
				"bs_date": bs_date_str(log.creation.date()),
				"time": log.creation.strftime("%H:%M:%S"),
				"operation": log.operation,
				"username": log.owner,
				"action": _("Sales Return") if log.direction == "Bill Return" else _("Sales"),
				"details": details,
			}
		)
	return rows


def _columns():
	return [
		{"label": _("Invoice Number"), "fieldname": "invoice_number", "fieldtype": "Data", "width": 200},
		{"label": _("Date"), "fieldname": "date", "fieldtype": "Date", "width": 100},
		{"label": _("BS Date"), "fieldname": "bs_date", "fieldtype": "Data", "width": 100},
		{"label": _("Time"), "fieldname": "time", "fieldtype": "Data", "width": 90},
		{"label": _("Operation"), "fieldname": "operation", "fieldtype": "Data", "width": 100},
		{"label": _("Username"), "fieldname": "username", "fieldtype": "Link",
			"options": "User", "width": 150},
		{"label": _("Action"), "fieldname": "action", "fieldtype": "Data", "width": 110},
		{"label": _("Details"), "fieldname": "details", "fieldtype": "Data", "width": 280},
	]
