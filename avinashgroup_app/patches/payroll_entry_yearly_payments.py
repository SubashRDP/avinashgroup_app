"""Dashain allowance and leave encashment chosen on the Payroll Entry itself.

They were buttons beside Prepare Payroll Inputs, each making drafts to submit
by hand somewhere else. Nothing on the entry said whether that month's Dashain
or encashment had been paid, by whom, or for how much, and the month was
calculated in three separate presses. Now the entry carries the choice (two
ticks, the festival component and its service cut-off) and a read-only log of
what each run posted; making and submitting the slips does all of it at once
(payroll/payroll_entry.py `prepare_payroll_inputs`).
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	create_custom_fields(
		{
			"Payroll Entry": [
				{
					"fieldname": "custom_yearly_payments_section",
					"label": "Yearly Payments",
					"fieldtype": "Section Break",
					"insert_after": "deduct_tax_for_unsubmitted_tax_exemption_proof",
					"collapsible": 0,
				},
				{
					"fieldname": "custom_pay_dashain",
					"label": "Pay Dashain Allowance",
					"fieldtype": "Check",
					"insert_after": "custom_yearly_payments_section",
					"description": "One month's basic, less for under a year's service. Paid on this month's slips.",
				},
				{
					"fieldname": "custom_festival_component",
					"label": "Festival Component",
					"fieldtype": "Link",
					"options": "Salary Component",
					"insert_after": "custom_pay_dashain",
					"depends_on": "eval:doc.custom_pay_dashain",
					"mandatory_depends_on": "eval:doc.custom_pay_dashain",
				},
				{
					"fieldname": "custom_festival_cutoff",
					"label": "Count Service To (Cut-off)",
					"fieldtype": "Date",
					"insert_after": "custom_festival_component",
					"depends_on": "eval:doc.custom_pay_dashain",
					"description": "Ghatasthapana, or the payment date. Blank: the month's last day.",
				},
				{
					"fieldname": "custom_pay_leave_encashment",
					"label": "Pay Leave Encashment",
					"fieldtype": "Check",
					"insert_after": "custom_festival_cutoff",
					"description": "Year-end balances (Ashadh) and anyone relieved this month, on this month's slips.",
				},
				{
					"fieldname": "custom_yearly_payments_cb",
					"fieldtype": "Column Break",
					"insert_after": "custom_pay_leave_encashment",
				},
				{
					"fieldname": "custom_festival_adjustment",
					"label": "Dashain Payroll Adjustment",
					"fieldtype": "Link",
					"options": "Payroll Adjustment",
					"insert_after": "custom_yearly_payments_cb",
					"read_only": 1,
					"allow_on_submit": 1,
					"depends_on": "eval:doc.custom_festival_adjustment",
				},
				{
					"fieldname": "custom_payroll_inputs_log",
					"label": "Payroll Inputs Log",
					"fieldtype": "Small Text",
					"insert_after": "custom_festival_adjustment",
					"read_only": 1,
					"allow_on_submit": 1,
					"no_copy": 1,
					"description": "What each run posted: tea, meals, overtime, late fines, advances, Dashain, encashment.",
				},
			]
		},
		update=True,
	)
	frappe.clear_cache(doctype="Payroll Entry")
