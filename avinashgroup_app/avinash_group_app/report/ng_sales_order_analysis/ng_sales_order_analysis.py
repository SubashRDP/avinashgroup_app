# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

"""NG Sales Order Analysis — desk.

The desk counterpart of the customer portal's Sales Order Analysis page
(templates/pages/sales_order_analysis.py). Same figures, same columns, one row
per Sales Order Item; the portal page imports `get_rows` from here so a fix to
the query lands on both at once.

Two deliberate differences from the portal:
  * a Customer column — the portal user is always looking at their own orders,
    staff are looking across many, so without it the rows are ambiguous;
  * raw numbers with real fieldtypes instead of the portal's pre-formatted
    strings, so desk sorting, the total row and the Excel export work.
"""

import json

import frappe
from frappe import _

# The Status column reports the Sales Order's *billing* status, not its workflow
# status — this is a billing-oriented report, so "Partly Billed" says more than
# "To Deliver and Bill". Options are Sales Order.billing_status verbatim.
SO_STATUSES = ["Not Billed", "Partly Billed", "Fully Billed", "Closed"]


def _as_list(value):
	"""Normalize a MultiSelectList/Link filter value (list, JSON string, or single) to a list."""
	if not value:
		return []
	if isinstance(value, str):
		value = value.strip()
		if value.startswith("["):
			try:
				value = json.loads(value)
			except Exception:
				return [value]
		else:
			return [value]
	if isinstance(value, (list, tuple, set)):
		return [v for v in value if v]
	return [value]


def get_rows(companies, customers, sales_orders, statuses, from_date, to_date):
	"""One row per Sales Order Item.

	`billed_qty` is summed from submitted Sales Invoice Items pointing back at the
	Sales Order Item, which is why the join is grouped by `soi.name`.

	Shared with the customer portal page — keep it free of anything that reads
	frappe.session, so both callers can scope it their own way.
	"""
	values = {
		"companies": tuple(companies),
		"from_date": from_date,
		"to_date": to_date,
	}
	conditions = ""

	if customers:
		conditions += " AND so.customer IN %(customers)s"
		values["customers"] = tuple(customers)
	if sales_orders:
		conditions += " AND so.name IN %(sales_orders)s"
		values["sales_orders"] = tuple(sales_orders)
	if statuses:
		conditions += " AND so.billing_status IN %(statuses)s"
		values["statuses"] = tuple(statuses)

	# custom_miti is a Custom Field and is not present on every site. Selecting it
	# blindly makes the whole report 500 where it is missing, so fall back to NULL
	# and let _miti() derive the BS date from transaction_date instead.
	miti_select = "so.custom_miti" if frappe.db.has_column("Sales Order", "custom_miti") else "NULL"

	return frappe.db.sql(
		f"""
		SELECT
			so.transaction_date AS date,
			{miti_select} AS custom_miti,
			so.name AS sales_order,
			so.billing_status AS status,
			so.customer,
			so.customer_name,
			soi.item_code,
			soi.item_name,
			IF(
				so.status IN ('Completed', 'To Bill'),
				0,
				GREATEST(IFNULL(DATEDIFF(CURRENT_DATE, soi.delivery_date), 0), 0)
			) AS delay,
			soi.qty,
			IFNULL(SUM(sii.qty), 0) AS billed_qty,
			soi.base_amount AS amount,
			(soi.billed_amt * IFNULL(so.conversion_rate, 1)) AS billed_amount,
			(soi.base_amount - (soi.billed_amt * IFNULL(so.conversion_rate, 1))) AS pending_amount
		FROM `tabSales Order` so
		INNER JOIN `tabSales Order Item` soi
			ON soi.parent = so.name
		LEFT JOIN `tabSales Invoice Item` sii
			ON sii.so_detail = soi.name AND sii.docstatus = 1
		WHERE so.docstatus = 1
		  AND so.status NOT IN ('Stopped', 'On Hold')
		  AND so.transaction_date BETWEEN %(from_date)s AND %(to_date)s
		  AND so.company IN %(companies)s
		  {conditions}
		GROUP BY soi.name
		ORDER BY so.transaction_date ASC, so.name ASC, soi.idx ASC
		""",
		values,
		as_dict=True,
	)


def _miti(custom_miti, date):
	"""The Miti shown in the first column.

	`Sales Order.custom_miti` is the field of record — a Data field already
	holding the BS date as a string, so it is printed exactly as entered. It is
	not populated on every order, so one without a stored miti falls back to
	converting its AD transaction_date.
	"""
	if custom_miti:
		return str(custom_miti).strip()
	if not date:
		return ""
	try:
		from avinashgroup_app.custom_code.CBMS.utils import bs_date_str

		return bs_date_str(date) or ""
	except Exception:
		return ""


