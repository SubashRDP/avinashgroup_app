"""The month's one-off amounts, entered the way the salary sheet does them.

SST, income tax, an advance being recovered, a festival bonus — each is one
person's amount for one month. ERPNext keeps them as Additional Salary, one
document each, which is fine for two people and miserable for twenty: NGI's
Falgun sheet types them as columns beside everyone's name.

This is that column. One document per company and month, a row per employee and
component; submitting creates and submits the Additional Salary records, and
cancelling takes them back, so the month can be undone in one place.

Nothing is calculated here. What each person owes or is owed is a decision — the
sheet types it too — and the amounts sit where they can be read back later.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate


class PayrollAdjustment(Document):
	def validate(self):
		self.validate_rows()
		self.set_bs_month()
		self.set_totals()

	def validate_rows(self):
		seen = set()
		for row in self.adjustments:
			key = (row.employee, row.salary_component)
			if key in seen:
				frappe.throw(
					_("Row {0}: {1} already has a {2} row — put the whole amount on one line").format(
						row.idx, row.employee_name or row.employee, row.salary_component
					)
				)
			seen.add(key)

			company = frappe.db.get_value("Employee", row.employee, "company")
			if company != self.company:
				frappe.throw(
					_("Row {0}: {1} belongs to {2}").format(row.idx, row.employee_name or row.employee, company)
				)
			if flt(row.amount) <= 0:
				frappe.throw(_("Row {0}: amount must be more than zero").format(row.idx))

	def set_bs_month(self):
		"""Name the Nepali month, so the document says which month it belongs to."""
		try:
			from rdp_common_app.utils.bs_boundaries import BS_MONTH_NAMES, ad_to_bs

			bs = ad_to_bs(getdate(self.payroll_date))
			self.bs_month = f"{BS_MONTH_NAMES[bs.month]} {bs.year}"
		except Exception:
			# A missing BS calendar must not stop payroll: the AD date still rules.
			self.bs_month = None

	def set_totals(self):
		earning = deduction = 0.0
		for row in self.adjustments:
			kind = frappe.db.get_value("Salary Component", row.salary_component, "type")
			if kind == "Earning":
				earning += flt(row.amount)
			else:
				deduction += flt(row.amount)
		self.total_earnings, self.total_deductions = earning, deduction

	def on_submit(self):
		for row in self.adjustments:
			doc = frappe.new_doc("Additional Salary")
			doc.update(
				{
					"employee": row.employee,
					"company": self.company,
					"salary_component": row.salary_component,
					"amount": row.amount,
					"payroll_date": self.payroll_date,
					"currency": frappe.db.get_value("Company", self.company, "default_currency"),
					"overwrite_salary_structure_amount": 0,
					"notes": row.note or _("From {0}").format(self.name),
				}
			)
			doc.flags.ignore_permissions = True
			doc.insert()
			doc.submit()
			row.db_set("additional_salary", doc.name, update_modified=False)

	def on_cancel(self):
		for row in self.adjustments:
			if not row.additional_salary or not frappe.db.exists("Additional Salary", row.additional_salary):
				continue
			doc = frappe.get_doc("Additional Salary", row.additional_salary)
			if doc.docstatus == 1:
				doc.flags.ignore_permissions = True
				doc.cancel()
