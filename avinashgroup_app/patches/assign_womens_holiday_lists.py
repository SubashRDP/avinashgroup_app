"""Run hr.womens_holiday_list over existing staff once, so every woman already on
the books is on her company's Women list (and nobody else is). Idempotent;
writes only rows whose list changes, without touching `modified`."""

import frappe

from avinashgroup_app.hr.womens_holiday_list import set_holiday_list


def execute():
	for row in frappe.get_all(
		"Employee",
		filters={"status": "Active"},
		fields=["name", "gender", "company", "holiday_list", "date_of_joining"],
	):
		doc = frappe._dict(row)
		before = doc.holiday_list
		set_holiday_list(doc)
		if doc.holiday_list != before:
			frappe.db.set_value("Employee", row.name, "holiday_list", doc.holiday_list, update_modified=False)
