"""A pay rise, done the way payroll actually survives one: dated, not edited.

The standard practice — and the only one ERPNext supports safely — is that a
salary is a dated fact. You never edit someone's basic in place; you assign the
structure again from the date the new pay starts, and the old assignment stays
behind as the record of what was paid before. Every slip then picks the
assignment in force on the month it covers, so last year's payslips keep
reconciling with last year's journal entries.

Two things follow from that, and both are why this document exists:

  A slip is paid at one rate for its whole month. HRMS picks the latest
  assignment dated on or before the slip's END date (`check_sal_struct`), so a
  rise dated the 15th pays the new rate for the whole month — the first
  fourteen days included — with no trace of the split. The effective date must
  therefore be day 1 of a BS month, and validate refuses any other day.

  Increments are agreed late. The rise runs from Shrawan, the meeting happens
  in Mangsir, and four months have already been paid at the old rate. That
  difference is arrears — a one-off amount in the month it is finally paid,
  never a backdated edit to submitted slips. Each month's share follows the
  days that month actually paid, so a month with unpaid leave owes less.

Allowances change the same way, because every allowance is a row on the
assignment (payroll/allowance.py). The Allowance Changes table says what moves:

  Raise Rate   an allowance of one salary structure, from its listed rate to a
               new one: everyone on that structure paid the listed rate is
               raised, and the structure's rate list follows. Anyone on a rate
               of their own (new staff's tea at 40) is left alone and named.
  Add          give every listed employee the allowance — at the New Rate, or
               blank for their structure's rate.
  Stop         take it off every listed employee.
  Change Rate  every listed employee who has it, to the New Rate.

Each listed person gets one new assignment carrying all of it, plus the old
one's other allowances, Initial Basic and SSF Applicable, with dearness at its
new amount. Arrears cover the months already paid: a monthly amount by the days
each month paid, tea and meal by the days or meals each month counted.
Cancelling cancels the new assignments and puts a raised rate back on the
structure, so the old assignments — old allowances included — are in force
again.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate

from avinashgroup_app.payroll.allowance import (
	NOT_ON_ASSIGNMENT,
	PERCENT_OF_INITIAL_BASIC,
	FIXED_KINDS,
	rate_is_computed,
	structure_rate,
	unit_for,
)
from avinashgroup_app.payroll.year_rollover import tax_slab_for

ARREARS_COMPONENT = "Salary Arrears"
DEARNESS_COMPONENT = "Dearness Allowance"
RAISE, ADD, STOP, CHANGE = "Raise Rate", "Add", "Stop", "Change Rate"


class SalaryRevision(Document):
	def validate(self):
		self.set_bs_month()
		self.validate_effective_date()
		self.validate_allowance_changes()
		self.validate_rows()
		self.set_totals()

	# ── the allowance changes ───────────────────────────────────────────────

	def validate_allowance_changes(self):
		seen = set()
		for change in self.get("allowance_changes") or []:
			if change.allowance in seen:
				frappe.throw(_("Allowance Changes: {0} is listed twice").format(change.allowance))
			seen.add(change.allowance)

			is_allowance, kind = frappe.get_cached_value(
				"Salary Component", change.allowance, ["custom_is_allowance", "custom_allowance_kind"]
			)
			if not is_allowance or kind in NOT_ON_ASSIGNMENT:
				frappe.throw(
					_("Allowance Changes row {0}: {1} is not an allowance paid from the salary assignment").format(
						change.idx, change.allowance
					)
				)
			change.unit = unit_for(change.allowance)
			if change.change in (RAISE, CHANGE) and rate_is_computed(change.allowance):
				frappe.throw(
					_("Allowance Changes row {0}: {1} is worked out from each person's basic; raise the basic instead").format(
						change.idx, change.allowance
					)
				)
			if change.change == STOP:
				change.new_rate = 0
			elif change.change in (RAISE, CHANGE) and flt(change.new_rate) <= 0:
				frappe.throw(_("Allowance Changes row {0}: type {1}'s new rate").format(change.idx, change.allowance))

			if change.change == RAISE:
				if frappe.db.get_value("Salary Structure", change.salary_structure, "company") != self.company:
					frappe.throw(
						_("Allowance Changes row {0}: {1} is not a salary structure of {2}").format(
							change.idx, change.salary_structure, self.company
						)
					)
				if self.docstatus == 0:
					change.old_rate = structure_rate(change.salary_structure, change.allowance)
				if not flt(change.old_rate):
					frappe.throw(
						_(
							"Allowance Changes row {0}: {1} lists no rate for {2}, so nobody is on it. "
							"Use Change Rate for the people concerned."
						).format(change.idx, change.salary_structure, change.allowance)
					)
				if flt(change.new_rate) == flt(change.old_rate):
					frappe.throw(
						_("Allowance Changes row {0}: {1} is already {2}").format(
							change.idx, change.allowance, flt(change.old_rate)
						)
					)
			else:
				change.salary_structure = None
				change.old_rate = 0

	def plan_allowances(self, current):
		"""The person's allowances after this revision. `current` is their
		assignment in force on the effective date.

		Returns `rows` ({allowance: row dict}), `changes` (one line per change
		made) and `own_rate` (one line per raise passed over because the person
		is on a rate of their own).
		"""
		rows = {
			a.allowance: {"allowance": a.allowance, "rate": flt(a.rate), "effective_from": None}
			for a in current.get("custom_allowances") or []
		}
		lines, own_rate = [], []
		for change in self.get("allowance_changes") or []:
			name, row = change.allowance, rows.get(change.allowance)
			if change.change == RAISE:
				if current.salary_structure != change.salary_structure or not row:
					continue
				if flt(row["rate"]) != flt(change.old_rate):
					own_rate.append(_("{0} {1}: own rate, not raised").format(name, flt(row["rate"])))
					continue
				row["rate"] = flt(change.new_rate)
				lines.append(f"{name} {flt(change.old_rate)} → {flt(change.new_rate)}")
			elif change.change == ADD:
				if row:
					continue
				rate = 0 if rate_is_computed(name) else (
					flt(change.new_rate) or structure_rate(current.salary_structure, name)
				)
				if not rate and not rate_is_computed(name):
					frappe.throw(
						_("Add {0}: {1} lists no rate for it; type the New Rate").format(name, current.salary_structure)
					)
				rows[name] = {"allowance": name, "rate": rate, "effective_from": None}
				lines.append(f"+ {name} {rate}" if rate else f"+ {name}")
			elif change.change == STOP:
				if rows.pop(name, None):
					lines.append(f"− {name}")
			elif change.change == CHANGE:
				if not row or flt(row["rate"]) == flt(change.new_rate):
					continue
				lines.append(f"{name} {flt(row['rate'])} → {flt(change.new_rate)}")
				row["rate"] = flt(change.new_rate)
		return frappe._dict(rows=rows, changes=lines, own_rate=own_rate)

	# ── the people ──────────────────────────────────────────────────────────

	def validate_rows(self):
		seen = set()
		for row in self.employees:
			if row.employee in seen:
				frappe.throw(
					_("Row {0}: {1} is listed twice").format(row.idx, row.employee_name or row.employee)
				)
			seen.add(row.employee)

			company = frappe.db.get_value("Employee", row.employee, "company")
			if company != self.company:
				frappe.throw(
					_("Row {0}: {1} belongs to {2}").format(row.idx, row.employee_name or row.employee, company)
				)

			current = current_assignment(row.employee, self.effective_date)
			if not current:
				frappe.throw(
					_("Row {0}: {1} has no salary structure assigned, so there is nothing to revise").format(
						row.idx, row.employee_name or row.employee
					)
				)
			row.salary_structure = current.salary_structure
			row.current_base = current.base
			row.current_dearness_allowance = _rate_of(current, DEARNESS_COMPONENT)
			if not flt(row.new_base):
				# An allowance-only revision leaves the basic where it is.
				row.new_base = current.base
			plan = self.plan_allowances(current)
			if self.changes_dearness():
				# An allowance change decides dearness; the column shows its outcome.
				row.new_dearness_allowance = flt(plan.rows.get(DEARNESS_COMPONENT, {}).get("rate"))
			elif not flt(row.new_dearness_allowance):
				# Dearness is taken off with Stop; a blank here means unchanged.
				row.new_dearness_allowance = row.current_dearness_allowance
			if flt(row.new_base) <= 0:
				frappe.throw(_("Row {0}: the new basic must be more than zero").format(row.idx))

			row.allowance_summary = "\n".join(plan.changes)
			row.arrears_months = months_already_paid(row.employee, self.effective_date)
			row.arrears_amount = self.arrears(row, current) if self.pay_arrears else 0

			if frappe.db.exists(
				"Salary Structure Assignment",
				{"employee": row.employee, "from_date": getdate(self.effective_date), "docstatus": 1},
			):
				frappe.throw(
					_("Row {0}: {1} already has a salary assigned from {2}").format(
						row.idx, row.employee_name or row.employee, self.effective_date
					)
				)

	def validate_effective_date(self):
		"""A rise starts on day 1 of a BS month — see the module notes for why."""
		from rdp_common_app.utils.bs_boundaries import BS_MONTH_NAMES, ad_to_bs, bs_to_ad

		bs = ad_to_bs(getdate(self.effective_date))
		if bs.day != 1:
			first = bs_to_ad(bs.year, bs.month, 1)
			frappe.throw(
				_(
					"A salary revision must start on the first day of a BS month. {0} is {1} {2} {3}; "
					"use {4} (1 {2}) or the first of the next month."
				).format(
					frappe.utils.formatdate(self.effective_date), bs.day, BS_MONTH_NAMES[bs.month], bs.year,
					frappe.utils.formatdate(first),
				),
				title=_("Effective date is mid-month"),
			)

	def set_bs_month(self):
		try:
			from rdp_common_app.utils.bs_boundaries import BS_MONTH_NAMES, ad_to_bs

			bs = ad_to_bs(getdate(self.effective_date))
			self.bs_month = f"{BS_MONTH_NAMES[bs.month]} {bs.year}"
		except Exception:
			# A missing BS calendar must not stop an increment: the AD date still rules.
			self.bs_month = None

	def monthly_increase(self, row, current) -> float:
		"""A full month's rise: basic, dearness and the other monthly allowances."""
		rows = self.plan_allowances(current).rows
		before = _monthly_allowances(current, {a.allowance: flt(a.rate) for a in current.custom_allowances})
		after = _monthly_allowances(current, {k: v["rate"] for k, v in rows.items()})
		# Dearness is counted from the row's columns, which follow any change to it.
		before.pop(DEARNESS_COMPONENT, None)
		after.pop(DEARNESS_COMPONENT, None)
		return (
			flt(row.new_base) - flt(row.current_base)
			+ flt(row.new_dearness_allowance) - flt(row.current_dearness_allowance)
			+ sum(after.values()) - sum(before.values())
		)

	def arrears(self, row, current) -> float:
		"""What the months already paid at the old pay are owed.

		Monthly pay (basic, dearness, gas, HRA…) by the days each month paid.
		Tea and meal by what each month counted — the days present, the meals —
		times the change in the person's rate.
		"""
		owed = arrears_for(row.employee, self.effective_date, self.monthly_increase(row, current))
		rows = self.plan_allowances(current).rows
		old = {a.allowance: flt(a.rate) for a in current.custom_allowances}
		for allowance in set(old) | set(rows):
			if not frappe.get_cached_value("Salary Component", allowance, "custom_is_attendance_driven"):
				continue
			if rate_is_computed(allowance):
				continue
			difference = flt(rows.get(allowance, {}).get("rate")) - old.get(allowance, 0)
			if difference:
				owed += difference * attendance_qty_paid(row.employee, allowance, self.effective_date)
		return flt(owed, 2)

	def set_totals(self):
		self.employee_count = len(self.employees)
		total = 0.0
		for row in self.employees:
			current = current_assignment(row.employee, self.effective_date)
			total += self.monthly_increase(row, current) if current else 0
		self.total_increase = flt(total, 2)
		self.total_arrears = sum(flt(row.arrears_amount) for row in self.employees)

	# ── submit / cancel ─────────────────────────────────────────────────────

	def on_submit(self):
		for row in self.employees:
			self.assign_new_salary(row)
			self.pay_the_arrears(row)
		self.set_structure_rates(new=True)

	def on_cancel(self):
		for row in self.employees:
			if row.arrears_additional_salary and frappe.db.exists(
				"Additional Salary", row.arrears_additional_salary
			):
				doc = frappe.get_doc("Additional Salary", row.arrears_additional_salary)
				if doc.docstatus == 1:
					doc.flags.ignore_permissions = True
					doc.cancel()

			if row.salary_structure_assignment and frappe.db.exists(
				"Salary Structure Assignment", row.salary_structure_assignment
			):
				doc = frappe.get_doc("Salary Structure Assignment", row.salary_structure_assignment)
				if doc.docstatus == 1:
					doc.flags.ignore_permissions = True
					doc.cancel()
		self.set_structure_rates(new=False)

	def set_structure_rates(self, new: bool):
		"""Raise Rate moves the structure's listed rate too; cancelling moves it back.

		Only a rate still at what this revision set is put back, so a later
		revision's rate is never undone by cancelling an earlier one.
		"""
		for change in self.get("allowance_changes") or []:
			if change.change != RAISE:
				continue
			doc = frappe.get_doc("Salary Structure", change.salary_structure)
			row = next((r for r in doc.get("custom_allowance_rates") or [] if r.allowance == change.allowance), None)
			if not row:
				continue
			want, was = (change.new_rate, change.old_rate) if new else (change.old_rate, change.new_rate)
			if flt(row.rate) != flt(was):
				continue
			row.rate = flt(want)
			doc.flags.ignore_permissions = True
			frappe.flags.in_salary_revision = True
			try:
				doc.save()
			finally:
				frappe.flags.in_salary_revision = False

	def assign_new_salary(self, row):
		current = current_assignment(row.employee, self.effective_date)
		rows = self.plan_allowances(current).rows
		doc = frappe.new_doc("Salary Structure Assignment")
		doc.update(
			{
				"employee": row.employee,
				"salary_structure": row.salary_structure or current.salary_structure,
				"from_date": self.effective_date,
				"base": row.new_base,
				"variable": current.variable if current else 0,
				"company": self.company,
				"currency": (current and current.currency)
				or frappe.db.get_value("Company", self.company, "default_currency"),
				# The slab of the year the rise falls in — not the old assignment's,
				# which may be last year's (see payroll/year_rollover.py).
				"income_tax_slab": tax_slab_for(self.company, self.effective_date)
				or (current.income_tax_slab if current else None),
				"payroll_payable_account": current.payroll_payable_account if current else None,
				"custom_initial_basic": current.get("custom_initial_basic") if current else 0,
				"custom_ssf_applicable": current.get("custom_ssf_applicable") if current else 1,
			}
		)
		for allowance in rows.values():
			doc.append("custom_allowances", allowance)
		self.set_dearness(doc, row)
		doc.flags.ignore_permissions = True
		doc.insert()
		doc.submit()
		row.db_set("salary_structure_assignment", doc.name, update_modified=False)

	def changes_dearness(self) -> bool:
		return any(c.allowance == DEARNESS_COMPONENT for c in self.get("allowance_changes") or [])

	def set_dearness(self, doc, row):
		"""The new assignment's dearness row at the revised amount, unless an
		allowance change already decided it."""
		if self.changes_dearness():
			return
		existing = next((a for a in doc.custom_allowances if a.allowance == DEARNESS_COMPONENT), None)
		if not flt(row.new_dearness_allowance):
			return
		if existing:
			existing.rate = flt(row.new_dearness_allowance)
		else:
			doc.append("custom_allowances", {"allowance": DEARNESS_COMPONENT, "rate": flt(row.new_dearness_allowance)})

	def pay_the_arrears(self, row):
		if not self.pay_arrears or not flt(row.arrears_amount):
			return

		ensure_arrears_component()
		doc = frappe.new_doc("Additional Salary")
		doc.update(
			{
				"employee": row.employee,
				"company": self.company,
				"salary_component": ARREARS_COMPONENT,
				"amount": row.arrears_amount,
				"payroll_date": self.arrears_payout_date,
				"currency": frappe.db.get_value("Company", self.company, "default_currency"),
				"overwrite_salary_structure_amount": 0,
				"deduct_full_tax_on_selected_payroll_date": 1,
				"notes": row.note
				or _("Arrears of the revision effective {0} ({1})").format(self.effective_date, self.name),
			}
		)
		doc.flags.ignore_permissions = True
		doc.insert()
		doc.submit()
		row.db_set("arrears_additional_salary", doc.name, update_modified=False)

	@frappe.whitelist()
	def get_employees(self):
		"""List everyone this revision changes, at the rise it proposes.

		With an increment percent, everyone on a salary. Otherwise the people an
		allowance change reaches: on the structure at its rate (Raise Rate),
		without the allowance (Add), with it (Stop, Change Rate). Anyone a raise
		passes over because their rate is their own is named in a message.
		"""
		self.validate_allowance_changes()
		self.set("employees", [])
		percent = flt(self.default_increment_percent)
		passed_over = []

		for employee in frappe.get_all(
			"Employee",
			filters={"company": self.company, "status": "Active"},
			fields=["name", "employee_name"],
			order_by="employee_name",
		):
			current = current_assignment(employee.name, self.effective_date)
			if not current or not flt(current.base):
				continue
			plan = self.plan_allowances(current)
			if plan.own_rate:
				passed_over.append(f"{employee.employee_name}: {', '.join(plan.own_rate)}")
			if not percent and not plan.changes:
				continue

			dearness = _rate_of(current, DEARNESS_COMPONENT)
			self.append(
				"employees",
				{
					"employee": employee.name,
					"employee_name": employee.employee_name,
					"salary_structure": current.salary_structure,
					"current_base": current.base,
					"increment_percent": percent,
					# No percent, no rounding: the basic is carried exactly as it was.
					"new_base": flt(flt(current.base) * (1 + percent / 100), 2) if percent else current.base,
					"current_dearness_allowance": dearness,
					"new_dearness_allowance": dearness,
				},
			)

		for row in self.employees:
			current = current_assignment(row.employee, self.effective_date)
			row.allowance_summary = "\n".join(self.plan_allowances(current).changes)
			row.arrears_months = months_already_paid(row.employee, self.effective_date)
			row.arrears_amount = self.arrears(row, current) if self.pay_arrears else 0
		self.set_totals()
		if passed_over:
			frappe.msgprint(
				"<br>".join(frappe.utils.escape_html(p) for p in passed_over),
				title=_("Not raised: on a rate of their own"),
				indicator="orange",
			)
		return len(self.employees)


