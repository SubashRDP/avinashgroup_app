"""Show the real voucher number in ERPNext's stock General Ledger.

The report prints `voucher_no`, which is the Frappe document name
(NGI-JE-83/84-00334). The number on the paper is NGI-CS-000002-83/84, and that
is what an accountant reconciles against.

The column is NOT rewritten in place: `voucher_no` is a Dynamic Link, so putting
a number there that is not a document name would leave a link that 404s. A
"Voucher No." column is added beside it instead, and the link keeps working.
"""

import frappe

from avinashgroup_app.utils.voucher_numbers import link, resolve

COLUMN = {
	"label": "Voucher No.",
	"fieldname": "custom_voucher_number",
	"fieldtype": "Data",
	"width": 170,
}


def patch_general_ledger_voucher_no():
	"""Wrap the General Ledger report so its rows carry their voucher number."""
	from erpnext.accounts.report.general_ledger import general_ledger as gl

	if getattr(gl, "_avinashgroup_voucher_no_patched", False):
		return

	original_execute = gl.execute

	def execute(filters=None):
		columns, data, *rest = original_execute(filters)

		if not data:
			return (columns, data, *rest)

		numbers = resolve(
			(row.get("voucher_type"), row.get("voucher_no"))
			for row in data
			if isinstance(row, dict)
		)
		if numbers:
			for row in data:
				if not isinstance(row, dict):
					continue
				number = numbers.get((row.get("voucher_type"), row.get("voucher_no")))
				row["custom_voucher_number"] = (
					link(row.get("voucher_type"), row.get("voucher_no"), number)
					if number
					else ""
				)

			# sit next to the document name the number belongs to
			position = next(
				(i for i, c in enumerate(columns) if c.get("fieldname") == "voucher_no"),
				len(columns) - 1,
			)
			columns.insert(position + 1, dict(COLUMN))

		return (columns, data, *rest)

	gl.execute = execute
	gl._avinashgroup_voucher_no_patched = True
