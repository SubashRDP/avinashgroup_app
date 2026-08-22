import json

import frappe
from frappe import _
from frappe.utils import add_days, getdate, nowdate, flt


# Place Order sells one product, LP Gas, and the item is per company (custom_company).
# A company that has no LP Gas item does not sell gas at all — Grihalaxmi Metal Industries
# is a cylinder/metal business — so it is kept off this page entirely rather than being
# served someone else's item.
LP_GAS_ITEM_NAME = "LP Gas"


def _lp_gas_companies():
	"""Companies this page serves: the ones that actually have an LP Gas item."""
	rows = frappe.db.sql("""
		SELECT DISTINCT custom_company
		FROM `tabItem`
		WHERE item_name = %(item_name)s
		AND disabled = 0 AND is_sales_item = 1
		AND custom_company IS NOT NULL AND custom_company != ''
		ORDER BY custom_company
	""", {"item_name": LP_GAS_ITEM_NAME}, as_list=True)
	return [r[0] for r in rows]


def _get_lp_gas_item(company):
	"""The LP Gas item belonging to `company`, or None. Never falls back to another
	company's item — that would put the wrong item on the order."""
	if not company:
		return None
	return frappe.db.get_value(
		"Item",
		{
			"item_name": LP_GAS_ITEM_NAME,
			"disabled": 0,
			"is_sales_item": 1,
			"custom_company": company,
		},
		["name", "item_name"],
		as_dict=True,
	)


# Rendered HTML for a website page is cached by path and language only
# (frappe/website/utils.py: cache_html) — not by user. This page is built from
# frappe.session.user, so caching it would serve one customer their neighbour's
# page. Frappe skips the cache when developer_mode is on, which is why this never
# shows up locally.
no_cache = 1


def get_context(context):
	context.no_cache = 1
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login"
		raise frappe.Redirect

	if "Customer" not in frappe.get_roles(frappe.session.user):
		frappe.throw(_("Only customers can access this page."), frappe.PermissionError)

	gas_companies = _lp_gas_companies()

	# Fetch ALL customers linked to this portal user
	portal_customers = frappe.db.sql("""
		SELECT parent FROM `tabPortal User`
		WHERE user = %s AND parenttype = 'Customer' AND parent IS NOT NULL AND parent != ''
	""", frappe.session.user, as_list=True)
	portal_customers = [r[0] for r in portal_customers]

	if portal_customers and gas_companies:
		# Portal user — show dropdown of their linked customers (filtered by company in JS)
		context.customer_list = frappe.db.sql("""
			SELECT name, customer_name, IFNULL(custom_company, '') as company
			FROM `tabCustomer`
			WHERE disabled = 0 AND name IN %(customers)s
			AND custom_company IN %(companies)s
			ORDER BY customer_name
		""", {"customers": portal_customers, "companies": gas_companies}, as_dict=True)
	else:
		# No portal user — free-text search (filtered by company via search_customers)
		context.customer_list = []

	company = (
		frappe.defaults.get_user_default("Company")
		or frappe.db.get_single_value("Global Defaults", "default_company")
		or ""
	)

	# Only a gas-selling company may be preselected. Otherwise prefer one the user can
	# actually order for, and fall back to blank so they pick it themselves.
	if company not in gas_companies:
		linked = [c.company for c in context.customer_list if c.company in gas_companies]
		company = linked[0] if linked else (gas_companies[0] if len(gas_companies) == 1 else "")

	context.company = company
	context.gas_companies = gas_companies
	context.customer = ""
	context.customer_name = ""
	context.price_list = ""
	context.currency = (
		frappe.db.get_value("Company", company, "default_currency")
		or frappe.db.get_single_value("Global Defaults", "default_currency")
		or ""
	)

	context.number_format = frappe.db.get_default("number_format") or "#,###.##"
	context.today = nowdate()
	context.default_delivery_date = add_days(nowdate(), 7)

	# The item is fixed on the form (no item picker) but resolved per company.
	default_item = _get_lp_gas_item(company)
	context.default_item_code = default_item.name if default_item else ""
	context.default_item_name = default_item.item_name if default_item else LP_GAS_ITEM_NAME
	context.default_uoms = get_item_uoms(default_item.name) if default_item else []


