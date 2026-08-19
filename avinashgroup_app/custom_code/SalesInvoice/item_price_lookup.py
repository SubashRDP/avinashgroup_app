import frappe
from frappe.utils import flt


def _get_company_field(item_price_meta):
	fieldname = "company" if item_price_meta.has_field("company") else None
	if not fieldname and item_price_meta.has_field("custom_company"):
		fieldname = "custom_company"
	return fieldname


def _get_item_group_field(item_price_meta):
	fieldname = "item_group" if item_price_meta.has_field("item_group") else None
	if not fieldname and item_price_meta.has_field("custom_item_group"):
		fieldname = "custom_item_group"
	return fieldname


def _find_item_price(filters):
	rows = frappe.get_all(
		"Item Price",
		filters=filters,
		fields=["price_list_rate"],
		order_by="valid_from desc, modified desc",
		limit=1,
	)
	return flt(rows[0].price_list_rate) if rows else 0.0


@frappe.whitelist()
def get_rate(item_code, price_list, uom=None, company=None):
	"""Return the Item Price rate for the given item/UOM/company.

	The lookup prefers the exact UOM row and then falls back to the item's stock UOM.
	If the Item Price doctype has company / item-group custom fields on this site,
	they are included as additional filters.
	"""
	if not item_code or not price_list:
		return 0.0

	item = frappe.get_cached_doc("Item", item_code)
	item_price_meta = frappe.get_meta("Item Price")

	company_field = _get_company_field(item_price_meta)
	item_group_field = _get_item_group_field(item_price_meta)

	def build_filters(resolved_uom):
		filters = {
			"item_code": item_code,
			"price_list": price_list,
			"selling": 1,
		}
		if resolved_uom:
			filters["uom"] = resolved_uom
		if company and company_field:
			filters[company_field] = company
		if item.item_group and item_group_field:
			filters[item_group_field] = item.item_group
		return filters

	rate = _find_item_price(build_filters(uom))
	if rate:
		return rate

	stock_uom = item.get("stock_uom")
	if stock_uom and stock_uom != uom:
		return _find_item_price(build_filters(stock_uom))

	return 0.0
