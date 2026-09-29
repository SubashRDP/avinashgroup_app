"""Take the Dashain Bonus screen off every site.

The user decided on 2026-09-29 not to run the festival bonus through a
document of its own (it had been installed by the now-removed
setup_dashain_bonus patch). The code is gone, so a site still holding the two
doctypes would show a form nothing can run.

A submitted Dashain Bonus has already paid people through Additional Salary,
and deleting it would leave those with nothing pointing back at them — so a
site with one is left alone and reported, for someone to decide. Drafts go
with the doctype. The `Dashain Bonus` salary component stays: it is a pay
line, usable on Additional Salary without this screen.
"""

import frappe

DOCTYPES = ("Dashain Bonus", "Dashain Bonus Employee")


def execute():
	if not frappe.db.exists("DocType", "Dashain Bonus"):
		return

	submitted = frappe.db.count("Dashain Bonus", {"docstatus": ["!=", 0]})
	if submitted:
		print(f"Dashain Bonus kept: {submitted} submitted/cancelled record(s) still on this site")
		return

	# Drafts by SQL: the controller is gone, so delete_doc cannot load one.
	frappe.db.delete("Dashain Bonus Employee")
	frappe.db.delete("Dashain Bonus")
	for doctype in DOCTYPES:
		frappe.delete_doc("DocType", doctype, force=True, ignore_missing=True, ignore_permissions=True)
		# Deleting a DocType leaves its (now empty) table behind.
		frappe.db.sql_ddl(f"drop table if exists `tab{doctype}`")
