"""Fiscal Year utilities for reports."""

import frappe
from rdp_common_app.utils.bs_boundaries import get_current_bs_month


@frappe.whitelist()
def get_default_fiscal_year():
	"""Get current fiscal year based on BS month.

	Fiscal year runs Shrawan (month 4) → Ashadh (month 3 of next year).
	- Months 4-12 → same BS year
	- Months 1-3 → next BS year

	Returns:
		str: Fiscal year name (e.g. "82/83")
	"""
	bs_year, bs_month = get_current_bs_month()
	fy_year = bs_year if bs_month >= 4 else bs_year - 1

	fy_name = f"{fy_year % 100}/{(fy_year + 1) % 100}"

	if frappe.db.exists("Fiscal Year", fy_name):
		return fy_name

	fy = frappe.db.get_value("Fiscal Year", {"docstatus": 1}, "name")
	return fy or None
