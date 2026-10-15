"""The payroll journal posts each section's pay to that section's own account.

The chart keeps every staff cost three ways — O/O (Admin & Accounts), S/D
(Marketing), F/P (Plant) — and the client's salary sheet charges each person
by department. HRMS's accrual journal groups slip amounts by (component, cost
centre) and takes ONE account per component and company
(`PayrollEntry.get_salary_component_account`), so all of it landed on O/O.

This override groups by (component, cost centre, section) instead, where the
section is the employee's Department → `custom_payroll_section`, and takes the
account for that section from the component's Accounts row for the company
(`custom_account_marketing`, `custom_account_plant`; the row's own account is
Admin & Accounts). A blank S/D or F/P falls back to the row's own account, which
is exactly what HRMS would have posted. See payroll/allowance.py.

The entry is made by choosing a Fiscal Year and BS month; validate fills the
dates and company defaults from them first (payroll/payroll_month.py).

Boundary: only the expense (earning) and deduction rows of the accrual
journal. Employee-advance recoveries and the payable side are HRMS's own
logic, untouched. Replaces the Salary-Expenses-only routing that used to live
in payroll/hr_journal.py. Registered via override_doctype_class.
"""

import frappe
from frappe import _
from frappe.utils import flt

from hrms.payroll.doctype.payroll_entry.payroll_entry import PayrollEntry

from avinashgroup_app.payroll.allowance import get_section, has_section_accounts, section_account
from avinashgroup_app.payroll.income_tax import warn_missing_tax_history
from avinashgroup_app.payroll.payroll_month import fill_from_bs_month, warn_missing_attendance


def prepare_payroll_inputs(entry, stage):
	"""Post everything this month's slips read, in one go, without committing.

	Tea, meals, overtime and late fines (attendance), advance instalments, and,
	when ticked on the entry, the Dashain allowance and leave encashment. Each
	is posted as submitted Additional Salary, so the slips HRMS makes or submits
	next carry it. Runs inside HRMS's own submit and slip calls, which commit
	(or roll back) all of it together. Every run appends a line to the entry's
	Payroll Inputs Log, so the entry records what was paid and when.

	Re-running is safe: attendance lines are replaced, a Dashain or encashment
	already submitted for the person is left alone and not paid twice.
	"""
	from avinashgroup_app.payroll.advance_recovery import post_recoveries
	from avinashgroup_app.payroll.attendance_allowance import create_additional_salaries

	attendance = create_additional_salaries(entry, commit=False)
	advances = post_recoveries(entry)
	totals = {"Earning": 0.0, "Deduction": 0.0}
	for row in attendance["created"]:
		kind = frappe.get_cached_value("Salary Component", row["salary_component"], "type")
		totals[kind] = totals.get(kind, 0.0) + flt(row["amount"])
	parts = [
		_("{0} attendance lines: tea / meal / overtime {1}, late fines {2}").format(
			len(attendance["created"]), _money(totals["Earning"]), _money(totals["Deduction"])
		),
		_("{0} advance instalments").format(len(advances or [])),
	]
	if attendance["skipped"]:
		parts.append(_("{0} skipped (Error Log)").format(len(attendance["skipped"])))
	if entry.get("custom_pay_dashain"):
		parts.append(_pay_dashain(entry))
	if entry.get("custom_pay_leave_encashment"):
		parts.append(_pay_leave_encashment(entry))

	when = frappe.utils.format_datetime(frappe.utils.now_datetime(), "yyyy-MM-dd HH:mm")
	line = f"{when} {stage} by {frappe.session.user}: " + "; ".join(parts)
	log = (entry.get("custom_payroll_inputs_log") or "").strip()
	entry.db_set("custom_payroll_inputs_log", f"{log}\n{line}".strip(), update_modified=False)


def _money(amount):
	return frappe.utils.fmt_money(flt(amount, 2))


def _pay_dashain(entry):
	"""Build and submit the entry's Dashain Payroll Adjustment; returns its log text."""
	from avinashgroup_app.payroll.festival_allowance import make_festival_adjustment

	result = make_festival_adjustment(entry.name, entry.custom_festival_component, entry.get("custom_festival_cutoff"))
	name = result.get("payroll_adjustment")
	if name:
		adjustment = frappe.get_doc("Payroll Adjustment", name)
		adjustment.flags.ignore_permissions = True
		adjustment.submit()
		entry.db_set("custom_festival_adjustment", name, update_modified=False)
		return _("Dashain {0}: {1} people, total {2}").format(name, result["count"], _money(result["total"]))
	# Nothing due: everyone already paid by an earlier run, or nobody qualifies.
	return _("Dashain: nothing new to pay ({0} left out)").format(len(result.get("left_out") or []))


def _pay_leave_encashment(entry):
	"""Make and submit the month's Leave Encashments; returns its log text."""
	from avinashgroup_app.payroll.leave_encashment import encash_month

	if frappe.utils.getdate() < frappe.utils.getdate(entry.start_date):
		return _("Leave encashment: not before {0}, the month's first day").format(entry.start_date)
	currency = frappe.get_cached_value("Company", entry.company, "default_currency")
	result = encash_month(entry.company, currency, [r.employee for r in entry.employees], entry.start_date, entry.end_date)
	for row in result["created"]:
		doc = frappe.get_doc("Leave Encashment", row["name"])
		doc.flags.ignore_permissions = True
		doc.submit()
	return _("Leave encashment: {0} people, total {1}; {2} left out").format(
		len(result["created"]), _money(result["total"]), len(result["left_out"])
	)


