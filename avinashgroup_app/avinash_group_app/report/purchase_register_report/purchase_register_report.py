# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

import frappe
from frappe import _


def execute(filters=None):
	filters = filters or {}
	columns = get_columns()
	data = get_data(filters)
	if data:
		total = {"date": None, "miti": None, "purchase_type": None, "voucher_no": _("Total"), "supplier_invoice_no": None, "supplier_invoice_date": None, "supplier_invoice_miti": None, "supplier_name": None, "vat_number": None, "bold": 1}
		for col in columns:
			if col.get("fieldtype") in ("Currency", "Float"):
				total[col["fieldname"]] = sum(row.get(col["fieldname"]) or 0 for row in data)
		data.append(total)
	return columns, data


def get_columns():
	return [
		{"fieldname": "date",                  "label": _("Date"),                    "fieldtype": "Date",            "width": 100},
		{"fieldname": "miti",                  "label": _("Miti"),                    "fieldtype": "Data",            "width": 120},
		{"fieldname": "purchase_type",         "label": _("Purchase Type"),           "fieldtype": "Data",            "width": 120},
		{"fieldname": "voucher_no",            "label": _("Voucher No"),              "fieldtype": "Link",            "options": "Purchase Invoice", "width": 170},
		{"fieldname": "supplier_invoice_no",   "label": _("Supplier Invoice No"),     "fieldtype": "Data",            "width": 150},
		{"fieldname": "supplier_invoice_date", "label": _("Supplier Invoice Date"),   "fieldtype": "Date",            "width": 130},
		{"fieldname": "supplier_invoice_miti", "label": _("Supplier Invoice Miti"),   "fieldtype": "Data",            "width": 130},
		{"fieldname": "supplier_name",         "label": _("Supplier Name"),           "fieldtype": "Data",            "width": 180},
		{"fieldname": "vat_number",            "label": _("VAT Number"),              "fieldtype": "Data",            "width": 130},
		{"fieldname": "purchase",              "label": _("Purchase"),                "fieldtype": "Currency",        "width": 130},
		{"fieldname": "tax_free_purchase",     "label": _("Tax Free Purchase"),       "fieldtype": "Currency",        "width": 140},
		{"fieldname": "taxable_purchase",      "label": _("Taxable Purchase"),        "fieldtype": "Currency",        "width": 140},
		{"fieldname": "vat",                   "label": _("VAT"),                     "fieldtype": "Currency",        "width": 110},
		{"fieldname": "taxable_import",        "label": _("Taxable Import"),          "fieldtype": "Currency",        "width": 140},
		{"fieldname": "import_vat",            "label": _("Import VAT"),              "fieldtype": "Currency",        "width": 110},
		{"fieldname": "capitalized_purchase",  "label": _("Capitalized Purchase VAT"),"fieldtype": "Currency",        "width": 170},
		{"fieldname": "capitalized_vat",       "label": _("Capitalized VAT"),         "fieldtype": "Currency",        "width": 120},
		{"fieldname": "total_vat",             "label": _("Total VAT"),               "fieldtype": "Currency",        "width": 110},
		{"fieldname": "qty",                   "label": _("QTY"),                     "fieldtype": "Float",           "width": 80},
	]


def get_data(filters):
	conditions = "pi.docstatus = 1 AND pi.is_return = 0"

	if filters.get("company"):
		placeholders = ", ".join(["'{}'".format(c) for c in filters.get("company")])
		conditions += " AND pi.company IN ({})".format(placeholders)
	if filters.get("from_date"):
		conditions += " AND pi.posting_date >= %(from_date)s"
	if filters.get("to_date"):
		conditions += " AND pi.posting_date <= %(to_date)s"
	if filters.get("supplier"):
		placeholders = ", ".join(["'{}'".format(c) for c in filters.get("supplier")])
		conditions += " AND pi.supplier IN ({})".format(placeholders)
	if filters.get("purchase_type"):
		placeholders = ", ".join(["'{}'".format(c) for c in filters.get("purchase_type")])
		conditions += " AND pi.custom_purchase_type IN ({})".format(placeholders)

	return frappe.db.sql(
		f"""
		SELECT
			pi.posting_date                                                                          AS date,
			pi.custom_nepali_miti                                                                    AS miti,
			pi.custom_purchase_type                                                                  AS purchase_type,
			pi.name                                                                                  AS voucher_no,
			pi.bill_no                                                                               AS supplier_invoice_no,
			pi.bill_date                                                                             AS supplier_invoice_date,
			pi.custom_supplier_invoice_miti                                                          AS supplier_invoice_miti,
			pi.supplier_name                                                                         AS supplier_name,
			s.tax_id                                                                                 AS vat_number,
			pi.custom_total_amount_including_excise                                                  AS purchase,
			SUM(CASE WHEN pii.custom_vat_apply_on = 'VAT 0%%'                                                                          THEN pii.amount ELSE 0 END) AS tax_free_purchase,
			SUM(CASE WHEN pii.custom_vat_apply_on IN ('VAT 13%%','Amount') AND i.is_fixed_asset = 0 AND s.custom_territory = 'Nepal'    THEN pii.amount ELSE 0 END) AS taxable_purchase,
			SUM(CASE WHEN pii.custom_vat_apply_on IN ('VAT 13%%','Amount') AND i.is_fixed_asset = 0 AND s.custom_territory = 'Nepal'    THEN pii.custom_vat_amount ELSE 0 END) AS vat,
			SUM(CASE WHEN pii.custom_vat_apply_on IN ('VAT 13%%','Amount') AND i.is_fixed_asset = 0 AND s.custom_territory != 'Nepal'   THEN pii.amount ELSE 0 END) AS taxable_import,
			SUM(CASE WHEN pii.custom_vat_apply_on IN ('VAT 13%%','Amount') AND i.is_fixed_asset = 0 AND s.custom_territory != 'Nepal'   THEN pii.custom_vat_amount ELSE 0 END) AS import_vat,
			SUM(CASE WHEN pii.custom_vat_apply_on IN ('VAT 13%%','Amount') AND i.is_fixed_asset = 1 AND s.custom_territory = 'Nepal'    THEN pii.amount ELSE 0 END) AS capitalized_purchase,
			SUM(CASE WHEN pii.custom_vat_apply_on IN ('VAT 13%%','Amount') AND i.is_fixed_asset = 1 AND s.custom_territory = 'Nepal'    THEN pii.custom_vat_amount ELSE 0 END) AS capitalized_vat,
			SUM(CASE WHEN pii.custom_vat_apply_on IN ('VAT 13%%','Amount') AND i.is_fixed_asset = 0 AND s.custom_territory = 'Nepal'    THEN pii.custom_vat_amount
			         WHEN pii.custom_vat_apply_on IN ('VAT 13%%','Amount') AND i.is_fixed_asset = 0 AND s.custom_territory != 'Nepal'   THEN pii.custom_vat_amount
			         WHEN pii.custom_vat_apply_on IN ('VAT 13%%','Amount') AND i.is_fixed_asset = 1 AND s.custom_territory = 'Nepal'    THEN pii.custom_vat_amount
			         ELSE 0 END)                                                                      AS total_vat,
			SUM(pii.qty)                                                                             AS qty
		FROM `tabPurchase Invoice` pi
		JOIN `tabPurchase Invoice Item` pii ON pii.parent = pi.name
		JOIN `tabSupplier` s ON s.name = pi.supplier
		JOIN `tabItem` i ON i.name = pii.item_code
		WHERE {conditions}
		GROUP BY pi.name
		ORDER BY pi.posting_date ASC
		""",
		filters,
		as_dict=True,
	)
