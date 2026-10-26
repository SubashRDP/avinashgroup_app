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

A Payroll Entry with Payout set (Dashain Allowance, Leave Encashment) pays only
that, on slips of its own, and posts its own journal and bank entry the same
way: payroll/special_payout.py. Its slips sit beside the month's salary slips,
so the duplicate checks and Get Employees compare a slip only with slips of
its own kind (`validate_existing_salary_slips`, `fill_employee_details`).

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
from avinashgroup_app.payroll.recovery_cap import cap_recoveries
from avinashgroup_app.payroll.special_payout import (
	DASHAIN,
	ENCASHMENT,
	PAYOUT_FIELD,
	employees_due,
	slip_kind_filter,
)


def prepare_payroll_inputs(entry, stage):
	"""Post everything this entry's slips read, in one go, without committing.

	Monthly salary: tea, meals, overtime and late fines (attendance), advance
	instalments, and, when Settle Leave is ticked, the recovery of leave taken
	beyond what was earned. A payout entry: only its payout — the Dashain
	allowance, or the leave encashment (payroll/special_payout.py). Each is
	posted as submitted Additional Salary, so the slips HRMS makes or submits
	next carry it. Runs inside HRMS's own submit and slip calls, which commit
	(or roll back) all of it together. Every run appends a line to the entry's
	Payroll Inputs Log, so the entry records what was paid and when.

	Re-running is safe: attendance lines are replaced, a Dashain or encashment
	already submitted for the person is left alone and not paid twice.
	"""
	payout = entry.get(PAYOUT_FIELD)
	if payout == DASHAIN:
		append_inputs_log(entry, stage, _pay_dashain(entry))
		return
	if payout == ENCASHMENT:
		append_inputs_log(entry, stage, _pay_leave_encashment(entry))
		return

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
	if attendance.get("already_paid"):
		parts.append(_("{0} already paid, left as they are").format(len(attendance["already_paid"])))
	if entry.get("custom_pay_leave_encashment"):
		parts.append(_recover_leave(entry))
	append_inputs_log(entry, stage, "; ".join(parts))


def append_inputs_log(entry, stage, text):
	"""Add a dated line to the entry's Payroll Inputs Log.

	A site not yet migrated to the Yearly Payments fields (patch
	payroll_entry_yearly_payments) has no log field: the line goes to the
	entry's comments instead, so posting never fails on a missing column.
	"""
	when = frappe.utils.format_datetime(frappe.utils.now_datetime(), "yyyy-MM-dd HH:mm")
	line = f"{when} {stage} by {frappe.session.user}: {text}"
	if not entry.meta.has_field("custom_payroll_inputs_log"):
		entry.add_comment("Info", line)
		return
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
		if entry.meta.has_field("custom_festival_adjustment"):
			entry.db_set("custom_festival_adjustment", name, update_modified=False)
		return _("Dashain {0}: {1} people, total {2}").format(name, result["count"], _money(result["total"]))
	# Nothing due: everyone already paid by an earlier run, or nobody qualifies.
	return _("Dashain: nothing new to pay ({0} left out)").format(len(result.get("left_out") or []))


def _pay_leave_encashment(entry):
	"""Make and submit the month's Leave Encashments (a Leave Encashment payout entry); returns its log text."""
	from avinashgroup_app.payroll.leave_encashment import encash_month

	if frappe.utils.getdate() < frappe.utils.getdate(entry.start_date):
		return _("Leave encashment: not before {0}, the month's first day").format(entry.start_date)
	currency = frappe.get_cached_value("Company", entry.company, "default_currency")
	employees = [r.employee for r in entry.employees]
	result = encash_month(entry.company, currency, employees, entry.start_date, entry.end_date)
	for row in result["created"]:
		doc = frappe.get_doc("Leave Encashment", row["name"])
		doc.flags.ignore_permissions = True
		doc.submit()
	return _("Leave encashment: {0} people, total {1}; {2} left out").format(
		len(result["created"]), _money(result["total"]), len(result["left_out"])
	)


def _recover_leave(entry):
	"""Deduct leave taken beyond what was earned, on the month's salary slips; returns its log text.

	Stays on the monthly (or final) slip: it is a deduction from pay, not a payout.
	"""
	from avinashgroup_app.payroll.leave_encashment import recover_month

	if frappe.utils.getdate() < frappe.utils.getdate(entry.start_date):
		return _("Leave recovery: not before {0}, the month's first day").format(entry.start_date)
	employees = [r.employee for r in entry.employees]
	recovered = recover_month(entry.company, employees, entry.start_date, entry.end_date)
	return _("Leave recovery: {0} people, total {1}").format(
		len({m["employee"] for m in recovered["made"]}), _money(recovered["total"])
	)


