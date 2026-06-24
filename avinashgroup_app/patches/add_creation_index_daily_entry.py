# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

"""Add a composite `(owner, creation)` index for every doctype tracked by the
User Daily Entry Summary report.

The report counts "Created" docs with `owner = user AND creation BETWEEN day`.
A composite (owner, creation) index matches that predicate exactly — equality on
owner, range on creation — so it returns only the audited user's rows instead of
full-scanning the table (e.g. ~110k rows on Sales Invoice). "Modified" already
rides Frappe's built-in `modified` index. Idempotent: skips tables that already
carry the named index.
"""

import frappe

INDEX_NAME = "daily_entry_owner_creation"


def execute():
	doctypes = frappe.get_all(
		"User Daily Entry Summary Doctype", pluck="document_type", distinct=True
	)

	for dt in {d for d in doctypes if d}:
		if not frappe.db.exists("DocType", dt):
			continue

		table = f"tab{dt}"
		already_indexed = frappe.db.sql(
			f"SHOW INDEX FROM `{table}` WHERE Key_name = %s", INDEX_NAME
		)
		if already_indexed:
			continue

		try:
			frappe.db.add_index(dt, ["owner", "creation"], index_name=INDEX_NAME)
		except Exception:
			frappe.log_error(
				title="add_creation_index_daily_entry failed",
				message=f"Could not add (owner, creation) index on {dt}",
			)