@frappe.whitelist()
def get_item_uoms(item_code):
	"""Every UOM the item can be sold in — its conversion rows plus the stock UOM,
	smallest factor first. This is what the UOM dropdown offers."""
	if not item_code:
		return []

	stock_uom = frappe.db.get_value("Item", item_code, "stock_uom")
	rows = frappe.db.sql("""
		SELECT uom, conversion_factor
		FROM `tabUOM Conversion Detail`
		WHERE parenttype = 'Item' AND parent = %(item)s
		ORDER BY conversion_factor
	""", {"item": item_code}, as_dict=True)

	uom_list = []
	for r in rows:
		if r.uom and r.uom not in uom_list:
			uom_list.append(r.uom)
	if stock_uom and stock_uom not in uom_list:
		uom_list.insert(0, stock_uom)
	return uom_list


def _priced_uoms(item_code, price_list):
	"""The sizes this account can actually buy: the item's UOMs that carry a selling
	price on the customer's own price list, smallest first. Offering a size with no
	price is a dead end — the customer picks it and the rate comes back 0.00."""
	if not (item_code and price_list):
		return []
	rows = frappe.db.sql("""
		SELECT ip.uom
		FROM `tabItem Price` ip
		JOIN `tabUOM Conversion Detail` ucd
			ON ucd.parenttype = 'Item' AND ucd.parent = ip.item_code AND ucd.uom = ip.uom
		WHERE ip.item_code = %(item)s AND ip.price_list = %(pl)s AND ip.selling = 1
		AND IFNULL(ip.price_list_rate, 0) > 0
		GROUP BY ip.uom, ucd.conversion_factor
		ORDER BY ucd.conversion_factor
	""", {"item": item_code, "pl": price_list}, as_list=True)
	return [r[0] for r in rows]


@frappe.whitelist()
def get_company_item(company, customer=None):
	"""The LP Gas item and the sizes on offer. Once a customer is known the sizes are
	narrowed to what their price list prices. Empty when the company does not sell
	LP Gas — the page disables itself in that case."""
	item = _get_lp_gas_item(company)
	if not item:
		return {}

	price_list = frappe.db.get_value("Customer", customer, "default_price_list") if customer else None
	return {
		"item_code": item.name,
		"item_name": item.item_name,
		"uoms": _priced_uoms(item.name, price_list) if price_list else get_item_uoms(item.name),
		"price_list": price_list or "",
		"narrowed": bool(price_list),
	}


@frappe.whitelist()
def search_customers(txt, company=None):
	gas_companies = _lp_gas_companies()
	if not gas_companies:
		return []

	values = {"txt": f"%{txt}%" if txt else "%"}
	if company:
		if company not in gas_companies:
			return []
		company_condition = "AND custom_company = %(company)s"
		values["company"] = company
	else:
		company_condition = "AND custom_company IN %(companies)s"
		values["companies"] = gas_companies

	return frappe.db.sql(f"""
		SELECT name, customer_name FROM `tabCustomer`
		WHERE disabled = 0
		{company_condition}
		AND (name LIKE %(txt)s OR customer_name LIKE %(txt)s)
		ORDER BY customer_name
		LIMIT 10
	""", values, as_dict=True)


@frappe.whitelist()
def search_companies(txt, customer=None):
	gas_companies = _lp_gas_companies()
	if not gas_companies:
		return []

	# For portal users, restrict to companies linked via their customers' custom_company
	portal_customers = frappe.db.sql("""
		SELECT parent FROM `tabPortal User`
		WHERE user = %s AND parenttype = 'Customer' AND parent IS NOT NULL AND parent != ''
	""", frappe.session.user, as_list=True)
	portal_customers = [r[0] for r in portal_customers]

	if portal_customers:
		rows = frappe.db.sql("""
			SELECT DISTINCT custom_company AS name
			FROM `tabCustomer`
			WHERE disabled = 0
			AND name IN %(customers)s
			AND custom_company IN %(companies)s
			{txt_condition}
			ORDER BY custom_company
		""".format(
			txt_condition="AND custom_company LIKE %(txt)s" if txt else ""
		), {
			"customers": portal_customers,
			"companies": gas_companies,
			**({"txt": f"%{txt}%"} if txt else {}),
		}, as_dict=True)
		return rows

	# Non-portal user — every company that sells LP Gas
	needle = (txt or "").strip().lower()
	return [
		{"name": c, "company_name": c}
		for c in gas_companies
		if not needle or needle in c.lower()
	][:10]


