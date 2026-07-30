# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

"""Excel downloads with a company letterhead on top of the table.

Two entry points:
- send_report_xlsx: used by Script Reports (Materialized Report & Return) to
  build the whole workbook, including a totals row for numeric columns.
- export_query: replaces frappe.desk.reportview.export_query via
  override_whitelisted_methods — a Sales Invoice list-view Excel export comes
  out as a fixed VAT REGISTER layout (with the filtered company's letterhead)
  no matter which columns the report view shows; everything else passes
  through unchanged.
"""

import json
from io import BytesIO

import frappe
from frappe import _
from frappe.utils import flt
from frappe.utils.xlsxutils import make_xlsx
from openpyxl import load_workbook
from openpyxl.styles import Alignment, Font


def get_company_header_rows(company):
	"""Letterhead rows pulled from the Company record and its linked Addresses.

	    [company name]                                   <- bolded by make_xlsx (row 1)
	    [Pan No.: <tax_id>]
	    [<address line1, city>, Ph: <phone>, Factory: <factory line1, city>]

	Every line — and every fragment of the address line — is dropped when the
	company has no data for it, so nothing renders as an empty label.
	"""
	if not company:
		return []

	company_doc = frappe.db.get_value(
		"Company", company, ["company_name", "tax_id", "phone_no"], as_dict=True
	)
	if not company_doc:
		return []

	rows = [[company_doc.company_name or company]]

	if company_doc.tax_id:
		rows.append(["Pan No.: {0}".format(company_doc.tax_id)])

	addresses = frappe.db.sql(
		"""
		select a.address_line1, a.city, a.phone, a.address_type, a.address_title
		from `tabAddress` a
		join `tabDynamic Link` dl on dl.parent = a.name and dl.parenttype = 'Address'
		where dl.link_doctype = 'Company' and dl.link_name = %s and a.disabled = 0
		order by a.is_primary_address desc, a.creation asc
		""",
		company,
		as_dict=True,
	)

	def address_text(addr):
		return ", ".join(filter(None, [addr.address_line1, addr.city]))

	def is_factory(addr):
		return "factory" in ((addr.address_type or "") + (addr.address_title or "")).lower()

	main = next((a for a in addresses if not is_factory(a)), None)
	factory = next((a for a in addresses if is_factory(a)), None)

	parts = []
	if main and address_text(main):
		parts.append(address_text(main))

	phone = company_doc.phone_no or (main and main.phone)
	if phone:
		parts.append("Ph: {0}".format(phone))

	if factory and address_text(factory):
		parts.append("Factory: {0}".format(address_text(factory)))

	if parts:
		rows.append([", ".join(parts)])

	return rows


def send_report_xlsx(columns, data, company, title, filename):
	"""Build the workbook and attach it to frappe.response as a file download.

	columns/data are exactly what the report's execute() returned; Check columns
	come out as Excel TRUE/FALSE and Float columns get a summed totals row.
	"""
	rows = get_company_header_rows(company)
	rows.append([title])
	letterhead_row_count = len(rows)
	rows.append([c["label"] for c in columns])

	# execute() pads an empty result with one blank dict so the desk keeps its
	# column headers visible — drop that padding here.
	data = [d for d in data if isinstance(d, dict) and d]

	float_fields = [c["fieldname"] for c in columns if c["fieldtype"] == "Float"]
	totals = {f: 0 for f in float_fields}
	for d in data:
		row = []
		for c in columns:
			value = d.get(c["fieldname"])
			if c["fieldtype"] == "Check":
				value = bool(value)
			row.append(value)
		rows.append(row)
		for f in float_fields:
			totals[f] += flt(d.get(f))

	if data:
		total_row = [
			flt(totals[c["fieldname"]], 2) if c["fieldname"] in totals else "" for c in columns
		]
		total_row[0] = _("Total")
		rows.append(total_row)

	xlsx = make_xlsx(rows, title.title())
	xlsx = _center_letterhead(xlsx, letterhead_row_count, len(columns))
	frappe.response.filename = filename
	frappe.response.filecontent = xlsx.getvalue()
	frappe.response.type = "binary"


