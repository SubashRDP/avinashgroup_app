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

from avinashgroup_app.custom_code.CBMS.utils import bs_date_str, get_fiscal_year_dates

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
	if not frappe.has_permission("Sales Invoice", "read"):
		frappe.throw(_("Not permitted to read Sales Invoice."), frappe.PermissionError)
	_apply_date_window(filters)

	# Honor Company User Permissions: a user restricted to some companies only
	# ever sees those, and cannot pull another company's data by picking it in
	# the filter. `company_scope` is the list of companies every source query is
	# confined to (None == unrestricted). The report uses frappe.get_all, which
	# bypasses user permissions, so this scope must be applied by hand.
	filters.company_scope = _resolve_company_scope(filters)

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

	events = _apply_invoice_context(events, filters)
	events = _order_events(events)

	return _columns(), [_row(e) for e in events]


def _order_events(events):
	"""Group events by invoice and order each invoice's events oldest -> newest,
	so a print sequence reads Tax Invoice, Invoice, Copy of Original 1, 2, ...
	(the Tax Invoice + Invoice pair shares a timestamp, so the sheet's copy
	number breaks the tie). Invoices are ordered by their most recent activity,
	newest first."""
	from collections import defaultdict

	groups = defaultdict(list)
	for e in events:
		groups[e["invoice"]].append(e)

	ordered = []
	for invoice in sorted(groups, key=lambda inv: max(e["_ts"] for e in groups[inv]), reverse=True):
		ordered.extend(sorted(groups[invoice], key=lambda e: (e["_ts"], e.get("copy") or 0)))
	return ordered


def _apply_date_window(filters):
	"""Resolve the From/To window entirely in the backend — the report has no
	date filters in the UI. The window is fixed to the CURRENT fiscal year (its
	year_start_date .. year_end_date, resolved from today's date on the server);
	a Fiscal Year filter, if picked, overrides with that year's span."""
	fy = (
		get_fiscal_year_dates(filters.fiscal_year)
		if filters.get("fiscal_year")
		else _current_fiscal_year_dates()
	)
	if fy:
		if not filters.get("from_date"):
			filters.from_date = fy["from_date"]
		if not filters.get("to_date"):
			filters.to_date = fy["to_date"]

	# Fallback only if no Fiscal Year record covers today.
	today = frappe.utils.nowdate()
	if not filters.get("to_date"):
		filters.to_date = today
	if not filters.get("from_date"):
		filters.from_date = str(frappe.utils.get_first_day(today))


def _current_fiscal_year_dates():
	"""AD start/end of the fiscal year covering today, resolved on the server."""
	from erpnext.accounts.utils import get_fiscal_year

	try:
		fy = get_fiscal_year(frappe.utils.nowdate(), as_dict=True)
	except Exception:
		return {}
	return {"from_date": str(fy.year_start_date), "to_date": str(fy.year_end_date)}


def _resolve_company_scope(filters):
	"""Companies this report run is confined to.

	Starts from the companies the current user is permitted (Company User
	Permissions); a user with none is unrestricted. A picked company must fall
	within that set, else it is rejected — no leaking another company's data.
	Returns a list of company names, or None when unrestricted.
	"""
	allowed = _allowed_companies()
	picked = filters.get("company")
	if not picked:
		# The filter is reqd in the JS, so this only fires for a call that
		# bypasses the form — the API, a Prepared Report, a script. Without it an
		# unrestricted user gets every company's activity blended into one list,
		# which reads as a bug rather than as "no filter applied".
		frappe.throw(_("Select a Company."), frappe.MandatoryError)
	if picked:
		if allowed is not None and picked not in allowed:
			frappe.throw(
				_("You do not have access to company {0}.").format(picked),
				frappe.PermissionError,
			)
		return [picked]
	return allowed


def _allowed_companies():
	"""Company names the current user may see, from Company User Permissions.

	None means unrestricted — the Administrator, or a user with no Company user
	permission (Frappe's "no user permission == see everything" rule).
	"""
	if frappe.session.user == "Administrator":
		return None
	from frappe.core.doctype.user_permission.user_permission import get_user_permissions

	perms = get_user_permissions().get("Company") or []
	companies = [
		p.get("doc")
		for p in perms
		if p.get("doc")
		and (not p.get("applicable_for") or p.get("applicable_for") == "Sales Invoice")
	]
	return companies or None


def _apply_company_scope(fl, filters):
	"""Add the company IN-filter for the resolved scope, if any."""
	scope = filters.get("company_scope")
	if scope:
		fl["company"] = ["in", scope]
	return fl