def drop_employees_not_due(entry):
	"""Take off a payout entry everyone with nothing to be paid on it; returns their names.

	The payout's amounts are worked out for every employee on the entry (the
	Dashain rules, the encashment balances); someone left out would otherwise
	get a slip with nothing on it, which HRMS cannot make. Throws when nobody
	is left.
	"""
	due = employees_due([r.employee for r in entry.employees], entry.get(PAYOUT_FIELD), entry.start_date, entry.end_date)
	dropped = [r for r in entry.employees if r.employee not in due]
	if not dropped:
		return []
	if len(dropped) == len(entry.employees):
		frappe.throw(
			_("Nobody on this entry has {0} to be paid between {1} and {2}. See the Payroll Inputs Log.").format(
				entry.get(PAYOUT_FIELD), entry.start_date, entry.end_date
			),
			title=_("Nothing to pay"),
		)
	for row in dropped:
		frappe.db.delete("Payroll Employee Detail", {"name": row.name})
		entry.remove(row)
	entry.db_set("number_of_employees", len(entry.employees), update_modified=False)
	names = [r.employee_name or r.employee for r in dropped]
	append_inputs_log(entry, _("Not due"), _("{0} people taken off, nothing to pay: {1}").format(len(names), ", ".join(names)))
	return names


def warn_shortfalls(entry, shortfalls):
	"""Log and show what recoveries could not be taken from the last slips (payroll/recovery_cap.py)."""
	if not shortfalls:
		return
	lines = [
		_("{0} ({1}): {2} of {3}").format(s["employee_name"], s["employee"], _money(s["amount"]), s["component"])
		for s in shortfalls
	]
	append_inputs_log(entry, _("Recoveries cut to the pay"), _("collect outside payroll: ") + "; ".join(lines))
	frappe.msgprint(
		_("These recoveries were more than the slip could pay, so the slip takes what it can. Collect the rest outside payroll:")
		+ "<br>" + "<br>".join(frappe.utils.escape_html(line) for line in lines),
		title=_("Collect Outside Payroll"),
		indicator="orange",
	)


def check_ready_for_slips(entry):
	"""Refuse the run up front, naming every employee who would break it.

	HRMS finds these one at a time, deep in the run: slip creation stops at the
	first person with no salary assignment for the month, and slip submission
	stops at the journal for the first person with no payroll section. By then
	the month's tea, overtime and fines are already posted and the entry reads
	"Failed" with one name. Checking first keeps the run all-or-nothing and
	gives HR the whole list, with what to do for each.

	Two checks, exactly HRMS's and the journal's own:
	  * a submitted Salary Structure Assignment dated on or before the day the
	    slip starts (the month's first day, or the joining day if later);
	  * a Payroll Section on the person's Department, when any of the
	    company's components posts by section.
	"""
	from frappe.utils import getdate

	from avinashgroup_app.payroll.allowance import get_section, has_section_accounts

	start, end = getdate(entry.start_date), getdate(entry.end_date)
	posts_by_section = any(
		has_section_accounts(entry.company, name)
		for name in frappe.get_all("Salary Component", filters={"disabled": 0}, pluck="name")
	)
	problems = []
	for row in entry.employees:
		joined = frappe.get_cached_value("Employee", row.employee, "date_of_joining")
		slip_start = getdate(joined) if joined and start < getdate(joined) <= end else start
		if not frappe.db.exists(
			"Salary Structure Assignment",
			{"employee": row.employee, "docstatus": 1, "from_date": ("<=", slip_start)},
		):
			later = frappe.db.get_value(
				"Salary Structure Assignment",
				{"employee": row.employee, "docstatus": 1},
				"from_date",
				order_by="from_date asc",
			)
			problems.append(
				_("{0}: salary assignment starts {1}; it must start on or before {2}").format(
					row.employee_name or row.employee, later, slip_start
				)
				if later
				else _("{0}: no submitted salary assignment").format(row.employee_name or row.employee)
			)
		if posts_by_section and not get_section(row.employee):
			department = frappe.get_cached_value("Employee", row.employee, "department")
			problems.append(
				_("{0}: Department {1} has no Payroll Section").format(row.employee_name or row.employee, department)
				if department
				else _("{0}: no Department").format(row.employee_name or row.employee)
			)
	if problems:
		frappe.throw(
			_("Nothing was posted. Fix these, or remove the people from the Employees table, then try again:")
			+ "<ul>"
			+ "".join(f"<li>{frappe.utils.escape_html(p)}</li>" for p in problems)
			+ "</ul>",
			title=_("Payroll cannot run yet"),
		)


def check_payout(entry):
	"""Set a payout entry up for its payout alone, and refuse what it would refuse later.

	Dashain Allowance: Pay Dashain ticked, the festival component and pay
	month checked. Leave Encashment: Settle Leave ticked. Either way attendance
	is not checked (the amount does not depend on it). A monthly entry never
	pays Dashain any more; a tick left from before is cleared with a notice.
	"""
	payout = entry.get(PAYOUT_FIELD)
	if payout:
		entry.validate_attendance = 0
		entry.custom_pay_dashain = 1 if payout == DASHAIN else 0
		entry.custom_pay_leave_encashment = 1 if payout == ENCASHMENT else 0
	elif entry.get("custom_pay_dashain"):
		entry.custom_pay_dashain = 0
		frappe.msgprint(
			_("Dashain is paid on its own slips now: make a Payroll Entry for this month with Payout = Dashain Allowance."),
			title=_("Dashain not paid on the salary"),
			indicator="orange",
		)
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
			_("{0} is paid in {1}; this entry is for {2}. Change the month.").format(
				rules.name, rules.custom_festival_pay_month, entry.custom_bs_month
			)
		)


