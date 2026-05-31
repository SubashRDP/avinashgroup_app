__version__ = "0.0.1"


# Apply runtime patches at app load.
# The Stock Adjustment engine patch makes rate-0 rows survive backdated reposts.
# Wrapped in try/except so a patch import error never blocks app boot.
try:
	from avinashgroup_app.avinash_group_app.doctype.stock_adjustment.engine_patch import apply_patch
	apply_patch()
except Exception:
	import frappe
	frappe.log_error(frappe.get_traceback(), "Stock Adjustment engine patch failed to load")
