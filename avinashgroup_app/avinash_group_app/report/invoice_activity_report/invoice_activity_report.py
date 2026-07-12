# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

"""Invoice Activity Report — the IRD audit trail for Sales Invoices.

One row per event in an invoice's life, merged chronologically from four sources:

  Add       -> the invoice was SUBMITTED — the moment it becomes a tax document
               and its IRD number is final. Timestamp and user come from the
               docstatus 0 -> 1 Version; invoices predating change-tracking fall
               back to record creation/owner. Unsubmitted drafts have no Add row.
  Printed   -> a physical print or PDF, one row per copy (Sales Invoice Print Log)
  Modified  -> a tracked post-creation change (Version), skipping submit-time
               recalculations and scheduler status updates
  Deleted   -> a draft was removed (Deleted Document)

There is deliberately no "Cancelled" operation: for IRD an issued invoice is
never cancelled — it is reversed by a credit note, which appears as its own
Add row with Action = Sales Return. Cancellation versions (docstatus -> 2)
are therefore not reported.

Every event shows the AD date, BS date, time and user; Action distinguishes
Sales from Sales Return (credit notes).
"""

import json

import frappe
from frappe import _
from frappe.utils import cstr

from avinashgroup_app.custom_code.CBMS.utils import bs_date_str

# Field changes that are side effects rather than user edits — a Version whose
# parent-level changes are only these is not worth an audit row on its own,
# and they are left out of the Modified details summary.
INCIDENTAL_FIELDS = {
	"docstatus",
	"status",
	"modified",
	"custom_print_count",
	"posting_time",
	"in_words",
	"base_in_words",
	"other_charges_calculation",
}


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if not filters.get("from_date") or not filters.get("to_date"):
		frappe.throw(_("Please select From Date and To Date."))
	if not frappe.has_permission("Sales Invoice", "read"):
		frappe.throw(_("Not permitted to read Sales Invoice."), frappe.PermissionError)

	from_dt = f"{filters.from_date} 00:00:00"
	to_dt = f"{filters.to_date} 23:59:59"
	operation = filters.get("operation") or "All"

	events = []
	if operation in ("All", "Add", "Modified"):
		events += _version_events(filters, from_dt, to_dt, operation)
	if operation in ("All", "Add"):
		already_added = {e["invoice"] for e in events if e["operation"] == "Add"}
		events += _legacy_add_events(filters, from_dt, to_dt, already_added)
	if operation in ("All", "Printed"):
		events += _print_events(filters, from_dt, to_dt)
	if operation in ("All", "Deleted"):
		events += _deleted_events(filters, from_dt, to_dt)

	events = _apply_invoice_context(events, filters)
	events.sort(key=lambda e: e["_ts"], reverse=True)

	return _columns(), [_row(e) for e in events]


def _row(e):
	ts = e["_ts"]
	return {
		"invoice_number": e["invoice"],
		"date": ts.date(),
		"bs_date": bs_date_str(ts.date()),
		"time": ts.strftime("%H:%M:%S"),
		"operation": e["operation"],
		"username": e["user"],
		"action": _("Sales Return") if e.get("is_return") else _("Sales"),
		"details": e.get("details") or "",
	}


def _legacy_add_events(filters, from_dt, to_dt, already_added):
	"""Add rows for submitted invoices that have NO docstatus 0 -> 1 Version
	(created before change-tracking was enabled) — for those, record creation
	is the best available submit moment. Invoices whose submit Version exists
	but falls outside the range are excluded: their Add belongs to that date."""
	fl = {"creation": ["between", [from_dt, to_dt]], "docstatus": ["in", [1, 2]]}
	if filters.get("sales_invoice"):
		fl["name"] = filters.sales_invoice
	if filters.get("company"):
		fl["company"] = filters.company

	candidates = [
		r
		for r in frappe.get_all(
			"Sales Invoice",
			filters=fl,
			fields=["name", "creation", "owner", "company", "is_return"],
		)
		if r.name not in already_added
	]
	if not candidates:
		return []

	has_submit_version = set()
	for v in frappe.get_all(
		"Version",
		filters={
			"ref_doctype": "Sales Invoice",
			"docname": ["in", [c.name for c in candidates]],
			"data": ["like", '%"docstatus"%'],
		},
		fields=["docname", "data"],
	):
		try:
			data = json.loads(v.data or "{}")
		except (ValueError, TypeError):
			continue
		for c in data.get("changed") or []:
			if c and len(c) >= 3 and c[0] == "docstatus" and cstr(c[2]) == "1":
				has_submit_version.add(v.docname)
				break

	return [
		{
			"invoice": r.name,
			"_ts": r.creation,
			"user": r.owner,
			"operation": "Add",
			"company": r.company,
			"is_return": r.is_return,
		}
		for r in candidates
		if r.name not in has_submit_version
	]


def _print_events(filters, from_dt, to_dt):
	fl = {"creation": ["between", [from_dt, to_dt]]}
	if filters.get("sales_invoice"):
		fl["sales_invoice"] = filters.sales_invoice
	if filters.get("company"):
		fl["company"] = filters.company

	return [
		{
			"invoice": r.sales_invoice,
			"_ts": r.creation,
			"user": r.owner,
			"operation": "Printed",
			"company": r.company,
			"details": _copy_title(r.copy_number),
		}
		for r in frappe.get_all(
			"Sales Invoice Print Log",
			filters=fl,
			fields=["sales_invoice", "creation", "owner", "company", "copy_number"],
		)
	]