#: The account types a salary payment may be made from (HRMS's own filter on
#: the Payment Account field, payroll_entry.js).
PAYMENT_ACCOUNT_TYPES = ("Bank", "Cash")


class AvinashPayrollEntry(PayrollEntry):
	def validate(self):
		check_payout(self)
		fill_from_bs_month(self)
		super().validate()
		if self.is_new() or self.has_value_changed("start_date"):
			if not self.get(PAYOUT_FIELD):
				warn_missing_attendance(self)
			warn_missing_tax_history(self)

	def before_submit(self):
		# Submitting makes the slips (HRMS on_submit); refuse before the entry is submitted.
		check_ready_for_slips(self)
		if not self.get(PAYOUT_FIELD):
			warn_missing_attendance(self)
		warn_missing_tax_history(self)
		super().before_submit()

	def validate_existing_salary_slips(self):
		"""HRMS's duplicate check, against slips of this entry's own kind only.

		A Dashain or encashment payout slip sits beside the month's salary slip
		(payroll/special_payout.py); two salary slips, or two payouts of the
		same kind, for one person and month are still refused.
		"""
		if not self.employees:
			return
		existing = frappe.get_all(
			"Salary Slip",
			filters={
				"employee": ("in", [e.employee for e in self.employees]),
				"start_date": self.start_date,
				"end_date": self.end_date,
				"docstatus": ("!=", 2),
				**slip_kind_filter(self.get(PAYOUT_FIELD)),
			},
			fields=["employee", "name"],
		)
		if existing:
			frappe.throw(
				_("Salary Slip already exists for {0} for the given dates").format(
					frappe.utils.comma_and([frappe.bold(d.employee) for d in existing])
				)
				+ "<br><br>"
				+ _("Reference: {0}").format(
					frappe.utils.comma_and([frappe.utils.get_link_to_form("Salary Slip", d.name) for d in existing])
				),
				title=_("Duplicate Entry"),
			)

	@frappe.whitelist()
	def fill_employee_details(self):
		"""HRMS's Get Employees, leaving out only those already paid on a slip of this kind.

		HRMS drops anyone with any submitted slip for the dates, so a payout
		entry made after the month's salary (or the salary after the payout)
		found nobody. Same query otherwise (hrms 15 payroll_entry.get_employee_list).
		"""
		from hrms.payroll.doctype.payroll_entry.payroll_entry import get_filtered_employees, get_salary_structure

		filters = self.make_filters()
		structures = get_salary_structure(
			filters.company, filters.currency, filters.salary_slip_based_on_timesheet, filters.payroll_frequency
		)
		found = (
			get_filtered_employees(structures, filters, as_dict=True, ignore_match_conditions=True) if structures else []
		)
		paid = set(
			frappe.get_all(
				"Salary Slip",
				filters={
					"employee": ("in", [e.employee for e in found] or [""]),
					"docstatus": 1,
					"start_date": self.start_date,
					"end_date": self.end_date,
					**slip_kind_filter(self.get(PAYOUT_FIELD)),
				},
				pluck="employee",
			)
		)
		employees = list({e.employee: e for e in found if e.employee not in paid}.values())
		if not employees:
			# HRMS's own search finds a subset of these, so it finds none too
			# and throws its detailed "No employees found" message.
			return super().fill_employee_details()
		self.set("employees", employees)
		self.number_of_employees = len(self.employees)
		self.update_employees_with_withheld_salaries()
		return self.get_employees_with_unmarked_attendance()

	@frappe.whitelist()
	def create_salary_slips(self):
		"""HRMS's slip creation, with this month's payroll inputs posted first.

		Late fine, tea, meals, overtime, advances and leave recovery
		reach a slip only as Additional Salary. Left to buttons they were
		forgotten (NGI-SAL-83/84-00005 went out without its late fine and tea),
		so making the slips posts them first, and the slips are born with them.
		A payout entry posts its payout instead, and drops from its list anyone
		with nothing due on it (`drop_employees_not_due`).
		"""
		check_ready_for_slips(self)
		prepare_payroll_inputs(self, _("Slips created"))
		if self.get(PAYOUT_FIELD):
			drop_employees_not_due(self)
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

		check_ready_for_slips(self)
		prepare_payroll_inputs(self, _("Slips submitted"))
		refresh_draft_slips(self)
		if not self.get(PAYOUT_FIELD):
			# A payout slip carries no recoveries; there is nothing to cap.
			warn_shortfalls(self, cap_recoveries(self))
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