def _rate_of(assignment, allowance) -> float:
	return next((flt(a.rate) for a in assignment.get("custom_allowances") or [] if a.allowance == allowance), 0.0)


def _monthly_allowances(assignment, rates: dict) -> dict:
	"""{allowance: full-month amount} of the monthly kinds among `rates`."""
	out = {}
	for allowance, rate in rates.items():
		kind = frappe.get_cached_value("Salary Component", allowance, "custom_allowance_kind")
		if kind not in FIXED_KINDS:
			continue
		if kind == PERCENT_OF_INITIAL_BASIC:
			rate = flt(assignment.get("custom_initial_basic")) * flt(rate) / 100
		out[allowance] = flt(rate)
	return out


def current_assignment(employee, on_date):
	"""The assignment in force on the effective date — what is being replaced."""
	name = frappe.db.get_value(
		"Salary Structure Assignment",
		{"employee": employee, "docstatus": 1, "from_date": ["<=", getdate(on_date)]},
		"name",
		order_by="from_date desc",
	)
	return frappe.get_doc("Salary Structure Assignment", name) if name else None


def months_already_paid(employee, effective_date):
	"""Submitted slips covering a month on or after the date the rise runs from."""
	return frappe.db.count(
		"Salary Slip",
		{"employee": employee, "docstatus": 1, "start_date": [">=", getdate(effective_date)]},
	)


