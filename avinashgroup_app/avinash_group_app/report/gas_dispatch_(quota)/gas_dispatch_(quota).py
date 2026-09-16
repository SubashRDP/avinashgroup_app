# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

"""Gas Dispatch (Quota) — LP Gas sold per customer, per BS month of a fiscal year.

One row per customer, twelve columns Shrawan -> Ashadh, so a year's gas offtake
per customer reads across a single line. The existing Sales Analysis reports
answer "how much in this date range" and cannot show the month-by-month shape
the quota conversation needs.

Quantity is the invoice quantity as entered, summed across every UOM the item
sells in (14.2 KG, 7.1 KG, 5 KG, 50 KG, 450 KG, 1 MT) — no conversion to Kg.

Deliberately narrow:
- Only items named "LP Gas" count. Regulators, cylinders and the rest of the gas
  item group are out.
- Sales returns (credit notes) count against the month they were posted in, not
  the month of the invoice they return.
- Months come from the posting date converted to BS. Sales Invoice carries no BS
  date field of its own.
"""

import json

import frappe
from frappe import _
from frappe.utils import flt, getdate

from rdp_common_app.utils.bs_boundaries import BS_MONTH_NAMES, ad_to_bs

from avinashgroup_app.utils.fiscal_year_utils import get_default_fiscal_year

# The gas item is named "LP Gas" in every company (NGI-ITEM-00167,
# NGN-ITEM-00150, ...), which is what ties the seven item codes together.
LP_GAS_ITEM_NAME = "LP Gas"

# A BS fiscal year runs Shrawan (month 4) -> Ashadh (month 3 of the next year).
FY_MONTH_ORDER = [4, 5, 6, 7, 8, 9, 10, 11, 12, 1, 2, 3]


def execute(filters=None):
	filters = frappe._dict(filters or {})
	start_date, end_date, _fy_name = _fiscal_year_window(filters)

	percentage = flt(filters.get("percentage"))
	columns = get_columns(percentage)
	data = _build_rows(filters, start_date, end_date, percentage)
	return columns, data


def _as_list(value):
	"""Normalize a MultiSelectList filter value (list, JSON string, or single value) to a list."""
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

	rows = frappe.db.sql(
		"""
		SELECT cust.name, cust.customer_name
		FROM `tabCustomer` cust
		WHERE {where}
		ORDER BY cust.customer_name
		LIMIT 50
		""".format(where=" AND ".join(conditions)),
		values,
	)
	# Name first, code second: the dropdown shows `value` as its bold first line,
	# so the customer name has to be the value. _sales_by_customer_and_date
	# matches the filter against both the code and the name for that reason.
	return [{"value": customer_name or name, "description": name} for name, customer_name in rows]


def _fiscal_year_window(filters):
	"""(start_date, end_date, name) of the filter's Fiscal Year.

	The dates are resolved here rather than in the filter JS so every caller —
	desk, API, a scheduled export — gets the same window for a given year.
	Throws if the year has no row, which is the same failure the naming series
	raises when a fiscal year has not been created yet.
	"""
	fy_name = filters.get("fiscal_year") or get_default_fiscal_year()
	if not fy_name:
		frappe.throw(_("Select a Fiscal Year."))

	row = frappe.db.get_value(
		"Fiscal Year", fy_name, ["year_start_date", "year_end_date"], as_dict=True
	)
	if not row:
		frappe.throw(_("Fiscal Year {0} does not exist.").format(fy_name))

	return getdate(row.year_start_date), getdate(row.year_end_date), fy_name


