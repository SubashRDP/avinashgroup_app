# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

"""Materialized Report — the IRD "VAT Annexure 7" sales book.

The layout reproduces the annexure the old NGI billing software exported, so the
group can retire that software: 21 columns in its order, BS dates with slashes,
Yes/No instead of checkboxes, and (via export_xlsx) its letterhead block and
Indian-grouped number formatting.

Row source is CBMS Bill — one row per bill actually reported to the IRD. The
print columns come from Sales Invoice Print Log, which holds one row per SHEET,
so several rows per invoice; the query collapses that to the EARLIEST sheet,
reading its timestamp and its printer from the same row (taking them separately
could pair a reprinter's name with the original print's time).

Three columns have no source and are always blank: Payment Method, VAT Refund
Amount and Transaction Id. They are empty in every row of the software's own
export too — placeholders kept so the column layout matches.
"""

import json
import re

import frappe
from frappe import _
from frappe.utils import cint, flt

from avinashgroup_app.custom_code.CBMS.utils import bs_date_str, bs_datetime_str, bs_long_date
from avinashgroup_app.utils.report_excel import ANNEXURE7_TOTAL_FIELDS, send_annexure7_xlsx


def execute(filters=None):
	filters = frappe._dict(filters or {})
	data = get_data(filters)
	if data:
		# The three columns the exported sheet totals, labelled in the same column
		# it labels them in — the table's last row is the sheet's last row.
		data.append(totals_row(data, ANNEXURE7_TOTAL_FIELDS, "customer_pan", label=_("Totals")))
	# With zero rows the desk hides the table entirely ("Nothing to show");
	# a single blank row keeps the column headers visible.
	return get_columns(), data or [{}]


def totals_row(data, fields, label_field, label=None):
	"""Grand-total row to append to a report's data.

	`is_total_row` marks it for two readers: export_xlsx drops it before handing
	the rows to a workbook builder that sums them and writes its own totals row
	(without this the last row would be counted twice), and the desk's Print view
	renders the row's first column as "Total".
	"""
	row = {label_field: label or _("Total"), "is_total_row": 1}
	for field in fields:
		row[field] = flt(sum(flt(d.get(field)) for d in data), 2)
	return row


def strip_totals_row(data):
	"""The rows of `data` that came from the query — no appended totals row."""
	return [d for d in data if not d.get("is_total_row")]


def get_columns():
	def col(label, fieldname, width, fieldtype="Data"):
		return {"label": _(label), "fieldname": fieldname, "fieldtype": fieldtype, "width": width}

	return [
		col("Fiscal Year", "fiscal_year", 100),
		col("Sale Invoice Number", "invoice_number", 170),
		col("Sale Invoice Date", "invoice_date", 130),
		col("Customer Name", "customer_name", 220),
		col("PAN", "customer_pan", 110),
		col("Amount", "amount", 130, "Float"),
		col("Discount", "discount", 110, "Float"),
		col("Taxable Amount", "taxable_amount", 130, "Float"),
		col("Tax Amount", "tax_amount", 120, "Float"),
		col("Total Amount", "total_amount", 130, "Float"),
		col("Sync with IRD", "synced_with_ird", 110),
		col("Printed", "printed", 80),
		col("Active", "active", 80),
		col("Printed Time", "printed_time", 180),
		col("Entered By", "entered_by", 150),
		col("Printed By", "printed_by", 150),
		col("Realtime", "realtime", 90),
		col("Payment Method", "payment_method", 130),
		col("VAT Refund Amount (if any)", "vat_refund_amount", 170),
		col("Transaction Id (if any)", "transaction_id", 170),
		col("Sync with IRD Date & Time", "synced_at", 190),
		# Sheets printed for this invoice, from Sales Invoice Print Count. Not
		# part of the IRD annexure layout — it sits last so the 21 columns before
		# it stay in the order the filed sheets use.
		col("Print Count", "print_count", 110, "Int"),
	]


def get_conditions(filters):
	conditions = []

	scope = company_scope(filters, "CBMS Bill", "Sales Invoice")
	if scope:
		filters.company_scope = scope
		conditions.append("bill.company in %(company_scope)s")
	if filters.fiscal_year:
		# The report has no From/To Date filters — the date window is derived
		# here from the selected fiscal year, whose AD start/end span comes off
		# the Fiscal Year record (named with a slash, "82/83").
		fy = fiscal_year_span(filters.fiscal_year)
		if fy:
			filters.from_date = fy.year_start_date
			filters.to_date = fy.year_end_date
			conditions.append("bill.invoice_date >= %(from_date)s")
			conditions.append("bill.invoice_date <= %(to_date)s")

		filters.update(fiscal_year_forms(filters.fiscal_year))
		conditions.append(FISCAL_YEAR_CONDITION)
	if filters.sync_status:
		conditions.append("bill.sync_status = %(sync_status)s")

	return (" and " + " and ".join(conditions)) if conditions else ""