SALES_INVOICE_VAT_COLUMNS = [
	{"label": "Transaction Type", "fieldname": "transaction_type", "fieldtype": "Data"},
	{"label": "Date", "fieldname": "date", "fieldtype": "Date"},
	{"label": "BS Date", "fieldname": "bs_date", "fieldtype": "Data"},
	{"label": "Document Number", "fieldname": "document_number", "fieldtype": "Data"},
	{"label": "Customer Name", "fieldname": "customer_name", "fieldtype": "Data"},
	{"label": "Customer PAN", "fieldname": "customer_pan", "fieldtype": "Data"},
	{"label": "Total Qty", "fieldname": "total_qty", "fieldtype": "Float"},
	{"label": "Discount Amount", "fieldname": "discount_amount", "fieldtype": "Float"},
	{"label": "Gross Amount", "fieldname": "gross_amount", "fieldtype": "Float"},
	{"label": "Taxable Amount", "fieldname": "taxable_amount", "fieldtype": "Float"},
	{"label": "Tax Amount", "fieldname": "tax_amount", "fieldtype": "Float"},
	{"label": "Grand Total", "fieldname": "grand_total", "fieldtype": "Float"},
]


@frappe.whitelist()
def export_query():
	"""Sales Invoice list-view Excel exports become a VAT REGISTER file; every
	other doctype/format keeps the stock reportview export."""
	from frappe.desk import reportview

	doctype = frappe.form_dict.get("doctype")
	file_format = frappe.form_dict.get("file_format_type")

	if doctype == "Sales Invoice" and file_format == "Excel":
		_export_sales_invoice_vat_register()
		return

	reportview.export_query()


def _export_sales_invoice_vat_register():
	"""Fixed VAT-register layout: one row per invoice, returns as Credit Memo,
	always the same columns regardless of what the report view shows.

	The list's own filters (company, date, status, ...) are applied as-is —
	except cancelled documents, which are always left out. Exporting selected
	rows only is honoured. Amounts are company-currency; return rows keep their
	negative sign so the totals row stays a true net."""
	if not frappe.permissions.can_export("Sales Invoice"):
		frappe.throw(_("You are not allowed to export Sales Invoice"), frappe.PermissionError)

	if selection := frappe.form_dict.get("selected_items"):
		filters = [["Sales Invoice", "name", "in", json.loads(selection)]]
	else:
		filters = frappe.form_dict.get("filters") or []
		if isinstance(filters, str):
			filters = json.loads(filters)

	if isinstance(filters, dict):
		filters["docstatus"] = ["!=", 2]
	else:
		filters.append(["Sales Invoice", "docstatus", "!=", 2])

	invoices = frappe.get_list(
		"Sales Invoice",
		filters=filters,
		fields=[
			"name",
			"company",
			"is_return",
			"posting_date",
			"custom_invoice_miti",
			"customer_name",
			"tax_id",
			"total_qty",
			"base_discount_amount",
			"base_total",
			"base_net_total",
			"base_total_taxes_and_charges",
			"base_grand_total",
		],
		order_by="posting_date asc, name asc",
		limit_page_length=0,
	)

	# Letterhead company comes from the exported rows themselves — this works
	# for selected-rows exports and for "like" filters alike. Rows spanning
	# more than one company get no letterhead rather than a wrong one.
	companies = {inv.company for inv in invoices}
	company = companies.pop() if len(companies) == 1 else None

	data = [
		{
			"transaction_type": "Credit Memo" if inv.is_return else "Invoice",
			"date": inv.posting_date,
			"bs_date": inv.custom_invoice_miti,
			"document_number": inv.name,
			"customer_name": inv.customer_name,
			"customer_pan": inv.tax_id,
			"total_qty": inv.total_qty,
			"discount_amount": inv.base_discount_amount,
			"gross_amount": inv.base_total,
			"taxable_amount": inv.base_net_total,
			"tax_amount": inv.base_total_taxes_and_charges,
			"grand_total": inv.base_grand_total,
		}
		for inv in invoices
	]

	send_report_xlsx(SALES_INVOICE_VAT_COLUMNS, data, company, "VAT REGISTER", "vat_register.xlsx")


def _center_letterhead(xlsx_file, row_count, table_width):
	"""Merge each letterhead row across the table's columns and center it.
	make_xlsx works on a write-only workbook, which cannot merge cells — so the
	styling is applied by reopening the finished file."""
	wb = load_workbook(xlsx_file)
	ws = wb.active
	for row in range(1, row_count + 1):
		ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=table_width)
		cell = ws.cell(row=row, column=1)
		cell.alignment = Alignment(horizontal="center")
		# Company name (row 1) and the report title (last letterhead row) in bold.
		if row == 1 or row == row_count:
			cell.font = Font(bold=True)
	out = BytesIO()
	wb.save(out)
	return out
