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


def fiscal_year_for_date(posting_date):
	"""Name of the Fiscal Year spanning `posting_date`, or None.

	The books run on the Bikram Sambat calendar, so a year is "82/83" and
	starts mid-July. Returns None rather than throwing when no row spans the
	date — callers here are filling in a descriptive field, and a missing
	Fiscal Year row must never take down a print or an import.
	"""
	if not posting_date:
		return None
	for row in _fiscal_year_ranges():
		if row.year_start_date <= posting_date <= row.year_end_date:
			return row.name
	return None


def _fiscal_year_ranges():
	"""Every Fiscal Year row as (name, year_start_date, year_end_date), cached.

	Read once per request: resolving a whole legacy register asks this for tens
	of thousands of invoices.
	"""
	rows = frappe.local.__dict__.get("_agapp_fiscal_year_ranges")
	if rows is None:
		rows = frappe.get_all(
			"Fiscal Year",
			fields=["name", "year_start_date", "year_end_date"],
			order_by="year_start_date",
		)
		frappe.local._agapp_fiscal_year_ranges = rows
	return rows
