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

	# Try to identify customer from Portal User
	customer = frappe.db.get_value(
		"Portal User",
		{"user": frappe.session.user, "parenttype": "Customer"},
		"parent",
	)

	context.customer = customer or ""
	context.customer_readonly = bool(customer)
	if customer:
		context.customer_name = frappe.db.get_value("Customer", customer, "customer_name") or customer
	else:
		context.customer_name = ""

	company = (
		frappe.defaults.get_user_default("Company")
		or frappe.db.get_single_value("Global Defaults", "default_company")
		or ""
	)
	context.company = company

	if customer:
		cust = frappe.db.get_value(
			"Customer",
			customer,
			["default_price_list", "default_currency"],
			as_dict=True,
		)
		context.price_list = cust.default_price_list or ""
		context.currency = (
			cust.default_currency
			or frappe.db.get_value("Company", company, "default_currency")
			or frappe.db.get_single_value("Global Defaults", "default_currency")
			or ""
		)
	else:
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
	# If customer has a default price list, only show that one
	if customer:
		default_pl = frappe.db.get_value("Customer", customer, "default_price_list")
		if default_pl:
			if not txt or txt.lower() in default_pl.lower():
				return [{"name": default_pl}]
			return []

	filters = {"enabled": 1}
	if txt:
		filters["name"] = ["like", f"%{txt}%"]
	return frappe.get_list(
		"Price List",
		filters=filters,
		fields=["name"],
		limit=10,
		ignore_permissions=True,
	)


@frappe.whitelist()
def search_uoms(item_code, txt):
	uom_list = []

	if item_code and frappe.db.exists("Item", item_code):
		# Item-specific UOMs first
		rows = frappe.get_list(
			"UOM Conversion Detail",
			filters={"parent": item_code},
			fields=["uom"],
			ignore_permissions=True,
		)
		stock_uom = frappe.db.get_value("Item", item_code, "stock_uom")
		uom_list = [u.uom for u in rows]
		if stock_uom and stock_uom not in uom_list:
			uom_list.insert(0, stock_uom)
		if txt:
			uom_list = [u for u in uom_list if txt.lower() in u.lower()]

	if not uom_list:
		# Fall back to global UOM search
		filters = {"enabled": 1}
		if txt:
			filters["uom_name"] = ["like", f"%{txt}%"]
		rows = frappe.get_list(
			"UOM",
			filters=filters,
			fields=["name"],
			limit=10,
			ignore_permissions=True,
		)
		uom_list = [r.name for r in rows]

	return uom_list


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
def search_customers(txt):
	if txt:
		customers = frappe.db.sql("""
			SELECT name, customer_name FROM `tabCustomer`
			WHERE disabled=0
			AND (name LIKE %(txt)s OR customer_name LIKE %(txt)s)
			LIMIT 10
		""", {"txt": f"%{txt}%"}, as_dict=True)
	else:
		customers = frappe.get_list(
			"Customer",
			filters={"disabled": 0},
			fields=["name", "customer_name"],
			limit=10,
			ignore_permissions=True,
		)
	return customers


@frappe.whitelist()
def search_companies(txt, customer=None):
	# If only one company exists, return only that
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
def search_items(txt):
	filters = {"disabled": 0, "is_sales_item": 1}
	if txt:
		filters["item_name"] = ["like", f"%{txt}%"]
	return frappe.get_list(
		"Item",
		filters=filters,
		fields=["item_code", "item_name"],
		limit=10,
		ignore_permissions=True,
	)


@frappe.whitelist()
def get_in_words(amount, currency):
	from frappe.utils import money_in_words
	return money_in_words(flt(amount), currency)


@frappe.whitelist()
def get_customer_defaults(customer):
	if not customer or not frappe.db.exists("Customer", customer):
		frappe.throw(_("Invalid customer."))

	company = (
		frappe.defaults.get_user_default("Company")
		or frappe.db.get_single_value("Global Defaults", "default_company")
		or ""
	)
	cust = frappe.db.get_value(
		"Customer",
		customer,
		["default_price_list", "default_currency"],
		as_dict=True,
	)
	price_list = cust.default_price_list or ""
	currency = (
		cust.default_currency
		or frappe.db.get_value("Company", company, "default_currency")
		or frappe.db.get_single_value("Global Defaults", "default_currency")
		or ""
	)
	return {"price_list": price_list, "currency": currency, "company": company}


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
