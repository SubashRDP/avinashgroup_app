"""Let a voucher number (custom_name) repeat in another fiscal year or company.

The old ERPs restarted every voucher series each fiscal year and numbered each
company on its own, and the legacy number arrives verbatim (copied from Fact
Numbering) with no year in it. Grishma's CN series is the case that surfaced
it: GEPL-CN00106 is a 79/80 credit note AND an 80/81 one. The numbering engine
already scopes its duplicate check to company + fiscal year
(naming_series._number_scope_filters, commit c168bcd) — but it falls back to a
whole-table check when the field carries a DB UNIQUE index, and custom_name had
one on Journal Entry / Payment Entry / Purchase Invoice / Purchase Receipt
(the original Custom Field, plus patches/add_unique_custom_name_index for PI/PR).
So every 80/81 row whose number also existed in 79/80 was rejected on import
("Number GEPL-CN00106 is already used by GEPL-JE-79/80-00114"), 192 rows in one
sandbox upload.

This patch drops that UNIQUE index (Custom Field unique = 0; Frappe's schema
sync removes the index) and keeps a plain index (search_index = 1) so lookups by
voucher number stay indexed. Uniqueness is then the Python check's job:
one voucher number per company per fiscal year, same-year repeats still throw.

The DB index also guarded against two users saving the SAME typed number in
the same instant. That job moves to naming_series._lock_number_scope: a named
lock per doctype + company + fiscal year + number, held to commit, so the
second saver waits and then fails the normal duplicate check. No index can do
it — the year is a date range, not a stored column (custom_fiscal_year is
blank on almost every row).

Idempotent: a doctype whose field is already non-unique is left alone.
"""

import frappe

# The doctypes whose custom_name was DB-unique — the original custom fields on
# JE/PE, plus PI/PR from patches/add_unique_custom_name_index.
DOCTYPES = ("Journal Entry", "Payment Entry", "Purchase Invoice", "Purchase Receipt")


def execute():
	for dt in DOCTYPES:
		cf_name = frappe.db.get_value("Custom Field", {"dt": dt, "fieldname": "custom_name"})
		if not cf_name:
			continue
		cf = frappe.get_doc("Custom Field", cf_name)
		if not cf.unique and cf.search_index:
			continue
		cf.unique = 0
		cf.search_index = 1
		cf.save(ignore_permissions=True)  # on_update syncs the schema: drops the unique index
		frappe.clear_cache(doctype=dt)