def _sales_by_customer_and_date(filters, start_date, end_date):
	"""LP Gas quantity summed per (customer, posting_date) over the fiscal year.

	Aggregating in SQL keeps the BS conversion below down to one call per
	distinct date (<= 366) instead of one per invoice line — NGI alone has over
	118,000 LP Gas lines.
	"""
	# Sales returns (credit notes) carry negative quantities, so including them
	# nets the return off the month it was posted in.
	conditions = [
		"si.docstatus = 1",
		"item.item_name = %(item_name)s",
		"si.posting_date BETWEEN %(start_date)s AND %(end_date)s",
	]
	values = {
		"item_name": LP_GAS_ITEM_NAME,
		"start_date": start_date,
		"end_date": end_date,
	}

	company = _as_list(filters.get("company"))
	if company:
		conditions.append("si.company IN %(company)s")
		values["company"] = tuple(company)

	customer = _as_list(filters.get("customer"))
	if customer:
		# The filter sends customer names (see get_company_customers), but a code
		# typed or saved from an older run still has to work.
		conditions.append("(si.customer IN %(customer)s OR si.customer_name IN %(customer)s)")
		values["customer"] = tuple(customer)

	return frappe.db.sql(
		"""
		SELECT si.customer, si.customer_name, si.posting_date, SUM(sii.qty) AS qty
		FROM `tabSales Invoice Item` sii
		INNER JOIN `tabSales Invoice` si ON si.name = sii.parent
		INNER JOIN `tabItem` item ON item.name = sii.item_code
		WHERE {where}
		GROUP BY si.customer, si.customer_name, si.posting_date
		""".format(where=" AND ".join(conditions)),
		values,
		as_dict=True,
	)


def _build_rows(filters, start_date, end_date, percentage=0.0):
	"""One row per customer: quantity per BS month, in fiscal-year order, then the
	quota (the highest of those twelve months).

	A percentage adds one more cell: the quota raised (+) or lowered (-) by that
	percentage.
	"""
	bs_month_by_date = {}
	rows_by_customer = {}

	for row in _sales_by_customer_and_date(filters, start_date, end_date):
		posting_date = getdate(row.posting_date)
		if posting_date not in bs_month_by_date:
			bs_month_by_date[posting_date] = ad_to_bs(posting_date).month
		month = bs_month_by_date[posting_date]

		customer_row = rows_by_customer.setdefault(
			row.customer,
			{
				"customer": row.customer,
				"customer_name": row.customer_name or "",
				**{_month_fieldname(m): 0.0 for m in FY_MONTH_ORDER},
			},
		)
		customer_row[_month_fieldname(month)] += flt(row.qty)

	# Quota = the customer's best month of the year, the peak the next year's
	# dispatch has to be able to meet. The percentage column raises or lowers
	# that quota.
	for customer_row in rows_by_customer.values():
		customer_row["quota_qty"] = max(
			customer_row[_month_fieldname(m)] for m in FY_MONTH_ORDER
		)
		if percentage:
			# Rounded to whole cylinders/kg: the adjusted quota is a dispatch
			# figure someone acts on, not a measured quantity.
			customer_row["adjusted_quota"] = flt(
				customer_row["quota_qty"] * (1 + percentage / 100.0), 0
			)

	return sorted(rows_by_customer.values(), key=lambda r: (r["customer_name"] or "").lower())


def _month_fieldname(bs_month):
	return f"month_{bs_month}"


def get_columns(percentage=0.0):
	columns = [
		{
			"label": _("Customer"),
			"fieldname": "customer",
			"fieldtype": "Link",
			"options": "Customer",
			"width": 140,
		},
		{
			"label": _("Customer Name"),
			"fieldname": "customer_name",
			"fieldtype": "Data",
			"width": 220,
		},
	]

	for bs_month in FY_MONTH_ORDER:
		columns.append(
			{
				"label": _(BS_MONTH_NAMES[bs_month]),
				"fieldname": _month_fieldname(bs_month),
				"fieldtype": "Float",
				"precision": 2,
				"width": 90,
			}
		)

	columns.append(
		{
			"label": _("Quota"),
			"fieldname": "quota_qty",
			"fieldtype": "Float",
			"precision": 2,
			"width": 110,
		}
	)

	# The adjusted column is only meaningful once a percentage is given, so an
	# empty filter leaves the report at its plain month-by-month shape. A
	# negative percentage lowers the quota, which is why the sign is kept in
	# the label rather than assumed to be an increase.
	if percentage:
		columns.append(
			{
				"label": _("Estimated Sales"),
				"fieldname": "adjusted_quota",
				"fieldtype": "Float",
				"precision": 0,
				"width": 130,
			}
		)

	return columns