@frappe.whitelist()
def search_items(txt, company=None):
	txt_filter = f"%{txt}%" if txt else "%"
	values = {"txt": txt_filter}
	company_condition = ""

	if company:
		company_condition = "AND i.custom_company = %(company)s"
		values["company"] = company

	return frappe.db.sql(f"""
		SELECT i.name AS item_code, i.item_name
		FROM `tabItem` i
		WHERE i.disabled = 0 AND i.is_sales_item = 1
		{company_condition}
		AND (i.name LIKE %(txt)s OR i.item_name LIKE %(txt)s)
		LIMIT 10
	""", values, as_dict=True)


@frappe.whitelist()
def get_in_words(amount, currency):
	from frappe.utils import money_in_words
	return money_in_words(flt(amount), currency)


@frappe.whitelist()
def get_customer_defaults(customer, company=None):
	if not customer or not frappe.db.exists("Customer", customer):
		frappe.throw(_("Invalid customer."))

	cust = frappe.db.get_value(
		"Customer",
		customer,
		["default_price_list", "default_currency", "custom_company"],
		as_dict=True,
	)

	# Use customer's linked company if set; otherwise fall back to whatever the caller passed
	customer_company = cust.custom_company or ""
	effective_company = customer_company or company or (
		frappe.defaults.get_user_default("Company")
		or frappe.db.get_single_value("Global Defaults", "default_company")
		or ""
	)

	price_list = cust.default_price_list or ""
	price_list_name = (
		frappe.db.get_value("Price List", price_list, "price_list_name") if price_list else ""
	) or price_list
	currency = (
		cust.default_currency
		or frappe.db.get_value("Company", effective_company, "default_currency")
		or frappe.db.get_single_value("Global Defaults", "default_currency")
		or ""
	)
	return {"price_list": price_list, "price_list_name": price_list_name, "currency": currency, "customer_company": customer_company}


def _price_of(item_code, price_list, uom):
	"""The selling rate for this item at this size, straight from Item Price."""
	rate = frappe.db.get_value(
		"Item Price",
		{"item_code": item_code, "price_list": price_list, "selling": 1, "uom": uom},
		"price_list_rate",
	)
	return flt(rate)


@frappe.whitelist()
def get_item_price(item_code, price_list, uom=None):
	item = frappe.db.get_value("Item", item_code, ["item_name", "stock_uom", "sales_uom"], as_dict=True)
	if not item:
		frappe.throw(_("Item {0} not found.").format(item_code))

	default_uom = item.sales_uom or item.stock_uom or ""
	resolved_uom = uom or default_uom
	rate = 0.0

	if price_list:
		filters = {"item_code": item_code, "price_list": price_list, "selling": 1}
		if resolved_uom:
			filters["uom"] = resolved_uom
		ip = frappe.db.get_value("Item Price", filters, "price_list_rate")
		rate = flt(ip) if ip is not None else 0.0

	return {"item_name": item.item_name, "uom": resolved_uom, "stock_uom": item.stock_uom, "rate": rate}