def company_scope(filters, *applicable_doctypes):
	"""Companies this report run may read, as a tuple for an SQL `in`, or None.

	A Script Report runs raw SQL, so nothing applies User Permissions on our
	behalf the way a list view or `get_list` would. Without this, a user limited
	to one company could pick any other — or clear the filter and read all seven
	at once, export included, since export_xlsx is whitelisted and reachable by
	URL.

	A picked company must fall inside the permitted set, else the run is refused
	rather than quietly emptied, so a user who follows a link or a saved filter
	for another company is told why. A blank filter narrows to the permitted set
	instead of throwing: for an unrestricted user that is None, and the report
	stays group-wide exactly as before.
	"""
	allowed = allowed_companies(*applicable_doctypes)
	picked = filters.get("company")
	if picked:
		if allowed is not None and picked not in allowed:
			frappe.throw(
				_("You do not have access to company {0}.").format(picked),
				frappe.PermissionError,
			)
		return (picked,)
	return tuple(allowed) if allowed else None


def allowed_companies(*applicable_doctypes):
	"""Company names the current user may see, from Company User Permissions.

	None means unrestricted — the Administrator, or a user with no Company user
	permission at all (Frappe's "no user permission == see everything" rule).

	A user permission may be narrowed to one doctype through Applicable For; such
	a row only counts when it names a doctype this report actually reads, which
	is what Frappe itself would do for a query on that table.
	"""
	if frappe.session.user == "Administrator":
		return None
	from frappe.core.doctype.user_permission.user_permission import get_user_permissions

	scopes = set(applicable_doctypes)
	companies = [
		p.get("doc")
		for p in (get_user_permissions().get("Company") or [])
		if p.get("doc") and (not p.get("applicable_for") or p.get("applicable_for") in scopes)
	]
	return companies or None


def fiscal_year_span(fiscal_year):
	"""AD start/end dates of a Fiscal Year record, or None."""
	return frappe.get_cached_value(
		"Fiscal Year",
		fiscal_year,
		["year_start_date", "year_end_date"],
		as_dict=True,
	)


# CBMS records carry the year in one of two shapes, and both are live data.
# Everything written before 1429ad2 reached the site (2026-08-12) holds the
# dotted form the IRD uses, "83.84" — 277,000-odd rows. Everything written
# since holds the Fiscal Year docname itself, "83/84". Matching only one shape
# silently drops the other, which is what hid the newest bills from this report.
#
# Two literals rather than replace() on the column, so the comparison stays
# index-friendly on a table this size.
FISCAL_YEAR_CONDITION = "bill.fiscal_year in (%(fiscal_year_dot)s, %(fiscal_year_slash)s)"


def fiscal_year_forms(fiscal_year):
	"""Both stored spellings of a fiscal year, for FISCAL_YEAR_CONDITION.

	Accepts either shape and does not touch `fiscal_year` itself — callers still
	need the original docname to look the Fiscal Year record up (export_xlsx
	resolves its letterhead dates from the filters after execute() has run).
	"""
	return {
		"fiscal_year_dot": fiscal_year.replace("/", "."),
		"fiscal_year_slash": fiscal_year.replace(".", "/"),
	}


def get_data(filters):
	# amount is the invoice total before VAT and total_amount the grand total:
	# CBMS `total_sales` excludes exempt sales (see build_cbms_fields), so adding
	# them back reconstitutes the total, which keeps Amount + Tax = Total on
	# every row.
	#
	# Entered By comes off the bill's own created_by, stamped from the invoice's
	# owner when the bill was written (sales_invoice_hooks.build_cbms_fields).
	# The report does not go to Sales Invoice, nor to tabUser, to resolve it.
	# The Sales Invoice join that remains serves Active alone: whether the
	# invoice was later cancelled is a fact about the invoice, with no copy on
	# the bill.
	#
	# The two print subqueries share one ORDER BY ... LIMIT 1, so both read the
	# SAME Log row — the invoice's earliest sheet. printed_by falls back through
	# the row's owner for sheets logged before the printed_by field existed.
	rows = frappe.db.sql(
		"""
		select
			bill.fiscal_year,
			bill.invoice_number,
			bill.invoice_date_bs,
			bill.buyer_name,
			bill.buyer_pan,
			(bill.total_sales + bill.tax_exempted_sales - bill.vat) as amount,
			bill.discount,
			bill.taxable_sales_vat,
			bill.vat,
			(bill.total_sales + bill.tax_exempted_sales) as total_amount,
			bill.sync_status,
			bill.is_realtime,
			bill.last_attempt,
			bill.created_by as entered_by,
			si.docstatus,
			(
				select l.creation
				from `tabSales Invoice Print Log` l
				where l.sales_invoice = bill.sales_invoice
				order by l.creation asc, l.copy_number asc
				limit 1
			) as printed_time,
			(
				select coalesce(nullif(l.printed_by, ''), nullif(pu.full_name, ''), l.owner)
				from `tabSales Invoice Print Log` l
				left join `tabUser` pu on pu.name = l.owner
				where l.sales_invoice = bill.sales_invoice
				order by l.creation asc, l.copy_number asc
				limit 1
			) as printed_by,
			pc.print_count
		from `tabCBMS Bill` bill
		left join `tabSales Invoice` si on si.name = bill.sales_invoice
		-- Sales Invoice Print Count holds at most one row per invoice
		-- (sales_invoice is unique, and the doctype autonames from it), so this
		-- join cannot fan the result out. LEFT because a counter only exists once
		-- an invoice has actually been printed.
		left join `tabSales Invoice Print Count` pc on pc.sales_invoice = bill.sales_invoice
		where 1 = 1 {conditions}
		order by bill.fiscal_year asc, bill.invoice_date asc, bill.invoice_number asc
		""".format(conditions=get_conditions(filters)),
		filters,
		as_dict=True,
	)

	return [_format_row(r) for r in rows]


