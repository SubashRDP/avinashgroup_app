"""The number a document shows to the outside world, not its Frappe name.

A Journal Entry named NGI-JE-83/84-00334 is NGI-CS-000002-83/84 on the paper
the customer is handed, and that is the number every ledger and statement is
expected to print. Which field holds it differs per doctype -- custom_branch_name
on Sales Invoice, custom_name on the rest -- so nothing here hardcodes it:
Numbering Configuration.target_field already names the field, and reading the
rule means a new doctype, or a changed target, needs no edit here.
"""

import frappe


def target_fields():
	"""DocType -> the field holding its voucher number, per Numbering Configuration."""
	fields = {}
	for row in frappe.get_all(
		"Numbering Configuration",
		filters={"enabled": 1},
		fields=["document_type", "target_field"],
	):
		if row.target_field and row.document_type not in fields:
			fields[row.document_type] = row.target_field
	return fields


def resolve(pairs):
	"""Map {(voucher_type, name): number} for the (voucher_type, name) pairs given.

	Pairs whose doctype has no numbering rule, or whose document carries no
	number yet, are simply absent -- callers fall back to the Frappe name.
	"""
	wanted = {}
	for voucher_type, name in pairs:
		if voucher_type and name:
			wanted.setdefault(voucher_type, set()).add(name)

	numbers = {}
	targets = target_fields()
	for voucher_type, names in wanted.items():
		field = targets.get(voucher_type)
		if not field or not frappe.db.has_column(voucher_type, field):
			continue
		names = list(names)
		for start in range(0, len(names), 500):
			for row in frappe.get_all(
				voucher_type,
				filters={"name": ("in", names[start : start + 500])},
				fields=["name", "{0} as number".format(field)],
			):
				if row.number:
					numbers[(voucher_type, row.name)] = row.number
	return numbers