def get_columns():
	return [
		{"fieldname": "miti", "label": _("Miti"), "fieldtype": "Data", "width": 100},
		{"fieldname": "date", "label": _("Date"), "fieldtype": "Date", "width": 100},
		{
			"fieldname": "sales_order",
			"label": _("Order No."),
			"fieldtype": "Link",
			"options": "Sales Order",
			"width": 160,
		},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 110},
		# The customer's name, not their ID — "NGI-CUS-00001" means nothing to the
		# person reading the report. Data rather than Link for that reason: a Link
		# column always renders the docname.
		{"fieldname": "customer_name", "label": _("Customer"), "fieldtype": "Data", "width": 200},
		{"fieldname": "item_name", "label": _("Item Name"), "fieldtype": "Data", "width": 200},
		{"fieldname": "qty", "label": _("Qty"), "fieldtype": "Float", "width": 100},
		{"fieldname": "billed_qty", "label": _("Billed Qty"), "fieldtype": "Float", "width": 110},
		{"fieldname": "qty_to_bill", "label": _("Qty to Bill"), "fieldtype": "Float", "width": 110},
		{"fieldname": "amount", "label": _("Amount"), "fieldtype": "Currency", "width": 130},
		{
			"fieldname": "billed_amount",
			"label": _("Billed Amount"),
			"fieldtype": "Currency",
			"width": 130,
		},
		{
			"fieldname": "pending_amount",
			"label": _("Pending Amount"),
			"fieldtype": "Currency",
			"width": 130,
		},
		{"fieldname": "delay", "label": _("Delay (in Days)"), "fieldtype": "Int", "width": 120},
	]


def execute(filters=None):
	filters = frappe._dict(filters or {})

	companies = _as_list(filters.company)
	if not companies:
		frappe.throw(_("Please select at least one Company."))

	from_date, to_date = filters.from_date, filters.to_date
	if not (from_date and to_date):
		frappe.throw(_("From Date and To Date are required."))
	if frappe.utils.getdate(to_date) < frappe.utils.getdate(from_date):
		frappe.throw(_("To Date cannot be before From Date."))

	raw = get_rows(
		companies,
		_as_list(filters.customer),
		_as_list(filters.sales_order),
		_as_list(filters.status),
		from_date,
		to_date,
	)

	data = []
	for d in raw:
		data.append(
			{
				"miti": _miti(d.custom_miti, d.date),
				"date": d.date,
				"sales_order": d.sales_order,
				"status": d.status,
				"customer_name": d.customer_name or d.customer,
				"item_name": d.item_name or d.item_code,
				"qty": frappe.utils.flt(d.qty),
				"billed_qty": frappe.utils.flt(d.billed_qty),
				"qty_to_bill": frappe.utils.flt(d.qty) - frappe.utils.flt(d.billed_qty),
				"amount": frappe.utils.flt(d.amount),
				"billed_amount": frappe.utils.flt(d.billed_amount),
				"pending_amount": frappe.utils.flt(d.pending_amount),
				"delay": int(frappe.utils.flt(d.delay)),
			}
		)

	return get_columns(), data


# ── Filter options ──────────────────────────────────────────────────────────
# Company-scoped, so a user picking a company never sees another company's
# customers or orders in the dropdown.


@frappe.whitelist()
def get_company_customers(company=None, txt=None):
	"""Customer options scoped to the selected company via the customer's custom_company."""
	company = _as_list(company)
	like = f"%{(txt or '').strip()}%"
	conditions = ["(cust.name LIKE %(txt)s OR cust.customer_name LIKE %(txt)s)"]
	values = {"txt": like}
	if company:
		conditions.append("(cust.custom_company IN %(company)s OR COALESCE(cust.custom_company, '') = '')")
		values["company"] = tuple(company)
	where = " AND ".join(conditions)

	return frappe.db.sql(
		f"""
		SELECT cust.name AS value, cust.customer_name AS label, cust.name AS description
		FROM `tabCustomer` cust
		WHERE {where}
		ORDER BY cust.customer_name
		LIMIT 50
		""",
		values,
		as_dict=True,
	)


@frappe.whitelist()
def get_company_sales_orders(company=None, customer=None, from_date=None, to_date=None, txt=None):
	"""Sales Order options, narrowed by whatever else the user has already picked."""
	company = _as_list(company)
	customer = _as_list(customer)
	like = f"%{(txt or '').strip()}%"

	conditions = ["so.docstatus = 1", "so.name LIKE %(txt)s"]
	values = {"txt": like}
	if company:
		conditions.append("so.company IN %(company)s")
		values["company"] = tuple(company)
	if customer:
		conditions.append("so.customer IN %(customer)s")
		values["customer"] = tuple(customer)
	if from_date and to_date:
		conditions.append("so.transaction_date BETWEEN %(from_date)s AND %(to_date)s")
		values["from_date"] = from_date
		values["to_date"] = to_date
	where = " AND ".join(conditions)

	return frappe.db.sql(
		f"""
		SELECT so.name AS value, so.name AS label, so.customer_name AS description
		FROM `tabSales Order` so
		WHERE {where}
		ORDER BY so.transaction_date DESC, so.name DESC
		LIMIT 50
		""",
		values,
		as_dict=True,
	)
