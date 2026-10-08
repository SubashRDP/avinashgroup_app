"""All the allowances one company pays, one row each, on one screen.

One record per company (named after it), so HR sees and edits the whole list
together. Each row (Company Allowance Item) is one allowance: who gets it, the
default rate, the rule, and three accounts. How the rows are used is explained
in payroll/company_allowance.py and docs/company-allowance.md.

This controller keeps every row consistent with the Salary Component it
describes, because HRMS reads the component:

  * an attendance-based allowance is posted as Additional Salary; if its
    component also had Depends on Payment Days, HRMS would cut it again for the
    absences the count has already left out;
  * a Fixed Monthly or % of Initial Basic allowance is added to the slip by
    payroll/salary_slip.py; if an active structure of the company also has the
    component, it would be paid twice;
  * HRMS throws "Please set account in Salary Component" unless the component
    has an account row for the company, so each row's Admin & Accounts account
    is written there on save.

HR never has to open Salary Component for an allowance: a row whose name has
no Salary Component yet gets one created on save (`create_missing_components`),
with Depends on Payment Days set the way the checks below require.
"""

import frappe
from frappe import _
from frappe.model.document import Document

from avinashgroup_app.payroll.company_allowance import SLIP_CALCULATIONS

ACCOUNT_FIELDS = ("account_admin", "account_marketing", "account_plant")


class CompanyAllowance(Document):
	def validate(self):
		self.create_missing_components()
		seen = set()
		for row in self.allowances:
			if row.salary_component in seen:
				frappe.throw(_("Row {0}: {1} is listed twice").format(row.idx, row.salary_component))
			seen.add(row.salary_component)

			self.validate_accounts(row)
			if row.is_attendance_based:
				row.calculation = None
				self.validate_attendance_based(row)
			else:
				row.based_on = None
				row.ot_eligible_only = 0
				if not row.calculation:
					frappe.throw(_("Row {0}: choose how {1} is calculated").format(row.idx, row.salary_component))
				self.validate_slip_calculation(row)
			self.validate_attendance_flag_agrees(row)

	def create_missing_components(self):
		"""Create the Salary Component behind each new allowance name; for an
		existing one, the row's Type follows the component."""
		for row in self.allowances:
			row.salary_component = (row.salary_component or "").strip()
			if not row.salary_component:
				frappe.throw(_("Row {0}: type the allowance's name").format(row.idx))
			existing_type = frappe.db.get_value("Salary Component", row.salary_component, "type")
			if existing_type:
				row.component_type = existing_type
				continue
			component = frappe.get_doc(
				{
					"doctype": "Salary Component",
					"salary_component": row.salary_component,
					"salary_component_abbr": unique_abbr(row.salary_component),
					"type": row.component_type or "Earning",
					# Attendance allowances are already counted on the days
					# worked; a fixed monthly one is cut for absent days.
					"depends_on_payment_days": 0 if row.is_attendance_based else 1,
					"is_tax_applicable": 1 if (row.component_type or "Earning") == "Earning" else 0,
					"description": _("Created from Company Allowance {0}").format(self.company),
				}
			)
			component.flags.ignore_permissions = True
			component.insert()
			frappe.msgprint(
				_("Created Salary Component {0}").format(row.salary_component), alert=True, indicator="green"
			)

	def validate_accounts(self, row):
		for field in ACCOUNT_FIELDS:
			account = row.get(field)
			if not account:
				continue
			company, is_group = frappe.db.get_value("Account", account, ["company", "is_group"])
			if company != self.company:
				frappe.throw(
					_("Row {0}: {1} belongs to {2}, not {3}").format(row.idx, account, company, self.company)
				)
			if is_group:
				frappe.throw(_("Row {0}: {1} is a group account; pick a ledger under it").format(row.idx, account))

	def validate_attendance_based(self, row):
		if not row.based_on:
			frappe.throw(_("Row {0}: choose what {1} is based on").format(row.idx, row.salary_component))
		if frappe.db.get_value("Salary Component", row.salary_component, "depends_on_payment_days"):
			frappe.throw(
				_(
					"Row {0}: untick Depends on Payment Days on Salary Component {1}: the attendance "
					"count already leaves out the absent days, so HRMS would cut it a second time."
				).format(row.idx, row.salary_component)
			)

	def validate_slip_calculation(self, row):
		if row.calculation not in SLIP_CALCULATIONS:
			return
		if frappe.db.get_value("Salary Component", row.salary_component, "type") != "Earning":
			frappe.throw(_("Row {0}: {1} can only be used for an Earning").format(row.idx, row.calculation))
		structures = frappe.db.sql(
			"""select distinct ss.name
			from `tabSalary Structure` ss
			join `tabSalary Detail` sd on sd.parent = ss.name and sd.parenttype = 'Salary Structure'
			where ss.company = %s and ss.docstatus = 1 and ss.is_active = 'Yes'
			  and sd.salary_component = %s""",
			(self.company, row.salary_component),
			pluck=True,
		)
		if structures:
			frappe.throw(
				_(
					"Row {0}: {1} is already in salary structure {2}, so it would be paid twice. "
					"Choose From Salary Structure, or take it out of the structure."
				).format(row.idx, row.salary_component, ", ".join(structures))
			)

	def validate_attendance_flag_agrees(self, row):
		"""A component is attendance-driven for every company or for none: the
		attendance reports read the flag off the component itself."""
		other = frappe.db.get_value(
			"Company Allowance Item",
			{
				"parenttype": "Company Allowance",
				"parent": ["!=", self.name],
				"salary_component": row.salary_component,
				"is_attendance_based": 0 if row.is_attendance_based else 1,
			},
			"parent",
		)
		if other:
			frappe.throw(
				_("Row {0}: {1} has {2} as {3}. Make the two companies agree.").format(
					row.idx,
					other,
					row.salary_component,
					_("not attendance based") if row.is_attendance_based else _("attendance based"),
				)
			)

	def on_update(self):
		for row in self.allowances:
			self.sync_component(row)

	def sync_component(self, row):
		component = frappe.get_doc("Salary Component", row.salary_component)
		changed = False
		if bool(component.get("custom_is_attendance_driven")) != bool(row.is_attendance_based):
			component.custom_is_attendance_driven = 1 if row.is_attendance_based else 0
			changed = True

		account_row = next((r for r in component.accounts if r.company == self.company), None)
		if not account_row:
			component.append("accounts", {"company": self.company, "account": row.account_admin})
			changed = True
		elif account_row.account != row.account_admin:
			account_row.account = row.account_admin
			changed = True

		if changed:
			component.flags.ignore_permissions = True
			component.save()


def unique_abbr(name: str) -> str:
	"""Initials of the name ("Mobile Recharge" -> "MR"), numbered if taken."""
	words = [w for w in name.replace("&", " ").split() if w[:1].isalnum()]
	base = "".join(w[0] for w in words).upper() or name[:3].upper()
	abbr, n = base, 1
	while frappe.db.exists("Salary Component", {"salary_component_abbr": abbr}):
		n += 1
		abbr = f"{base}{n}"
	return abbr
