import frappe

from avinashgroup_app.custom_code.Override.auto_insert_item_price import (
	patch_insert_item_price_set_company,
)


@frappe.whitelist()
def get_item_details(args, doc=None, for_validate=False, overwrite_warehouse=True, cmd=None):
	"""
	Override for `erpnext.stock.get_item_details.get_item_details`.

	Ensures our Item Price auto-insert patch is applied in the exact request that
	fetches item details (used by buying/selling transactions).
	"""
	patch_insert_item_price_set_company()

	from erpnext.stock.get_item_details import get_item_details as erpnext_get_item_details

	# `cmd` is sent by `/api/method/...` calls; the original function doesn't accept it.
	return erpnext_get_item_details(
		args=args, doc=doc, for_validate=for_validate, overwrite_warehouse=overwrite_warehouse
	)
