import json

import frappe
from frappe import _
from frappe.utils import add_days, nowdate, flt


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login"
		raise frappe.Redirect

	if "Customer" not in frappe.get_roles(frappe.session.user):
		frappe.throw(_("Only customers can access this page."), frappe.PermissionError)

	# Fetch ALL customers linked to this portal user
	portal_customers = frappe.db.sql("""
		SELECT parent FROM `tabPortal User`
		WHERE user = %s AND parenttype = 'Customer' AND parent IS NOT NULL AND parent != ''
	""", frappe.session.user, as_list=True)
	portal_customers = [r[0] for r in portal_customers]

	company = (
		frappe.defaults.get_user_default("Company")
		or frappe.db.get_single_value("Global Defaults", "default_company")
		or ""
	)

	if portal_customers:
		# Portal user — show dropdown of their linked customers (filtered by company in JS)
		context.customer_list = frappe.db.sql("""
			SELECT name, customer_name, IFNULL(custom_company, '') as company
			FROM `tabCustomer`
			WHERE disabled = 0 AND name IN %(customers)s
			ORDER BY customer_name
		""", {"customers": portal_customers}, as_dict=True)
	else:
		# No portal user — free-text search (filtered by company via search_customers)
		context.customer_list = []

	context.customer = ""
	context.customer_name = ""
	context.company = company
	context.price_list = ""
	context.currency = (
		frappe.db.get_value("Company", company, "default_currency")
		or frappe.db.get_single_value("Global Defaults", "default_currency")
		or ""
	)

	context.number_format = frappe.db.get_default("number_format") or "#,###.##"
	context.today = nowdate()
	context.default_delivery_date = add_days(nowdate(), 7)


@frappe.whitelist()
def search_price_lists(txt, customer=None):
	if customer:
		default_pl = frappe.db.get_value("Customer", customer, "default_price_list")
		if default_pl:
			if not txt or txt.lower() in default_pl.lower():
				pl_name = frappe.db.get_value("Price List", default_pl, "price_list_name") or default_pl
				return [{"name": default_pl, "price_list_name": pl_name}]
			return []

	txt_filter = f"%{txt}%" if txt else "%"
	results = frappe.db.sql("""
		SELECT name, price_list_name
		FROM `tabPrice List`
		WHERE enabled = 1
		AND (name LIKE %(txt)s OR price_list_name LIKE %(txt)s)
		LIMIT 10
	""", {"txt": txt_filter}, as_dict=True)
	return results


@frappe.whitelist()
def search_uoms(item_code, txt):
	priority = []

	if item_code and frappe.db.exists("Item", item_code):
		item_vals = frappe.db.get_value("Item", item_code, ["stock_uom", "sales_uom"], as_dict=True) or {}
		sales_uom = item_vals.get("sales_uom") or ""
		stock_uom = item_vals.get("stock_uom") or ""
		if sales_uom:
			priority.append(sales_uom)
		if stock_uom and stock_uom not in priority:
			priority.append(stock_uom)

	# All global UOMs (filtered by txt if given)
	filters = {"enabled": 1}
	if txt:
		filters["uom_name"] = ["like", f"%{txt}%"]
	global_rows = frappe.get_list(
		"UOM",
		filters=filters,
		fields=["name"],
		limit=50,
		ignore_permissions=True,
	)
	global_uoms = [r.name for r in global_rows]

	if txt:
		priority = [u for u in priority if txt.lower() in u.lower()]

	# Merge: priority first, then global (no duplicates)
	seen = set()
	result = []
	for u in priority + global_uoms:
		if u not in seen:
			result.append(u)
			seen.add(u)

	return result


@frappe.whitelist()
def get_item_uoms(item_code):
	uoms = frappe.get_list(
		"UOM Conversion Detail",
		filters={"parent": item_code},
		fields=["uom"],
		ignore_permissions=True,
	)
	# Always include stock UOM
	stock_uom = frappe.db.get_value("Item", item_code, "stock_uom")
	uom_list = [u.uom for u in uoms]
	if stock_uom and stock_uom not in uom_list:
		uom_list.insert(0, stock_uom)
	return uom_list


@frappe.whitelist()
def search_customers(txt, company=None):
	values = {"txt": f"%{txt}%" if txt else "%"}
	company_condition = ""
	if company:
		company_condition = "AND custom_company = %(company)s"
		values["company"] = company

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
			AND custom_company IS NOT NULL AND custom_company != ''
			{txt_condition}
			ORDER BY custom_company
		""".format(
			txt_condition="AND custom_company LIKE %(txt)s" if txt else ""
		), {
			"customers": portal_customers,
			**({"txt": f"%{txt}%"} if txt else {}),
		}, as_dict=True)
		return rows

	# Non-portal user — show all companies
	all_companies = frappe.get_list(
		"Company", fields=["name", "company_name"], ignore_permissions=True
	)
	if len(all_companies) == 1:
		return all_companies

	filters = {}
	if txt:
		filters["company_name"] = ["like", f"%{txt}%"]
	return frappe.get_list(
		"Company",
		filters=filters,
		fields=["name", "company_name"],
		limit=10,
		ignore_permissions=True,
	)


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
def create_sales_order(customer, company, transaction_date, selling_price_list, currency, items):
	if "Customer" not in frappe.get_roles(frappe.session.user):
		frappe.throw(_("Only customers can place orders."), frappe.PermissionError)

	if not frappe.db.exists("Customer", customer):
		frappe.throw(_("Invalid customer."))

	if isinstance(items, str):
		items = json.loads(items)

	if not items:
		frappe.throw(_("Please add at least one item."))

	for i, item in enumerate(items):
		if not item.get("item_code"):
			frappe.throw(_("Row {0}: Item Code is required.").format(i + 1))
		if not item.get("qty") or float(item.get("qty")) <= 0:
			frappe.throw(_("Row {0}: Quantity must be greater than 0.").format(i + 1))
		if not item.get("delivery_date"):
			frappe.throw(_("Row {0}: Delivery Date is required.").format(i + 1))

	so = frappe.new_doc("Sales Order")
	so.customer = customer
	so.company = company
	so.transaction_date = transaction_date
	so.selling_price_list = selling_price_list
	so.currency = currency
	so.order_type = "Sales"
	so.conversion_rate = 1.0

	price_list_currency = frappe.db.get_value("Price List", selling_price_list, "currency") or currency
	so.price_list_currency = price_list_currency
	so.plc_conversion_rate = 1.0

	for item in items:
		so.append("items", {
			"item_code": item.get("item_code"),
			"item_name": item.get("item_name"),
			"qty": float(item.get("qty") or 1),
			"rate": float(item.get("rate") or 0),
			"uom": item.get("uom"),
			"stock_uom": item.get("uom"),
			"delivery_date": item.get("delivery_date"),
		})

	so.flags.ignore_permissions = True
	so.owner = frappe.session.user
	so.insert()
	so.submit()

	return {"status": "success", "order_id": so.name}
