# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

"""Gas Dispatch (Quota) — LP Gas sold per customer, per BS month, over the last
twelve complete BS months.

One row per customer, twelve month columns oldest -> newest, so a year's gas
offtake per customer reads across a single line. The window always ends with the
BS month before today's and moves forward when a month ends: on 2083 Ashwin 1 it
is Ashwin 2082 -> Bhadra 2083. The month in progress is left out so every column
(and the quota taken from them) is a full month. The existing Sales Analysis reports
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
from datetime import timedelta

import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate

from rdp_common_app.utils.bs_boundaries import BS_MONTH_NAMES, ad_to_bs, bs_to_ad

# The gas item is named "LP Gas" in every company (NGI-ITEM-00167,
# NGN-ITEM-00150, ...), which is what ties the seven item codes together.
LP_GAS_ITEM_NAME = "LP Gas"

# Number of complete BS months the report covers.
MONTH_COUNT = 12


def execute(filters=None):
	filters = frappe._dict(filters or {})
	months, start_date, end_date = _last_complete_bs_months()

	percentage = flt(filters.get("percentage"))
	columns = get_columns(months, percentage)
	data = _build_rows(filters, months, start_date, end_date, percentage)
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


def _last_complete_bs_months():
	"""(months, start_date, end_date) for the last MONTH_COUNT complete BS months.

	months is a list of (bs_year, bs_month) oldest -> newest. start_date is the
	1st of the oldest month, end_date the day before the current BS month began.
	E.g. on 2083 Ashwin 1 (2026-09-17): Ashwin 2082 -> Bhadra 2083, 2025-09-17 ->
	2026-09-16.

	Resolved here rather than in the filter JS so every caller — desk, API, a
	scheduled export — gets the same window on the same day.
	"""
	today = ad_to_bs(getdate(nowdate()))

	months = []
	year, month = today.year, today.month
	for _i in range(MONTH_COUNT):
		# Step back one BS month; Baishakh (1) steps back to Chaitra (12).
		year, month = (year - 1, 12) if month == 1 else (year, month - 1)
		months.append((year, month))
	months.reverse()

	start_date = bs_to_ad(months[0][0], months[0][1], 1)
	end_date = bs_to_ad(today.year, today.month, 1) - timedelta(days=1)
	return months, start_date, end_date


def _sales_by_customer_and_date(filters, start_date, end_date):
	"""LP Gas quantity summed per (customer, posting_date) over the report window.

	Aggregating in SQL keeps the BS conversion below down to one call per
	distinct date (<= 366) instead of one per invoice line — NGI alone has over
	118,000 LP Gas lines.
	"""
	item_codes = _lp_gas_item_codes()
	if not item_codes:
		return []

	# Sales returns (credit notes) carry negative quantities, so including them
	# nets the return off the month it was posted in.
	conditions = [
		"si.docstatus = 1",
		"sii.item_code IN %(item_codes)s",
		"si.posting_date BETWEEN %(start_date)s AND %(end_date)s",
	]
	values = {
		"item_codes": item_codes,
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

	# STRAIGHT_JOIN pins the invoice table first. Left to itself MariaDB starts
	# from the item side -- nearly every invoice line on the site is LP Gas, so
	# that plan walks ~282,000 lines and looks up each invoice one at a time
	# (~71s measured). Invoice-first lets the company+posting_date index carry
	# the date range (~27s for a fiscal year, both on mysite1).
	return frappe.db.sql(
		"""
		SELECT si.customer, si.customer_name, si.posting_date, SUM(sii.qty) AS qty
		FROM `tabSales Invoice` si
		STRAIGHT_JOIN `tabSales Invoice Item` sii ON sii.parent = si.name
		WHERE {where}
		GROUP BY si.customer, si.customer_name, si.posting_date
		""".format(where=" AND ".join(conditions)),
		values,
		as_dict=True,
	)


def _lp_gas_item_codes():
	"""Item codes named "LP Gas" -- one per company, resolved in its own query.

	Joining tabItem into the main query costs a scan on the unindexed item_name;
	this lookup hits five rows and turns the filter into an indexed item_code IN.
	"""
	codes = frappe.db.get_all("Item", filters={"item_name": LP_GAS_ITEM_NAME}, pluck="name")
	return tuple(codes)


def _build_rows(filters, months, start_date, end_date, percentage=0.0):
	"""One row per customer: quantity per BS month, oldest -> newest, then the
	quota (the highest of those twelve months).

	A percentage adds one more cell: the quota raised (+) or lowered (-) by that
	percentage.
	"""
	month_fieldname_by_date = {}
	rows_by_customer = {}

	for row in _sales_by_customer_and_date(filters, start_date, end_date):
		posting_date = getdate(row.posting_date)
		if posting_date not in month_fieldname_by_date:
			bs = ad_to_bs(posting_date)
			month_fieldname_by_date[posting_date] = _month_fieldname(bs.year, bs.month)
		month_fieldname = month_fieldname_by_date[posting_date]

		customer_row = rows_by_customer.setdefault(
			row.customer,
			{
				"customer": row.customer,
				"customer_name": row.customer_name or "",
				**{_month_fieldname(y, m): 0.0 for y, m in months},
			},
		)
		customer_row[month_fieldname] += flt(row.qty)

	# Quota = the customer's best month of the twelve, the peak the next year's
	# dispatch has to be able to meet. The percentage column raises or lowers
	# that quota.
	for customer_row in rows_by_customer.values():
		customer_row["quota_qty"] = max(
			customer_row[_month_fieldname(y, m)] for y, m in months
		)
		if percentage:
			# Rounded to whole cylinders/kg: the adjusted quota is a dispatch
			# figure someone acts on, not a measured quantity.
			customer_row["adjusted_quota"] = flt(
				customer_row["quota_qty"] * (1 + percentage / 100.0), 0
			)

	return sorted(rows_by_customer.values(), key=lambda r: (r["customer_name"] or "").lower())


def _month_fieldname(bs_year, bs_month):
	return f"month_{bs_year}_{bs_month:02d}"


def get_columns(months, percentage=0.0):
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

	# The window crosses two BS years, so each label carries its year.
	for bs_year, bs_month in months:
		columns.append(
			{
				"label": f"{_(BS_MONTH_NAMES[bs_month])} {bs_year}",
				"fieldname": _month_fieldname(bs_year, bs_month),
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
				"label": _("Quota as per Estimated Supply"),
				"fieldname": "adjusted_quota",
				"fieldtype": "Float",
				"precision": 0,
				"width": 130,
			}
		)

	return columns
