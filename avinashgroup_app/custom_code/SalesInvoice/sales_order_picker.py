"""Sales Invoice > Get Items From > Sales Order: the rows of the picker dialog.

Stock ERPNext's picker lists only the order ID and the customer link, so the
billing clerk cannot tell two open orders of the same customer apart without
opening each one. This query feeds public/js/sales_invoice_so_picker.js, which
shows Sales Order ID, Customer Name, Qty, Order Miti and Remarks instead.

Remarks is custom_remarks (the customer's note from the portal's Place Order
page, patches/sales_order_remarks_field.py); read only where that column exists.

Sales Order has no Miti column on every site (custom_miti exists only where
place_order._set_order_miti found it), so the BS date is worked out here from
transaction_date rather than read from the row.

Deliberately narrow: the filters (company, docstatus, not Closed / On Hold,
per_billed < 99.99, customer, plus any the clerk adds in the dialog) are the
ones ERPNext's own sales_order_btn sends, passed through unchanged. Mapping the
picked orders onto the invoice is still erpnext's make_sales_invoice.
"""

import frappe
from frappe.utils import flt

from avinashgroup_app.custom_code.CBMS.utils import bs_date_str


@frappe.whitelist()
def search_open_sales_orders(doctype, txt, searchfield, start, page_len, filters, as_dict=False, **kwargs):
	"""Called by frappe.desk.search.search_widget (MultiSelectDialog's query).

	Returns dicts with name, customer_name, total_qty, miti and remarks.
	get_list keeps the user's Sales Order read permissions in force.
	"""
	filters = frappe.parse_json(filters) or {}
	or_filters = None
	if txt:
		like = ["like", f"%{txt}%"]
		or_filters = {"name": like, "customer_name": like}

	fields = ["name", "transaction_date", "customer_name", "total_qty"]
	has_remarks = frappe.db.has_column("Sales Order", "custom_remarks")
	if has_remarks:
		fields.append("custom_remarks")

	rows = frappe.get_list(
		"Sales Order",
		filters=filters,
		or_filters=or_filters,
		fields=fields,
		order_by="transaction_date desc, name desc",
		start=start,
		page_length=page_len,
	)
	for r in rows:
		r.miti = bs_date_str(r.transaction_date) if r.transaction_date else ""
		r.total_qty = flt(r.total_qty)
		r.remarks = (r.get("custom_remarks") or "") if has_remarks else ""
	return rows