def check_yearly_payments(entry):
	"""Refuse a Dashain tick the run would refuse later, while the entry can still be edited."""
	if not entry.get("custom_pay_dashain"):
		return
	from avinashgroup_app.payroll.festival_allowance import festival_components

	rules = next((c for c in festival_components() if c.name == entry.get("custom_festival_component")), None)
	if not rules:
		frappe.throw(
			_("{0} is not a festival allowance (tick Festival Allowance on the Salary Component)").format(
				entry.get("custom_festival_component") or _("No component")
			)
		)
	if rules.custom_festival_pay_month and entry.get("custom_bs_month") and rules.custom_festival_pay_month != entry.custom_bs_month:
		frappe.throw(
			_("{0} is paid in {1}; this entry is for {2}. Untick Pay Dashain Allowance or change the month.").format(
				rules.name, rules.custom_festival_pay_month, entry.custom_bs_month
			)
		)


#: The account types a salary payment may be made from (HRMS's own filter on
#: the Payment Account field, payroll_entry.js).
PAYMENT_ACCOUNT_TYPES = ("Bank", "Cash")


class AvinashPayrollEntry(PayrollEntry):
	def validate(self):
		fill_from_bs_month(self)
		super().validate()
		check_yearly_payments(self)
		if self.is_new() or self.has_value_changed("start_date"):
			warn_missing_attendance(self)
			warn_missing_tax_history(self)

	def before_submit(self):
		warn_missing_attendance(self)
		warn_missing_tax_history(self)
		super().before_submit()

	@frappe.whitelist()
	def create_salary_slips(self):
		"""HRMS's slip creation, with this month's payroll inputs posted first.

		Late fine, tea, meals, overtime, advances and the ticked yearly payments
		reach a slip only as Additional Salary. Left to buttons they were
		forgotten (NGI-SAL-83/84-00005 went out without its late fine and tea),
		so making the slips posts them first, and the slips are born with them.
		"""
		prepare_payroll_inputs(self, _("Slips created"))
		return super().create_salary_slips()

	@frappe.whitelist()
	def submit_salary_slips(self):
		"""HRMS's slip submission, with the inputs posted again just before.

		Attendance is often corrected between making and submitting the slips;
		posting again picks that up. Posting replaces the month's Additional
		Salary, so the drafts are recalculated onto the new ones before HRMS
		submits them (a draft still pointing at a replaced one cannot submit).
		"""
		from avinashgroup_app.payroll.attendance_allowance import refresh_draft_slips

		prepare_payroll_inputs(self, _("Slips submitted"))
		refresh_draft_slips(self)
		return super().submit_salary_slips()

	@frappe.whitelist()
	def make_bank_entry(self, for_withheld_salaries=False):
		"""HRMS's Make Bank Entry, refused when the saved Payment Account cannot pay.

		Payment Account is allow-on-submit, and the button checks only the
		form's unsaved value: picked but not saved with Update, the server saw
		none and ERPNext crashed with a TypeError (NGI-PAYR-83/84-00002,
		2026-10-09). And nothing stopped a non-bank account: the same entry held
		the gas stock account, which would have credited stock with the month's
		net pay.
		"""
		if not self.payment_account:
			frappe.throw(_("Choose the Payment Account and press Update to save it, then make the bank entry."))
		account_type = frappe.db.get_value("Account", self.payment_account, "account_type")
		if account_type not in PAYMENT_ACCOUNT_TYPES:
			frappe.throw(
				_("Payment Account {0} is a {1} account. Salary is paid from a Bank or Cash account.").format(
					frappe.bold(self.payment_account), account_type or _("untyped")
				)
			)
		return super().make_bank_entry(for_withheld_salaries=for_withheld_salaries)

	def get_salary_component_total(
		self,
		component_type=None,
		employee_wise_accounting_enabled=False,
	):
		"""HRMS's own loop (hrms 15, payroll_entry.py), keyed by section too."""
		salary_components = self.get_salary_components(component_type)
		if not salary_components:
			return

		component_dict = {}
		missing_section = set()
		for item in salary_components:
			if not self.should_add_component_to_accrual_jv(component_type, item):
				continue

			section = self.section_for(item, missing_section)
			employee_cost_centers = self.get_payroll_cost_centers_for_employee(
				item.employee, item.salary_structure
			)
			employee_advance = self.get_advance_deduction(component_type, item)

			for cost_center, percentage in employee_cost_centers.items():
				amount_against_cost_center = flt(item.amount) * percentage / 100

				if employee_advance:
					self.add_advance_deduction_entry(
						item, amount_against_cost_center, cost_center, employee_advance
					)
				else:
					key = (item.salary_component, cost_center, section)
					component_dict[key] = component_dict.get(key, 0) + amount_against_cost_center

				if employee_wise_accounting_enabled:
					self.set_employee_based_payroll_payable_entries(
						component_type, item.employee, amount_against_cost_center
					)

		if missing_section:
			frappe.throw(
				_(
					"Set Payroll Section on the Department of these employees, so their pay "
					"posts to the right account: {0}"
				).format(", ".join(sorted(missing_section)))
			)

		return self.get_account(component_dict=component_dict)

	def section_for(self, item, missing_section: set):
		"""The employee's section, if this component posts by section at all."""
		if not has_section_accounts(self.company, item.salary_component):
			return None
		section = get_section(item.employee)
		if not section:
			missing_section.add(item.employee)
		return section

	def get_account(self, component_dict=None):
		account_dict = {}
		for (component, cost_center, section), amount in component_dict.items():
			account = section_account(self.company, component, section) or self.get_salary_component_account(
				component
			)
			accounting_key = (account, cost_center)
			account_dict[accounting_key] = account_dict.get(accounting_key, 0) + amount
		return account_dict
