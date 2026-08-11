# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

"""Materialized Return Report — the credit-note side of the IRD sales book.

Laid out like the Materialized Report (see materialized_report.py) so the two
read as one pair: the same column order, the same Yes/No instead of checkboxes,
BS dates with slashes, and the same who/when columns. Where a column names the
document itself it names the credit note — number, date, and the original
invoice it is raised against — and Reason for Return sits with them, since only
a return has one.

Row source is CBMS Bill Return, one row per credit note reported to the IRD.
Print columns come from Sales Invoice Print Log against the return's own Sales
Invoice, collapsed to its earliest sheet, exactly as the sales report does.

The shared formatting helpers are imported from materialized_report rather than
copied: the two annexures must agree on how a fiscal year, a Yes/No and a BS
timestamp are rendered, and one implementation is how that stays true.
"""

import json

import frappe
from frappe import _

from avinashgroup_app.avinash_group_app.report.materialized_report.materialized_report import (
	_yes_no,
	fiscal_year_display,
	fiscal_year_span,
	strip_totals_row,
	totals_row,
)
from avinashgroup_app.custom_code.CBMS.utils import bs_datetime_str
from avinashgroup_app.utils.report_excel import send_report_xlsx


def execute(filters=None):
	filters = frappe._dict(filters or {})
	columns = get_columns()
	data = get_data(filters)
	if data:
		# Every amount column, labelled in the first one — the same last row
		# send_report_xlsx writes, so the table and its export agree.
		float_fields = [c["fieldname"] for c in columns if c["fieldtype"] == "Float"]
		data.append(totals_row(data, float_fields, columns[0]["fieldname"]))
	# With zero rows the desk hides the table entirely ("Nothing to show");
	# a single blank row keeps the column headers visible.
	return columns, data or [{}]


def get_columns():
	def col(label, fieldname, width, fieldtype="Data"):
		return {"label": _(label), "fieldname": fieldname, "fieldtype": fieldtype, "width": width}

	return [
		col("Fiscal Year", "fiscal_year", 100),
		col("Credit Note Number", "credit_note_number", 170),
		col("Credit Note Date", "credit_note_date", 130),
		col("Ref Invoice Number", "ref_invoice_number", 170),
		col("Customer Name", "customer_name", 220),
		col("PAN", "customer_pan", 110),
		col("Amount", "amount", 130, "Float"),
		col("Discount", "discount", 110, "Float"),
		col("Taxable Amount", "taxable_amount", 130, "Float"),
		col("Tax Amount", "tax_amount", 120, "Float"),
		col("Total Amount", "total_amount", 130, "Float"),
		col("Reason for Return", "reason_for_return", 180),
		col("Sync with IRD", "synced_with_ird", 110),
		col("Printed", "printed", 80),
		col("Active", "active", 80),
		col("Printed Time", "printed_time", 180),
		col("Entered By", "entered_by", 150),
		col("Printed By", "printed_by", 150),
		col("Realtime", "realtime", 90),
		col("Sync with IRD Date & Time", "synced_at", 190),
	]


def get_conditions(filters):
	conditions = []

	if filters.company:
		conditions.append("bill.company = %(company)s")
	if filters.fiscal_year:
		# The report has no From/To Date filters — the date window is derived
		# here from the selected fiscal year. The Fiscal Year docname keeps the
		# slash form ("82/83"), so look up its AD start/end span before converting
		# to the dotted form ("82.83") that bills store in the fiscal_year field.
		fy = fiscal_year_span(filters.fiscal_year)
		if fy:
			filters.from_date = fy.year_start_date
			filters.to_date = fy.year_end_date
			conditions.append("bill.credit_note_date >= %(from_date)s")
			conditions.append("bill.credit_note_date <= %(to_date)s")

		filters.fiscal_year = filters.fiscal_year.replace("/", ".")
		conditions.append("bill.fiscal_year = %(fiscal_year)s")
	if filters.sync_status:
		conditions.append("bill.sync_status = %(sync_status)s")

	return (" and " + " and ".join(conditions)) if conditions else ""