def arrears_for(employee, effective_date, monthly_difference):
	"""The rise owed on slips already paid: each month's share by the days it paid.

	A full month (31 of 31 days) owes the whole difference; a month with 5 days
	unpaid leave owes 26/31 of it — what the slip would have paid at the new rate.
	"""
	owed = 0.0
	for slip in frappe.get_all(
		"Salary Slip",
		filters={"employee": employee, "docstatus": 1, "start_date": [">=", getdate(effective_date)]},
		fields=["payment_days", "total_working_days"],
	):
		share = flt(slip.payment_days) / flt(slip.total_working_days) if flt(slip.total_working_days) else 1
		owed += flt(monthly_difference) * share
	return flt(owed, 2)


def attendance_qty_paid(employee, allowance, effective_date) -> float:
	"""The days or meals an attendance allowance counted in the months already paid.

	Counted again from attendance with the engine's own rule, so a newly added
	allowance is owed for the months it was not paid at all.
	"""
	from avinashgroup_app.payroll.attendance_allowance import (
		_attendance_period,
		_qty_for_employee,
		_skip_for_eligibility,
	)

	sc = frappe.get_cached_doc("Salary Component", allowance)
	if _skip_for_eligibility(frappe.get_cached_doc("Employee", employee), sc):
		return 0.0
	qty = 0.0
	for slip in frappe.get_all(
		"Salary Slip",
		filters={"employee": employee, "docstatus": 1, "start_date": [">=", getdate(effective_date)]},
		fields=["start_date", "end_date"],
	):
		qty += _qty_for_employee(employee, sc, *_attendance_period(sc, getdate(slip.start_date), getdate(slip.end_date)))
	return qty


def ensure_arrears_component():
	if frappe.db.exists("Salary Component", ARREARS_COMPONENT):
		return
	frappe.get_doc(
		{
			"doctype": "Salary Component",
			"salary_component": ARREARS_COMPONENT,
			"salary_component_abbr": "ARR",
			"type": "Earning",
			"is_tax_applicable": 1,
			"depends_on_payment_days": 0,
			"round_to_the_nearest_integer": 1,
		}
	).insert(ignore_permissions=True)