def _copy_title(n):
	if not n or n <= 1:
		return _("Tax Invoice")
	if n == 2:
		return _("Copy of Original")
	return _("Copy of Original {0}").format(n - 1)


def _version_events(filters, from_dt, to_dt, operation):
	fl = {"ref_doctype": "Sales Invoice", "creation": ["between", [from_dt, to_dt]]}
	if filters.get("sales_invoice"):
		fl["docname"] = filters.sales_invoice

	events = []
	for v in frappe.get_all(
		"Version", filters=fl, fields=["docname", "creation", "owner", "data"]
	):
		try:
			data = json.loads(v.data or "{}")
		except (ValueError, TypeError):
			continue

		changed = [c for c in data.get("changed") or [] if c and len(c) >= 3]
		row_changes = sum(
			len(data.get(key) or []) for key in ("added", "removed", "row_changed")
		)
		docstatus_after = next(
			(cstr(c[2]) for c in changed if c[0] == "docstatus"), None
		)

		if docstatus_after == "2":
			# Cancellation is not an IRD event — reversals happen via credit
			# notes (their own Add rows), so cancel versions are not reported.
			continue
		elif docstatus_after == "1":
			# The submit step IS the Add event — the invoice becomes a tax
			# document here. Recalculated fields and draft edits carried in
			# this version predate the invoice existing for IRD.
			op, details = "Add", ""
		else:
			user_changes = [c for c in changed if c[0] not in INCIDENTAL_FIELDS]
			if not user_changes and not row_changes:
				# A save that only touched derived/system fields — not a user edit.
				continue
			op = "Modified"
			details = _modified_summary(user_changes, row_changes)

		if operation != "All" and op != operation:
			continue

		events.append(
			{
				"invoice": v.docname,
				"_ts": v.creation,
				"user": v.owner,
				"operation": op,
				"details": details,
			}
		)
	return events


def _modified_summary(user_changes, row_changes):
	meta = frappe.get_meta("Sales Invoice")
	parts = []
	for fieldname, _old, _new in user_changes[:5]:
		df = meta.get_field(fieldname)
		parts.append(df.label if df and df.label else fieldname)
	if len(user_changes) > 5:
		parts.append(_("+{0} more").format(len(user_changes) - 5))
	if row_changes:
		parts.append(_("{0} table row change(s)").format(row_changes))
	return ", ".join(parts)


def _deleted_events(filters, from_dt, to_dt):
	fl = {"deleted_doctype": "Sales Invoice", "creation": ["between", [from_dt, to_dt]]}
	if filters.get("sales_invoice"):
		fl["deleted_name"] = filters.sales_invoice

	events = []
	for r in frappe.get_all(
		"Deleted Document",
		filters=fl,
		fields=["deleted_name", "creation", "owner", "data"],
	):
		company = is_return = None
		try:
			doc_data = json.loads(r.data or "{}")
			company = doc_data.get("company")
			is_return = doc_data.get("is_return")
		except (ValueError, TypeError):
			pass
		if filters.get("company") and company != filters.company:
			continue
		events.append(
			{
				"invoice": r.deleted_name,
				"_ts": r.creation,
				"user": r.owner,
				"operation": "Deleted",
				"company": company,
				"is_return": is_return,
				"details": _("Draft deleted"),
			}
		)
	return events


def _apply_invoice_context(events, filters):
	"""Fill company/is_return from the invoice for events whose source table
	doesn't carry them (Version rows), then apply the company filter."""
	need = {
		e["invoice"]
		for e in events
		if e.get("company") is None or e.get("is_return") is None
	}
	info = {}
	if need:
		for r in frappe.get_all(
			"Sales Invoice",
			filters={"name": ["in", list(need)]},
			fields=["name", "company", "is_return"],
		):
			info[r.name] = r

	company = filters.get("company")
	kept = []
	for e in events:
		inv = info.get(e["invoice"])
		if inv:
			if e.get("company") is None:
				e["company"] = inv.company
			if e.get("is_return") is None:
				e["is_return"] = inv.is_return
		if company and e.get("company") != company:
			continue
		kept.append(e)
	return kept


def _columns():
	return [
		{"label": _("Invoice Number"), "fieldname": "invoice_number", "fieldtype": "Link",
			"options": "Sales Invoice", "width": 200},
		{"label": _("Date"), "fieldname": "date", "fieldtype": "Date", "width": 100},
		{"label": _("BS Date"), "fieldname": "bs_date", "fieldtype": "Data", "width": 100},
		{"label": _("Time"), "fieldname": "time", "fieldtype": "Data", "width": 90},
		{"label": _("Operation"), "fieldname": "operation", "fieldtype": "Data", "width": 100},
		{"label": _("Username"), "fieldname": "username", "fieldtype": "Link",
			"options": "User", "width": 150},
		{"label": _("Action"), "fieldname": "action", "fieldtype": "Data", "width": 110},
		{"label": _("Details"), "fieldname": "details", "fieldtype": "Data", "width": 280},
	]