def _format_row(r):
	return {
		"fiscal_year": fiscal_year_display(r.fiscal_year),
		"invoice_number": r.invoice_number,
		# stored as "2083-04-01"; the annexure writes it with slashes
		"invoice_date": r.invoice_date_bs.replace("-", "/") if r.invoice_date_bs else None,
		"customer_name": r.buyer_name,
		"customer_pan": r.buyer_pan,
		"amount": r.amount,
		"discount": r.discount,
		"taxable_amount": r.taxable_sales_vat,
		"tax_amount": r.vat,
		"total_amount": r.total_amount,
		"synced_with_ird": _yes_no(r.sync_status == "Synced"),
		"printed": _yes_no(r.printed_time),
		# A bill exists only for a submitted invoice, so anything not cancelled
		# is active. A bill whose invoice has been deleted outright counts as
		# inactive rather than crashing the row.
		"active": _yes_no(r.docstatus is not None and r.docstatus != 2),
		"printed_time": bs_datetime_str(r.printed_time, twelve_hour=True),
		"entered_by": r.entered_by,
		"printed_by": r.printed_by,
		"realtime": _yes_no(r.is_realtime),
		# No source for these three — left null rather than blank-string so the
		# cell is genuinely empty, as it is in the legacy export.
		"payment_method": None,
		"vat_refund_amount": None,
		"transaction_id": None,
		# last_attempt is stamped on EVERY sync attempt, failures included, so it
		# is only a sync time once the bill actually reached the IRD. A Failed or
		# Pending bill reports no time rather than the moment it last failed.
		"synced_at": bs_datetime_str(r.last_attempt) if r.sync_status == "Synced" else None,
		# 0 rather than null for a never-printed invoice: the Printed column
		# already says No, and a blank here would read as "unknown" instead of
		# "none".
		"print_count": cint(r.print_count),
	}


def _yes_no(value):
	return "Yes" if value else "No"


def fiscal_year_display(fiscal_year):
	"""Bill fiscal year in the short dotted form the records carry: "82.83".

	Bills store the Fiscal Year name with a dot ("82.83"); the Fiscal Year
	record itself is named with a slash ("82/83"), which is what the report's
	filter shows. Both are accepted and normalised to the dot, so the column and
	the filter name the same year in the same shape.

	Anything that is not a two-part two-digit year passes through untouched.

	Earlier versions expanded this to a four-digit span. Up to 2026-08-12 that
	reproduced an off-by-one in the OLD software's Fiscal Year master — from
	79/80 on it printed start+2, so 82.83 read "2082-84" — kept deliberately so
	the report tied out against the Annexure-7 sheets filed with the IRD. That
	expansion is gone; if a four-digit span is ever wanted again, note that the
	filed sheets and the true year disagree for 79/80 onward.
	"""
	if not fiscal_year:
		return ""
	parts = re.split(r"[./-]", fiscal_year)
	if len(parts) == 2 and all(len(p) == 2 and p.isdigit() for p in parts):
		return f"{parts[0]}.{parts[1]}"
	return fiscal_year


@frappe.whitelist()
def export_xlsx(filters):
	"""Excel download in the legacy VAT Annexure 7 layout — company letterhead
	block above the table, a totals row below it. Replaces the built-in Export
	menu; see materialized_report.js."""
	if isinstance(filters, str):
		filters = frappe._dict(json.loads(filters))

	columns, data = execute(filters)
	send_annexure7_xlsx(
		columns,
		strip_totals_row(data),
		filters.get("company"),
		"materialized_report.xlsx",
		**_header_context(filters),
	)


def _header_context(filters):
	"""Fiscal year and date range for the annexure's letterhead block.

	Read straight from the filters rather than from execute()'s copy, which
	derives the same window but does not hand it back.
	"""
	fiscal_year = filters.get("fiscal_year")
	fy = fiscal_year_span(fiscal_year) if fiscal_year else None
	return {
		"fy_display": fiscal_year_display(fiscal_year) if fiscal_year else "",
		"period": (
			"{0} - {1}".format(
				bs_date_str(fy.year_start_date, sep="/"),
				bs_date_str(fy.year_end_date, sep="/"),
			)
			if fy
			else ""
		),
		"date_range": (
			"{0} to {1}".format(bs_long_date(fy.year_start_date), bs_long_date(fy.year_end_date))
			if fy
			else ""
		),
	}
