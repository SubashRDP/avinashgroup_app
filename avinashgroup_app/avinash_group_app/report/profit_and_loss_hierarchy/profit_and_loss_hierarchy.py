import frappe
from frappe import _
from frappe.utils import flt

from erpnext.accounts.report.financial_statements import (
	compute_growth_view_data,
	compute_margin_view_data,
	get_columns,
	get_data,
	get_filtered_list_for_consolidated_report,
	get_period_list,
)
from erpnext.accounts.report.profit_and_loss_statement.profit_and_loss_statement import (
	get_chart_data,
	get_net_profit_loss,
	get_report_summary,
)


def execute(filters=None):
	filters = frappe._dict(filters or {})

	period_list = get_period_list(
		filters.from_fiscal_year,
		filters.to_fiscal_year,
		filters.period_start_date,
		filters.period_end_date,
		filters.filter_based_on,
		filters.periodicity,
		company=filters.company,
	)

	income = get_data(
		filters.company,
		"Income",
		"Credit",
		period_list,
		filters=filters,
		accumulated_values=filters.accumulated_values,
		ignore_closing_entries=True,
	)

	expense = get_data(
		filters.company,
		"Expense",
		"Debit",
		period_list,
		filters=filters,
		accumulated_values=filters.accumulated_values,
		ignore_closing_entries=True,
	)

	net_profit_loss = get_net_profit_loss(
		income, expense, period_list, filters.company, filters.presentation_currency
	)

	data = []
	data.extend(income or [])
	data.extend(expense or [])
	if net_profit_loss:
		data.append(net_profit_loss)

	# apply hierarchy level filter: zero-out higher levels
	account_level = get_account_level(filters)
	if account_level:
		data = apply_account_level_filter(data, account_level, period_list)

	columns = get_columns(filters.periodicity, period_list, filters.accumulated_values, filters.company)

	currency = filters.presentation_currency or frappe.get_cached_value(
		"Company", filters.company, "default_currency"
	)
	chart = get_chart_data(filters, columns, income, expense, net_profit_loss, currency)

	report_summary, primitive_summary = get_report_summary(
		period_list, filters.periodicity, income, expense, net_profit_loss, currency, filters
	)

	if filters.get("selected_view") == "Growth":
		compute_growth_view_data(data, period_list)

	if filters.get("selected_view") == "Margin":
		compute_margin_view_data(data, period_list, filters.accumulated_values)

	return columns, data, None, chart, report_summary, primitive_summary


def get_account_level(filters) -> int | None:
	"""Return selected hierarchy level as int between 1 and 20 (or None)."""
	level = filters.get("account_level")
	if not level:
		return None

	try:
		level_int = int(level)
	except (TypeError, ValueError):
		return None

	if level_int < 1:
		return None

	# hard-cap to avoid nonsense values
	return min(level_int, 20)


def apply_account_level_filter(data, level: int, period_list):
	"""Zero-out values for *group* accounts above the chosen indent level.

	If level == 3, then group rows with indent 0,1,2 will have their
	period values, totals and opening balances cleared. Leaf accounts
	are left as-is so variable-depth charts still show detail values.
	Net profit row is kept.
	"""

	period_keys = [getattr(p, "key", p.get("key")) for p in period_list]
	profit_label = "'" + _("Profit for the year") + "'"

	for row in data:
		# keep the net profit line intact
		if row.get("account_name") == profit_label:
			continue

		indent = int(flt(row.get("indent") or 0))
		is_group = flt(row.get("is_group") or 0) == 1

		# only affect GROUP rows above the requested level
		if is_group and indent < level:
			for key in period_keys:
				if key in row:
					# make cells visually empty, not zero
					row[key] = None

			# clear summary fields where present
			if "total" in row:
				row["total"] = None
			if "opening_balance" in row:
				row["opening_balance"] = None
			row["has_value"] = False

	return data

