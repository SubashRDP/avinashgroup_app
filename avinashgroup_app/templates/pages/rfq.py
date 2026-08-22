import json

import frappe
from frappe import _
from frappe.utils.file_manager import save_file

from erpnext.accounts.party import get_party_account_currency
from erpnext.templates.pages.rfq import get_context as erpnext_get_context


# Rendered HTML for a website page is cached by path and language only
# (frappe/website/utils.py: cache_html) — not by user. This page is built from
# frappe.session.user, so caching it would serve one customer their neighbour's
# page. Frappe skips the cache when developer_mode is on, which is why this never
# shows up locally.
no_cache = 1


def get_context(context):
	context.no_cache = 1
	erpnext_get_context(context)


@frappe.whitelist()
def create_supplier_quotation(doc):
	if isinstance(doc, str):
		doc = json.loads(doc)

	try:
		sq_args = {
			"doctype": "Supplier Quotation",
			"supplier": doc.get("supplier"),
			"terms": doc.get("terms"),
			"company": doc.get("company"),
			"currency": doc.get("currency")
			or get_party_account_currency("Supplier", doc.get("supplier"), doc.get("company")),
			"buying_price_list": doc.get("buying_price_list")
			or frappe.db.get_value("Buying Settings", None, "buying_price_list"),
		}

		for fieldname in ("apply_discount_on", "additional_discount_percentage", "discount_amount"):
			if doc.get(fieldname) is not None:
				sq_args[fieldname] = doc.get(fieldname)

		sq_doc = frappe.get_doc(sq_args)
		_add_items(sq_doc, doc.get("supplier"), doc.get("items") or [])

		sq_doc.flags.ignore_permissions = True
		sq_doc.run_method("set_missing_values")
		sq_doc.run_method("calculate_taxes_and_totals")
		sq_doc.save()
		_attach_uploaded_files_to_supplier_quotation(
			sq_doc.name,
			doc.get("portal_attachment_files") or [],
			doc.get("items") or [],
		)

		frappe.msgprint(_("Supplier Quotation {0} Created").format(sq_doc.name))
		return sq_doc.name
	except Exception:
		return None


def _add_items(sq_doc, supplier, items):
	for data in items:
		if isinstance(data, dict):
			data = frappe._dict(data)

		_append_rfq_item(sq_doc, supplier, data)


def _append_rfq_item(sq_doc, supplier, data):
	args = {}
	item_meta = frappe.get_meta("Supplier Quotation Item")

	for field in (
		"item_code",
		"item_name",
		"description",
		"qty",
		"rate",
		"conversion_factor",
		"warehouse",
		"material_request",
		"material_request_item",
		"stock_qty",
		"uom",
	):
		args[field] = data.get(field)

	if item_meta.has_field("custom_vat_apply_on"):
		args["custom_vat_apply_on"] = data.get("custom_vat_apply_on") or "Percentage (%)"

	if item_meta.has_field("custom_vat_rate"):
		args["custom_vat_rate"] = data.get("custom_vat_rate") or 0

	if item_meta.has_field("custom_vat_amount"):
		args["custom_vat_amount"] = data.get("custom_vat_amount") or 0

	args.update(
		{
			"request_for_quotation_item": data.name,
			"request_for_quotation": data.parent,
			"supplier_part_no": frappe.db.get_value(
				"Item Supplier", {"parent": data.item_code, "supplier": supplier}, "supplier_part_no"
			),
		}
	)

	sq_doc.append("items", args)


@frappe.whitelist()
def upload_portal_item_attachment(file_name, filedata):
	if not file_name or not filedata:
		frappe.throw(_("File name and content are required"))

	if "," in filedata:
		filedata = filedata.split(",", 1)[1]

	file_doc = save_file(
		fname=file_name,
		content=filedata,
		dt=None,
		dn=None,
		decode=True,
		is_private=1,
	)

	return {"file_name": file_doc.name, "file_url": file_doc.file_url}


def _attach_uploaded_files_to_supplier_quotation(sq_name, portal_attachment_files, items):
	file_ids = set()

	for file_id in portal_attachment_files or []:
		if file_id:
			file_ids.add(file_id)

	for row in items:
		if isinstance(row, dict):
			row = frappe._dict(row)

		for file_id in row.get("portal_attachment_files") or []:
			if file_id:
				file_ids.add(file_id)

	for file_id in file_ids:
		if not frappe.db.exists("File", file_id):
			continue

		file_doc = frappe.get_doc("File", file_id)
		if file_doc.owner != frappe.session.user:
			continue

		file_doc.attached_to_doctype = "Supplier Quotation"
		file_doc.attached_to_name = sq_name
		file_doc.attached_to_field = None
		file_doc.flags.ignore_permissions = True
		file_doc.save()
