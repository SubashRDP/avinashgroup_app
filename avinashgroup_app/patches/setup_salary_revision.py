"""Install Salary Revision: a dated pay rise, with arrears for a late one."""

import frappe

from avinashgroup_app.avinash_group_app.doctype.salary_revision.salary_revision import (
	ensure_arrears_component,
)


def execute():
	frappe.reload_doc("avinash_group_app", "doctype", "salary_revision_row")
	frappe.reload_doc("avinash_group_app", "doctype", "salary_revision")
	ensure_arrears_component()
