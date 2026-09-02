"""Show the real voucher number in ERPNext's stock General Ledger.

The report prints `voucher_no`, which is the Frappe document name
(NGI-JE-83/84-00334). The number on the paper is NGI-CS-000002-83/84, and that
is what an accountant reconciles against.

`voucher_no` itself is left alone: it is a Dynamic Link, so putting a number
there that is not a document name would leave a link that 404s. A column
carrying the number is added beside it, as an anchor that shows the number and
points at the document -- so it links as well as the original does.

Two near-identically labelled Voucher No columns are just confusing, so the
original is hidden once its replacement is in place. It stays in the data (and
so in exports); only the display is dropped.

The same is done for "Against Voucher", which is where a credit note names the
invoice it reverses -- it too is a Dynamic Link holding a Frappe name, and it is
the column an accountant follows to match a return to its original.

Returns need no special handling beyond that: a credit note is still a Sales
Invoice, so it resolves through the same rule -- all 10,253 on avinas1 carry a
number.
"""

import frappe

from avinashgroup_app.utils.voucher_numbers import link, resolve

COLUMN = {
	"label": "Voucher No",
	"fieldname": "custom_voucher_number",
	"fieldtype": "Data",
	"width": 180,
}

AGAINST_COLUMN = {
	"label": "Against Voucher",
	"fieldname": "custom_against_voucher_number",
	"fieldtype": "Data",
	"width": 180,
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

		pairs = []
		for row in data:
			if not isinstance(row, dict):
				continue
			pairs.append((row.get("voucher_type"), row.get("voucher_no")))
			if row.get("against_voucher"):
				pairs.append((row.get("against_voucher_type"), row.get("against_voucher")))
		numbers = resolve(pairs)
		if numbers:
			for row in data:
				if not isinstance(row, dict):
					continue
				# A doctype with no numbering rule has no number to show, so the
				# column falls back to the document name -- the original column
				# is hidden below, and a blank cell would lose the reference
				# altogether.
				number = numbers.get((row.get("voucher_type"), row.get("voucher_no")))
				row["custom_voucher_number"] = link(
					row.get("voucher_type"),
					row.get("voucher_no"),
					number or row.get("voucher_no"),
				)

				# the invoice a return reverses, by its printed number
				against = row.get("against_voucher")
				if against:
					row["custom_against_voucher_number"] = link(
						row.get("against_voucher_type"),
						against,
						numbers.get((row.get("against_voucher_type"), against)) or against,
					)

			# take the place of the column it replaces, and hide that one --
			# two columns both called Voucher No help nobody. The original
			# keeps its data, so exports and any code reading voucher_no are
			# unaffected; only the display is dropped.
			position = next(
				(i for i, c in enumerate(columns) if c.get("fieldname") == "voucher_no"),
				len(columns) - 1,
			)
			columns[position] = dict(columns[position], hidden=1)
			columns.insert(position + 1, dict(COLUMN))

			against_at = next(
				(i for i, c in enumerate(columns) if c.get("fieldname") == "against_voucher"),
				None,
			)
			if against_at is not None:
				columns[against_at] = dict(columns[against_at], hidden=1)
				columns.insert(against_at + 1, dict(AGAINST_COLUMN))

		return (columns, data, *rest)

	gl.execute = execute
	gl._avinashgroup_voucher_no_patched = True
