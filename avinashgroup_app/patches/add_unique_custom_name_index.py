"""Give Purchase Invoice / Purchase Receipt the same DB-level duplicate
protection Journal Entry / Payment Entry already have: a UNIQUE index on
custom_name.

Why: the Python uniqueness validators read a REPEATABLE READ snapshot, so two
saves committing the same manually-typed number in the same instant can slip
past them. JE/PE are backstopped by their existing unique index; PI/PR were
not. The index is the last line of defense — the friendly validation errors
still fire first in every non-concurrent case.

Defensive: empty strings are NULLed first (NULLs may repeat under a unique
index; a second '' would violate it), and a doctype with existing duplicate
values is skipped with a logged error instead of failing the migrate."""

import frappe


DOCTYPES = ("Purchase Invoice", "Purchase Receipt")


def execute():
    for dt in DOCTYPES:
        cf_name = frappe.db.get_value("Custom Field", {"dt": dt, "fieldname": "custom_name"})
        if not cf_name:
            continue

        # '' -> NULL so blank names can repeat under the unique index
        frappe.db.sql("UPDATE `tab{}` SET custom_name = NULL WHERE custom_name = ''".format(dt))

        dup = frappe.db.sql(
            "SELECT custom_name FROM `tab{}` WHERE custom_name IS NOT NULL "
            "GROUP BY custom_name HAVING COUNT(*) > 1 LIMIT 1".format(dt)
        )
        if dup:
            frappe.log_error(
                title="unique custom_name index skipped",
                message="{}: duplicate custom_name '{}' exists — resolve and re-run "
                "avinashgroup_app.patches.add_unique_custom_name_index".format(dt, dup[0][0]),
            )
            continue

        cf = frappe.get_doc("Custom Field", cf_name)
        if cf.unique:
            continue
        try:
            cf.unique = 1
            cf.save(ignore_permissions=True)  # on_update syncs the DB schema
            frappe.db.commit()
        except Exception:
            frappe.db.rollback()
            frappe.log_error(title="unique custom_name index failed for " + dt)
