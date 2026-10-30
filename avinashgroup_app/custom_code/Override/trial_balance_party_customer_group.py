"""Add a Customer Group column and filter to ERPNext's stock "Trial Balance for Party".

The stock report lists each party with its balances but says nothing about the
customer's group, so the accountant cannot tell dealers from bulk customers
without opening every customer.

The column shows the group's name (Customer Group.customer_group_name, e.g.
"Dealers"), not its document ID (GEPL-CGR-00003): groups here are named by a
naming series, so the ID means nothing on paper.

The Customer Group filter keeps only customers in that group or any group under
it. It works by narrowing the stock report's own party filter before ERPNext
builds the rows, so its Totals row covers exactly the customers shown. The
filter field itself is added to the report's JS by
trial_balance_party_customer_group.js (served through query_report.get_script).

Deliberately narrow: only when Party Type is Customer. Suppliers, employees and
the rest get the report exactly as ERPNext builds it.

Wired from before_request and before_job in hooks.py, like
general_ledger_voucher_no.py. before_job matters: this report has
prepared_report on, so it is usually rendered in a background worker.
"""

import frappe

from avinashgroup_app.utils.site_scope import app_installed

COLUMN = {
	"label": "Customer Group",
	"fieldname": "customer_group_name",
	"fieldtype": "Data",
	"width": 180,
}


def patch_trial_balance_party_customer_group():
	"""Wrap the Trial Balance for Party report so Customer rows carry their group name."""
	from erpnext.accounts.report.trial_balance_for_party import trial_balance_for_party as tbp

	if getattr(tbp, "_avinashgroup_customer_group_patched", False):
		return

	original_execute = tbp.execute

	def execute(filters=None):
		# This worker serves every site on the bench; see utils/site_scope.py.
		if not app_installed():
			return original_execute(filters)

		filters = frappe._dict(filters or {})
		if filters.get("party_type") == "Customer" and filters.get("customer_group"):
			customers = _customers_in_groups(filters.customer_group)
			if filters.get("party"):
				customers = [c for c in customers if c == filters.party]
			# [""] matches no customer, so an empty group gives an empty report
			# instead of every customer.
			filters.party = ["in", customers or [""]]

		columns, data, *rest = original_execute(filters)

		if (filters or {}).get("party_type") != "Customer" or not data:
			return (columns, data, *rest)

		customers = [row.get("party") for row in data if isinstance(row, dict) and row.get("party")]
		group_by_customer = dict(
			frappe.db.sql(
				"""
				select c.name, cg.customer_group_name
				from `tabCustomer` c
				left join `tabCustomer Group` cg on cg.name = c.customer_group
				where c.name in %(customers)s
				""",
				{"customers": customers},
			)
		)
		for row in data:
			if isinstance(row, dict) and row.get("party") in group_by_customer:
				row["customer_group_name"] = group_by_customer[row["party"]]

		# right after Customer Name; after Customer when the name column is not shown
		position = next(
			(i for i, c in enumerate(columns) if c.get("fieldname") == "party_name"),
			next((i for i, c in enumerate(columns) if c.get("fieldname") == "party"), 0),
		)
		columns.insert(position + 1, dict(COLUMN))

		return (columns, data, *rest)

	tbp.execute = execute
	tbp._avinashgroup_customer_group_patched = True


def _customers_in_groups(customer_groups):
	"""Names of the customers in any of these Customer Groups, or any group under them.

	customer_groups is the filter's value: a list from the multi-select, or a JSON /
	plain string when the report is called some other way.
	"""
	if isinstance(customer_groups, str):
		customer_groups = frappe.parse_json(customer_groups) if customer_groups.startswith("[") else [customer_groups]

	return frappe.db.sql_list(
		"""
		select distinct c.name
		from `tabCustomer` c
		join `tabCustomer Group` cg on cg.name = c.customer_group
		join `tabCustomer Group` picked
			on picked.name in %(groups)s and cg.lft >= picked.lft and cg.rgt <= picked.rgt
		""",
		{"groups": tuple(customer_groups) or ("",)},
	)