def get_data(filters):
	# amount is the credit note total before VAT and total_amount the grand
	# total: CBMS `total_sales` excludes exempt sales (see build_cbms_fields), so
	# adding them back reconstitutes the total, which keeps Amount + Tax = Total
	# on every row.
	#
	# Entered By comes off the return's own created_by, stamped from the credit
	# note's custom_created_by when the return was written
	# (sales_invoice_hooks.build_cbms_fields). The Sales Invoice join serves
	# Active alone — whether the credit note was later cancelled is a fact about
	# the invoice, with no copy on the return.
	#
	# The two print subqueries share one ORDER BY ... LIMIT 1, so both read the
	# SAME Log row — the credit note's earliest sheet.
	rows = frappe.db.sql(
		"""
		select
			bill.fiscal_year,
			bill.credit_note_number,
			bill.credit_note_date_bs,
			bill.ref_invoice_number,
			bill.buyer_name,
			bill.buyer_pan,
			(bill.total_sales + bill.tax_exempted_sales - bill.vat) as amount,
			bill.discount,
			bill.taxable_sales_vat,
			bill.vat,
			(bill.total_sales + bill.tax_exempted_sales) as total_amount,
			bill.reason_for_return,
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
			) as printed_by
		from `tabCBMS Bill Return` bill
		left join `tabSales Invoice` si on si.name = bill.sales_invoice
		where 1 = 1 {conditions}
		order by bill.fiscal_year asc, bill.credit_note_date asc, bill.credit_note_number asc
		""".format(conditions=get_conditions(filters)),
		filters,
		as_dict=True,
	)

	return [_format_row(r) for r in rows]


def _format_row(r):
	return {
		"fiscal_year": fiscal_year_display(r.fiscal_year),
		"credit_note_number": r.credit_note_number,
		# stored as "2083-04-01"; the annexure writes it with slashes
		"credit_note_date": (
			r.credit_note_date_bs.replace("-", "/") if r.credit_note_date_bs else None
		),
		"ref_invoice_number": r.ref_invoice_number,
		"customer_name": r.buyer_name,
		"customer_pan": r.buyer_pan,
		"amount": r.amount,
		"discount": r.discount,
		"taxable_amount": r.taxable_sales_vat,
		"tax_amount": r.vat,
		"total_amount": r.total_amount,
		"reason_for_return": r.reason_for_return,
		"synced_with_ird": _yes_no(r.sync_status == "Synced"),
		"printed": _yes_no(r.printed_time),
		# A return exists only for a submitted credit note, so anything not
		# cancelled is active. One whose invoice has been deleted outright counts
		# as inactive rather than crashing the row.
		"active": _yes_no(r.docstatus is not None and r.docstatus != 2),
		"printed_time": bs_datetime_str(r.printed_time, twelve_hour=True),
		"entered_by": r.entered_by,
		"printed_by": r.printed_by,
		"realtime": _yes_no(r.is_realtime),
		# last_attempt is stamped on EVERY sync attempt, failures included, so it
		# is only a sync time once the return actually reached the IRD. A Failed
		# or Pending return reports no time rather than the moment it last failed.
		"synced_at": bs_datetime_str(r.last_attempt) if r.sync_status == "Synced" else None,
	}


@frappe.whitelist()
def export_xlsx(filters):
	"""Excel download with the company letterhead above the table and a totals
	row below it. Replaces the built-in Export menu — see materialized_return_report.js.

	Deliberately NOT the sales annexure builder: that one reproduces the legacy
	sales export's sheet — its column widths, its Indian digit grouping, its
	totals under three named columns — none of which was measured against a
	credit-note export, because there is no legacy credit-note export.
	"""
	if isinstance(filters, str):
		filters = frappe._dict(json.loads(filters))

	columns, data = execute(filters)
	send_report_xlsx(
		columns,
		strip_totals_row(data),
		filters.get("company"),
		"MATERIALIZED RETURN REPORT",
		"materialized_return_report.xlsx",
	)