def _row(e):
	ts = e["_ts"]
	# The Add event is dated by the invoice's posting date (set in
	# _apply_invoice_context) — its IRD date — while the Time stays the actual
	# clock time it happened (posting_time is 00:00:00, so it carries no time).
	# Printed / Modified use their own event timestamp for both date and time.
	day = e.get("_date") or ts.date()
	return {
		"invoice_number": e["invoice"],
		"customer_name": e.get("customer_name") or "",
		"date": day,
		"bs_date": bs_date_str(day),
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
	_apply_company_scope(fl, filters)

	candidates = [
		r
		for r in frappe.get_all(
			"Sales Invoice",
			filters=fl,
			fields=["name", "creation", "owner", "company", "is_return", "customer_name"],
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
			"customer_name": r.customer_name,
		}
		for r in candidates
		if r.name not in has_submit_version
	]


def _print_events(filters, from_dt, to_dt):
	fl = {"creation": ["between", [from_dt, to_dt]]}
	if filters.get("sales_invoice"):
		fl["sales_invoice"] = filters.sales_invoice
	_apply_company_scope(fl, filters)

	rows = frappe.get_all(
		"Sales Invoice Print Log",
		filters=fl,
		fields=[
			"sales_invoice",
			"creation",
			"owner",
			"printed_by",
			"company",
			"customer_name",
			"copy_number",
		],
	)

	# is_return isn't stored on the Print Log — resolve it from the Sales Invoice
	# (one query for all invoices in this batch) so a return's print row shows the
	# "Sales Return" action + details, matching the actual printed sheet.
	inv_names = list({r.sales_invoice for r in rows if r.sales_invoice})
	is_return_map = {
		si.name: si.is_return
		for si in frappe.get_all(
			"Sales Invoice",
			filters={"name": ["in", inv_names]},
			fields=["name", "is_return"],
		)
	} if inv_names else {}

	return [
		{
			"invoice": r.sales_invoice,
			"_ts": r.creation,
			# printed_by is the display name; owner is the user id. Rows
			# backfilled from the old billing software carry that software's
			# own user name in printed_by and the import runner in owner, so
			# preferring owner here would report every pre-Frappe print as
			# "Administrator".
			"user": r.printed_by or r.owner,
			"operation": "Printed",
			"company": r.company,
			"customer_name": r.customer_name,
			"copy": r.copy_number,
			"is_return": is_return_map.get(r.sales_invoice, 0),
			"details": _copy_title(r.copy_number, is_return_map.get(r.sales_invoice, 0)),
		}
		for r in rows
	]


def _copy_title(n, is_return=False):
	# Sheet titles match the actual print sequence (see invoice_copy_titles in
	# custom_code/SalesInvoice/print_count.py): the first print produces the
	# TAX INVOICE + INVOICE pair (sheets 1 and 2), and every later sheet is a
	# COPY OF ORIGINAL N. A return prints a single "Sales Return" sheet
	# (_titles_for returns ["Sales Return"]), never an invoice copy title.
	# This maps a STORED sheet number to a label, where _titles_for maps a print
	# event to a series — different jobs, so the wording is deliberately
	# duplicated. Keep the two in sync.
	if is_return:
		return _("Sales Return")
	n = n or 1
	if n <= 1:
		return _("Tax Invoice")
	if n == 2:
		return _("Invoice")
	return _("Copy of Original {0}").format(n - 2)


def _version_events(filters, from_dt, to_dt, operation):
	events = []
	for v in _version_rows(filters, from_dt, to_dt):
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


def _version_rows(filters, from_dt, to_dt):
	"""Sales Invoice Version rows in range.

	Unrestricted: every version in range (company is filled later). Scoped: join
	to Sales Invoice and keep only the permitted companies' versions — this both
	confines the data AND cuts the rows the report has to JSON-parse to just the
	user's companies, instead of scanning every company's versions and dropping
	them afterwards. A version whose invoice was deleted has no join match; under
	a scope those were already unreportable (company unknown), so parity holds.
	"""
	scope = filters.get("company_scope")
	if not scope:
		fl = {"ref_doctype": "Sales Invoice", "creation": ["between", [from_dt, to_dt]]}
		if filters.get("sales_invoice"):
			fl["docname"] = filters.sales_invoice
		return frappe.get_all(
			"Version", filters=fl, fields=["docname", "creation", "owner", "data"]
		)

	conditions = ""
	params = {"from_dt": from_dt, "to_dt": to_dt, "scope": tuple(scope)}
	if filters.get("sales_invoice"):
		conditions = "AND v.docname = %(sales_invoice)s"
		params["sales_invoice"] = filters.sales_invoice
	return frappe.db.sql(
		f"""
		SELECT v.docname, v.creation, v.owner, v.data
		FROM `tabVersion` v
		JOIN `tabSales Invoice` si ON si.name = v.docname
		WHERE v.ref_doctype = 'Sales Invoice'
		  AND v.creation BETWEEN %(from_dt)s AND %(to_dt)s
		  AND si.company IN %(scope)s
		  {conditions}
		""",
		params,
		as_dict=True,
	)


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


def _cbms_cutoffs(companies):
	"""Send From Date per company, from its enabled CBMS Config (enable_from_date).
	A company with no enabled config, or one without a date, has no cutoff — all
	its invoices show. Returns {company: date}."""
	if not companies:
		return {}
	cutoffs = {}
	for c in frappe.get_all(
		"CBMS Config",
		filters={"company": ["in", list(companies)], "enable_cbms": 1},
		fields=["company", "enable_from_date"],
	):
		if c.enable_from_date:
			cutoffs[c.company] = frappe.utils.getdate(c.enable_from_date)
	return cutoffs


def _apply_invoice_context(events, filters):
	"""Fill invoice context, date the Add event by the invoice's posting date,
	and keep only issued invoices inside the CBMS e-billing period.

	Kept only when the invoice: still exists AND is submitted (docstatus 1) —
	Version/Print Log rows outlive drafts, cancelled and deleted invoices, all of
	which are dropped; is within the company scope (applied in the lookup query);
	and is posted ON OR AFTER its company's CBMS Send From Date
	(CBMS Config.enable_from_date), so invoices predating e-billing never appear.

	The Add event is re-dated to the invoice's posting_date (its IRD date) rather
	than the submit/creation timestamp; its Time keeps the real clock time.
	Printed / Modified are left on their own event timestamp.

	The Add event's user AND clock time are re-read from the invoice's
	custom_created_by / custom_created_on — the app-wide audit pair naming the
	clerk who entered it and the moment they did. The Version row it was built
	from carries whoever performed the submit and when, which for API-created
	invoices is the API user on every row (Administrator on all 48,837 of
	avinas1's) at import time rather than entry time.

	Modified keeps its own Version owner and timestamp: that IS who edited, and
	when. Printed likewise stays on the Print Log row — neither the Print Log
	nor the CBMS doctypes carry the custom audit pair, and for an event log the
	row's own author is the actor anyway."""
	names = {e["invoice"] for e in events}
	info = {}
	if names:
		fl = {"name": ["in", list(names)], "docstatus": 1}
		_apply_company_scope(fl, filters)
		fields = ["name", "company", "is_return", "customer_name", "posting_date"]
		meta = frappe.get_meta("Sales Invoice")
		fields += [f for f in ("custom_created_by", "custom_created_on") if meta.has_field(f)]
		for r in frappe.get_all("Sales Invoice", filters=fl, fields=fields):
			info[r.name] = r

	cutoffs = _cbms_cutoffs({r.company for r in info.values()})

	kept = []
	for e in events:
		inv = info.get(e["invoice"])
		if not inv:
			# Not an issued tax document — draft, cancelled, or deleted.
			continue
		# CUTOFF: only invoices posted on/after the company's CBMS Send From Date.
		cutoff = cutoffs.get(inv.company)
		if cutoff and frappe.utils.getdate(inv.posting_date) < cutoff:
			continue
		if e.get("company") is None:
			e["company"] = inv.company
		if e.get("is_return") is None:
			e["is_return"] = inv.is_return
		if e.get("customer_name") is None:
			e["customer_name"] = inv.customer_name
		# The Add event is the invoice becoming a tax document — show it on the
		# invoice's posting date, not the submit/creation timestamp.
		if e["operation"] == "Add":
			e["_date"] = inv.posting_date
			e["user"] = inv.get("custom_created_by") or e["user"]
			e["_ts"] = inv.get("custom_created_on") or e["_ts"]
		kept.append(e)
	return kept


def _columns():
	return [
		{"label": _("Invoice Number"), "fieldname": "invoice_number", "fieldtype": "Link",
			"options": "Sales Invoice", "width": 200},
		{"label": _("Customer Name"), "fieldname": "customer_name", "fieldtype": "Data",
			"width": 180},
		{"label": _("Date"), "fieldname": "date", "fieldtype": "Date", "width": 100,
			"align": "center"},
		{"label": _("BS Date"), "fieldname": "bs_date", "fieldtype": "Data", "width": 100,
			"align": "center"},
		{"label": _("Time"), "fieldname": "time", "fieldtype": "Data", "width": 90,
			"align": "center"},
		{"label": _("Operation"), "fieldname": "operation", "fieldtype": "Data", "width": 100,
			"align": "center"},
		# Data, not Link -> User: Printed rows backfilled from the old billing
		# software name a user of THAT software (ASHISH, NDILLI), which has no
		# Frappe User record to link to. Add/Modified rows still show a user id,
		# just not as a clickable link.
		{"label": _("Username"), "fieldname": "username", "fieldtype": "Data",
			"width": 150, "align": "center"},
		{"label": _("Action"), "fieldname": "action", "fieldtype": "Data", "width": 110,
			"align": "center"},
		{"label": _("Details"), "fieldname": "details", "fieldtype": "Data", "width": 280},
	]