@frappe.whitelist()
def create_sales_order(customer, company, transaction_date, delivery_date, items):
	if "Customer" not in frappe.get_roles(frappe.session.user):
		frappe.throw(_("Only customers can place orders."), frappe.PermissionError)

	if not frappe.db.exists("Customer", customer):
		frappe.throw(_("Invalid customer."))

	# The item is decided by the company, never by the browser.
	gas_item = _get_lp_gas_item(company)
	if not gas_item:
		frappe.throw(_("{0} is not set up for {1}.").format(LP_GAS_ITEM_NAME, company or _("this company")))

	customer_company = frappe.db.get_value("Customer", customer, "custom_company")
	if customer_company and customer_company != company:
		frappe.throw(_("{0} belongs to {1}, not {2}.").format(customer, customer_company, company))

	# Price list and rates are never taken from the browser: the customer is not
	# shown a price list and must not be able to post one, or a rate of their own.
	selling_price_list = frappe.db.get_value("Customer", customer, "default_price_list")
	if not selling_price_list:
		frappe.throw(_("No price list is set for {0}. Please contact the depot.").format(customer))

	currency = (
		frappe.db.get_value("Customer", customer, "default_currency")
		or frappe.db.get_value("Company", company, "default_currency")
		or frappe.db.get_single_value("Global Defaults", "default_currency")
	)

	if not delivery_date:
		frappe.throw(_("Expected Delivery Date is required."))
	if transaction_date and getdate(delivery_date) < getdate(transaction_date):
		frappe.throw(_("Expected Delivery Date cannot be before the Transaction Date."))

	if isinstance(items, str):
		items = json.loads(items)

	if not items:
		frappe.throw(_("Please add at least one item."))

	# The order is submitted straight away, and submission enforces a delivery
	# warehouse (custom_code/Override/overrides.py::_lenient_warehouse_check). Nothing
	# else on this site supplies one — no Item Default, Item Group Default, Stock
	# Settings or global default — so it comes from the item's selling warehouse.
	# Resolve it here and say so plainly rather than letting the submit fail with
	# "Delivery warehouse required for stock item ...".
	warehouse = frappe.db.get_value("Item", gas_item.name, "custom_selling_warehouse")
	if not warehouse and frappe.db.get_value("Item", gas_item.name, "is_stock_item"):
		frappe.throw(_("{0} has no selling warehouse set up for {1}. Please contact the depot.").format(
			gas_item.item_name, company
		))

	allowed_uoms = get_item_uoms(gas_item.name)

	for i, item in enumerate(items):
		if item.get("item_code") != gas_item.name:
			frappe.throw(_("Row {0}: only {1} can be ordered for {2}.").format(
				i + 1, gas_item.item_name, company
			))
		if not item.get("qty") or float(item.get("qty")) <= 0:
			frappe.throw(_("Row {0}: Quantity must be greater than 0.").format(i + 1))
		if not item.get("uom"):
			frappe.throw(_("Row {0}: UOM is required.").format(i + 1))
		if allowed_uoms and item.get("uom") not in allowed_uoms:
			frappe.throw(_("Row {0}: {1} is not a valid UOM for {2}.").format(
				i + 1, item.get("uom"), gas_item.item_name
			))
		# No price on this account means no order — otherwise the depot receives a
		# submitted order worth nothing.
		if _price_of(gas_item.name, selling_price_list, item.get("uom")) <= 0:
			frappe.throw(_("Row {0}: {1} is not priced for your account. Please contact the depot.").format(
				i + 1, item.get("uom")
			))

	# A double-fired request must not become two orders on the depot's list. If this
	# user just placed the same order, hand back the one that already exists.
	total_qty = sum(float(i.get("qty") or 0) for i in items)
	existing = frappe.db.sql("""
		SELECT name FROM `tabSales Order`
		WHERE customer = %(customer)s AND company = %(company)s
		AND owner = %(user)s AND docstatus = 1
		AND delivery_date = %(delivery_date)s
		AND ROUND(total_qty, 3) = ROUND(%(total_qty)s, 3)
		AND creation >= NOW() - INTERVAL 2 MINUTE
		ORDER BY creation DESC LIMIT 1
	""", {
		"customer": customer, "company": company, "user": frappe.session.user,
		"delivery_date": delivery_date, "total_qty": total_qty,
	}, as_list=True)
	if existing:
		return {"status": "success", "order_id": existing[0][0], "duplicate": 1}

	so = frappe.new_doc("Sales Order")
	so.customer = customer
	so.company = company
	so.transaction_date = transaction_date
	so.delivery_date = delivery_date
	so.selling_price_list = selling_price_list
	so.currency = currency
	so.order_type = "Sales"
	so.conversion_rate = 1.0

	price_list_currency = frappe.db.get_value("Price List", selling_price_list, "currency") or currency
	so.price_list_currency = price_list_currency
	so.plc_conversion_rate = 1.0

	for item in items:
		# stock_uom and conversion_factor are the Item's business — passing the selling UOM
		# as stock_uom pins the factor to 1 and understates stock_qty.
		so.append("items", {
			"item_code": gas_item.name,
			"item_name": gas_item.item_name,
			"qty": float(item.get("qty") or 1),
			"rate": _price_of(gas_item.name, selling_price_list, item.get("uom")),
			"uom": item.get("uom"),
			"warehouse": warehouse,
			"delivery_date": delivery_date,
		})

	so.flags.ignore_permissions = True
	so.owner = frappe.session.user
	so.insert()
	so.submit()

	return {"status": "success", "order_id": so.name}
