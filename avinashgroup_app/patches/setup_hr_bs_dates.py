"""BS dates on the HR forms and a BS payslip; see hr/bs_dates.py for the why.

  1. A read-only-where-derived `custom_*_miti` Data field beside each AD date in
     hr.bs_dates.BS_DATE_FIELDS, and `Salary Slip.custom_bs_month`.
  2. A Bs Conversion record per editable doctype, so rdp_common_app's Nepali date
     picker binds the pair on the desk form (both directions), exactly as it
     does on Journal Entry and Payment Entry.
  3. Existing documents back-filled, so old leave and slips show BS too.
  4. "Salary Slip BS" as the Salary Slip default print format (the file is in
     avinash_group_app/print_format/), which is also what HRMS attaches when it
     emails a slip, and an email template naming the BS month, used only when
     Payroll Settings has none of its own.

Idempotent.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.custom.doctype.property_setter.property_setter import make_property_setter

from avinashgroup_app.hr.bs_dates import BS_DATE_FIELDS, bs_month_label, to_miti

# Slips and payroll runs are derived documents: their dates are set by HRMS from
# the BS period, never typed, so the miti is display-only there.
READ_ONLY_DOCTYPES = ("Salary Slip",)
PICKER_DOCTYPES = ("Leave Application", "Payroll Entry", "Employee")

EMAIL_TEMPLATE = "Salary Slip (BS)"


def execute():
	add_fields()
	register_pickers()
	backfill()
	set_payslip_defaults()


def add_fields():
	fields = {}
	for doctype, pairs in BS_DATE_FIELDS.items():
		fields[doctype] = [
			{
				"fieldname": miti,
				"label": label,
				"fieldtype": "Data",
				"insert_after": ad,
				"read_only": 1 if doctype in READ_ONLY_DOCTYPES else 0,
				"no_copy": 1,
				"description": "YYYY-MM-DD (BS). Kept in step with the AD date.",
			}
			for ad, miti, label in pairs
		]
	fields["Salary Slip"].append(
		{
			"fieldname": "custom_bs_month",
			"label": "Salary Month (BS)",
			"fieldtype": "Data",
			"insert_after": "custom_posting_miti",
			"read_only": 1,
			"no_copy": 1,
			"in_list_view": 1,
			"in_standard_filter": 1,
		}
	)
	create_custom_fields(fields, update=True)
	for doctype in BS_DATE_FIELDS:
		frappe.clear_cache(doctype=doctype)


def register_pickers():
	for doctype in PICKER_DOCTYPES:
		name = frappe.db.get_value("Bs Conversion", {"doctype_names": doctype}, "name")
		doc = frappe.get_doc("Bs Conversion", name) if name else frappe.new_doc("Bs Conversion")
		doc.doctype_names = doctype
		have = {row.ad_date for row in doc.get("ad_bs") or []}
		for ad, miti, label in BS_DATE_FIELDS[doctype]:
			if ad not in have:
				doc.append("ad_bs", {"ad_date": ad, "bs_date": miti, "bs_label": label, "enabled": 1})
		doc.flags.ignore_permissions = True
		if name:
			doc.save()
		else:
			doc.insert(set_name=doctype)


def backfill():
	for doctype, pairs in BS_DATE_FIELDS.items():
		ad_fields = [ad for ad, __, ___ in pairs]
		for row in frappe.get_all(doctype, fields=["name", *ad_fields]):
			values = {miti: to_miti(row.get(ad)) for ad, miti, __ in pairs if row.get(ad)}
			if doctype == "Salary Slip" and row.get("end_date"):
				values["custom_bs_month"] = bs_month_label(row.end_date)
			if values:
				frappe.db.set_value(doctype, row.name, values, update_modified=False)


def set_payslip_defaults():
	make_property_setter(
		"Salary Slip", None, "default_print_format", "Salary Slip BS", "Data", for_doctype=True
	)

	if not frappe.db.exists("Email Template", EMAIL_TEMPLATE):
		frappe.get_doc(
			{
				"doctype": "Email Template",
				"name": EMAIL_TEMPLATE,
				"subject": "Salary Slip — {{ custom_bs_month }} · {{ company }}",
				# HRMS renders `response`, never `response_html`.
				"response": (
					"<p>Dear {{ employee_name }},</p>"
					"<p>Your salary slip for <b>{{ custom_bs_month }}</b> "
					"({{ custom_start_miti }} to {{ custom_end_miti }}) is attached.</p>"
					"<p>{{ company }}</p>"
				),
			}
		).insert(ignore_permissions=True)

	if not frappe.db.get_single_value("Payroll Settings", "email_template"):
		frappe.db.set_single_value("Payroll Settings", "email_template", EMAIL_TEMPLATE)
