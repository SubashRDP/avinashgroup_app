import frappe
from frappe.utils import flt


def patch_insert_item_price_set_company():
	"""
	Patch `erpnext.stock.get_item_details.insert_item_price` so that when ERPNext auto-creates a
	new `Item Price`, it sets `company` from the calling transaction (`args.company`).

	This is needed when `Item Price.company` is mandatory (custom field / customization).
	"""
	from erpnext.stock import get_item_details as gid

	if getattr(gid, "_avinashgroup_insert_item_price_company_patched", False):
		return

	def _get_stock_uom_rate(rate, args):
		return rate / args.conversion_factor if args.conversion_factor else rate

	def insert_item_price(args):
		"""Insert Item Price if Price List and Price List Rate are specified and currency is the same"""
		if (
			not args.price_list
			or not args.rate
			or args.get("is_internal_supplier")
			or args.get("is_internal_customer")
		):
			return

		stock_settings = frappe.get_cached_doc("Stock Settings")

		if (
			not frappe.db.get_value("Price List", args.price_list, "currency", cache=True) == args.currency
			or not stock_settings.auto_insert_price_list_rate_if_missing
			or not frappe.has_permission("Item Price", "write")
		):
			return

		item_price = frappe.db.get_value(
			"Item Price",
			{
				"item_code": args.item_code,
				"price_list": args.price_list,
				"currency": args.currency,
				"uom": args.stock_uom,
			},
			["name", "price_list_rate"],
			as_dict=1,
		)

		update_based_on_price_list_rate = stock_settings.update_price_list_based_on == "Price List Rate"

		if item_price and item_price.name:
			if not stock_settings.update_existing_price_list_rate:
				return

			rate_to_consider = flt(args.price_list_rate) if update_based_on_price_list_rate else flt(args.rate)
			price_list_rate = _get_stock_uom_rate(rate_to_consider, args)

			if not price_list_rate or item_price.price_list_rate == price_list_rate:
				return

			frappe.db.set_value("Item Price", item_price.name, "price_list_rate", price_list_rate)
			frappe.msgprint(
				frappe._("Item Price updated for {0} in Price List {1}").format(
					args.item_code, args.price_list
				),
				alert=True,
			)
		else:
			rate_to_consider = (
				(flt(args.price_list_rate) or flt(args.rate))
				if update_based_on_price_list_rate
				else flt(args.rate)
			)
			price_list_rate = _get_stock_uom_rate(rate_to_consider, args)

			item_price_doc = {
				"doctype": "Item Price",
				"price_list": args.price_list,
				"item_code": args.item_code,
				"currency": args.currency,
				"price_list_rate": price_list_rate,
				"uom": args.stock_uom,
			}

			company = args.get("company")
			if company:
				item_price_meta = frappe.get_meta("Item Price")
				# Some setups use a custom field instead of standard `company`.
				if item_price_meta.get_field("company"):
					item_price_doc["company"] = company
				if item_price_meta.get_field("custom_company"):
					item_price_doc["custom_company"] = company

			frappe.get_doc(item_price_doc).insert()
			frappe.msgprint(
				frappe._("Item Price added for {0} in Price List {1}").format(args.item_code, args.price_list),
				alert=True,
			)

	gid.insert_item_price = insert_item_price
	gid._avinashgroup_insert_item_price_company_patched = True
