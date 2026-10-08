"""Calculator: Attendance + per-employee rates → Additional Salary.

Per Payroll Entry:
1. List Salary Components where `custom_is_attendance_driven = 1` and not disabled.
2. For each (employee, component), skip anyone not tagged with it — not in their
   salary structure and no Eligible row of their own (payroll/allowance.py) —
   and, for an "Only OT-Eligible Staff" component, anyone not OT eligible.
3. Evaluate the component's condition against the employee's submitted
   Attendance rows in the period — the payroll's BS month, or the one before
   it when the component's Attendance Month says so — and sum the qty.
4. Multiply qty × rate (employee's own row → the company's Default Rate on the
   component's Accounts row → the component's rate basis: a flat default, or
   Hourly Basic × Multiplier for OT and late fine).
5. Create and submit an Additional Salary per (employee, component,
   payroll_date), tagged with `custom_source = "Nepal HRMS Attendance
   Allowance"`. Idempotent: earlier rows with the same tag are replaced.
"""

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, getdate

from avinashgroup_app.hr.overtime import ENTITLEMENT_OVERTIME
from avinashgroup_app.hr.shift_day import measure_day
from avinashgroup_app.payroll.allowance import (
	company_default_rate,
	get_employee_allowance_rows,
	is_tagged,
)

SOURCE_TAG = "Nepal HRMS Attendance Allowance"

# Statuses that are *not* "present" full-day. Half Day is excluded because it's
# weighted at 0.5 separately; Absent/On Leave aren't worked days at all.
_NON_PRESENT_STATUSES = frozenset({"Absent", "On Leave", "Half Day"})


def get_present_statuses() -> tuple:
	"""Return tuple of Attendance.status values that count as a full present day.

	Derived from the Attendance doctype's `status` Select options minus the
	well-known non-present statuses, so adding a new status (e.g. via Custom
	Field) doesn't require code changes here.
	"""
	cached = getattr(frappe.local, "_agp_present_statuses", None)
	if cached is not None:
		return cached

	options = frappe.get_meta("Attendance").get_field("status").options or ""
	statuses = [s.strip() for s in options.split("\n") if s.strip()]
	result = tuple(s for s in statuses if s not in _NON_PRESENT_STATUSES)

	# Memoize per request: this runs in the innermost employee×day×component loop
	# of the attendance reports. frappe.local resets each request, so schema
	# changes to Attendance.status are picked up on the next request (no stale cache).
	frappe.local._agp_present_statuses = result
	return result


@frappe.whitelist()
def trigger_for_payroll_entry(payroll_entry: str) -> dict:
	pe = frappe.get_doc("Payroll Entry", payroll_entry)
	if pe.docstatus == 2:
		frappe.throw(_("Cannot calculate allowances for a cancelled Payroll Entry."))
	result = create_additional_salaries(pe)

	# The month's advance instalments go in with the allowances: one button
	# prepares everything the slips will read.
	from avinashgroup_app.payroll.advance_recovery import post_recoveries

	recoveries = post_recoveries(pe)
	refreshed = refresh_draft_slips(pe)
	frappe.db.commit()
	return {
		"payroll_entry": pe.name,
		"created": len(result["created"]),
		"skipped": len(result["skipped"]),
		"records": result["created"],
		"skipped_records": result["skipped"],
		"advance_recoveries": len(recoveries),
		"slips_refreshed": refreshed,
		"recovery_records": recoveries,
	}


def refresh_draft_slips(pe) -> int:
	"""Recalculate the entry's draft salary slips so they show what was just posted.

	HRMS makes the slips when the Payroll Entry is submitted. Pressed after
	that, the button's Additional Salary would reach a slip only when the slip
	is next saved, so HR would review drafts without this month's tea, meals
	and overtime. Submitted slips are never touched.
	"""
	refreshed = 0
	for name in frappe.get_all("Salary Slip", filters={"payroll_entry": pe.name, "docstatus": 0}, pluck="name"):
		slip = frappe.get_doc("Salary Slip", name)
		slip.flags.ignore_permissions = True
		slip.save()
		refreshed += 1
	return refreshed


def create_additional_salaries(payroll_entry) -> dict:
	if isinstance(payroll_entry, str):
		payroll_entry = frappe.get_doc("Payroll Entry", payroll_entry)

	start_date = getdate(payroll_entry.start_date)
	end_date = getdate(payroll_entry.end_date)
	payroll_date = end_date
	company = payroll_entry.company

	components = get_attendance_driven_components()
	if not components:
		return {"created": [], "skipped": []}

	employees = [row.employee for row in (payroll_entry.employees or [])]
	if not employees:
		employees = _employees_in_payroll_entry(payroll_entry)

	created: list[dict] = []
	skipped: list[dict] = []
	for employee in employees:
		emp_doc = frappe.get_cached_doc("Employee", employee)
		emp_rows = get_employee_allowance_rows(employee, end_date)
		for sc in components:
			row = emp_rows.get(sc.name)
			if not is_tagged(employee, sc.name, row, end_date) or _skip_for_eligibility(emp_doc, sc):
				continue
			rate = _resolve_rate(row, sc, employee, end_date, emp_doc.company)
			if rate is None:
				continue
			qty = _qty_for_employee(employee, sc, *_attendance_period(sc, start_date, end_date))
			if qty <= 0:
				continue
			amount = flt(qty * rate, 2)
			if amount <= 0:
				continue

			# A savepoint is a SQL identifier, so anything but letters, digits and
			# underscores has to go: "Tea & Conveyance" made MariaDB reject the
			# whole statement and no allowance was ever written.
			savepoint = _savepoint_name(employee, sc.name)
			frappe.db.savepoint(savepoint)
			try:
				_delete_existing_draft(employee, sc.name, payroll_date)
				doc = _make_additional_salary(
					employee=employee,
					salary_component=sc,
					amount=amount,
					payroll_date=payroll_date,
					company=company,
					qty=qty,
					rate=rate,
				)
				created.append({
					"employee": employee,
					"salary_component": sc.name,
					"qty": qty,
					"rate": rate,
					"amount": amount,
					"additional_salary": doc.name,
				})
			except Exception as e:
				frappe.db.rollback(save_point=savepoint)
				skipped.append({
					"employee": employee,
					"salary_component": sc.name,
					"qty": qty,
					"rate": rate,
					"amount": amount,
					"reason": str(e),
				})
				frappe.log_error(
					message=frappe.get_traceback(),
					title=f"Nepal HRMS Attendance Allowance: {employee}/{sc.name}",
				)

	frappe.db.commit()
	if skipped:
		frappe.msgprint(
			_("{0} record(s) skipped (see Error Log for details).").format(len(skipped)),
			indicator="orange",
			alert=True,
		)
	return {"created": created, "skipped": skipped}


def _qty_for_employee(employee: str, sc, start_date, end_date) -> float:
	rows = _attendance_rows(employee, start_date, end_date)
	if not rows:
		return 0.0

	total = 0.0
	matched_any = False
	for row in rows:
		contribution = evaluate_rule(row, sc, employee)
		if contribution > 0:
			matched_any = True
			total += contribution

	if (sc.custom_unit or "Per Day") == "Flat per Period":
		return 1.0 if matched_any else 0.0
	return total


def evaluate_rule(row, sc, employee: str) -> float:
	condition = sc.custom_condition_type
	status = row.status
	working_hours = flt(row.working_hours)
	unit = sc.custom_unit or "Per Day"
	present_statuses = get_present_statuses()

	if condition in ("Status = Present", "Status = Half Day") and row.custom_worked_on_holiday:
		# A component earned by turning up need not be earned on a holiday: NGI's
		# sheet pays tea for working days only, and pays the holiday itself
		# through Worked on Holiday. Blank reads as Pay, so a component that has
		# never been asked the question keeps paying exactly what it paid.
		if (sc.get("custom_pay_on_holiday") or "Pay") == "Do Not Pay":
			return 0.0

	if condition == "Status = Present":
		if status in present_statuses:
			return _per_unit(unit, day=1.0, hours=working_hours)
		if status == "Half Day":
			# Tea and conveyance are earned by turning up, not by the hours: the
			# client's rule is that someone who comes gets the day (policy call,
			# 2026-09-21). A component that should pay half, or nothing, says so
			# on itself.
			counts = sc.get("custom_half_day_counts") or "Full Day"
			if counts == "Not At All":
				return 0.0
			return _per_unit(unit, day=0.5 if counts == "Half Day" else 1.0, hours=working_hours)
		return 0.0

	if condition == "Status = Half Day":
		return 1.0 if status == "Half Day" else 0.0

	if condition == "Worked on Holiday":
		if not row.custom_worked_on_holiday:
			return 0.0
		if status not in present_statuses and status != "Half Day":
			return 0.0
		return _per_unit(unit, day=1.0, hours=working_hours)

	if condition == "Meal Entitlement":
		return _meals_for_day(row, sc, present_statuses)

	if condition == "Authorised Overtime":
		# Policy 5.1: the per-day Overtime Sheet decides who is paid overtime and
		# for which day; the punches decide how many hours. Hours already rounded
		# to the half hour by settlement.
		return _authorised_overtime_hours(employee, row.attendance_date)

	if condition == "Late Time":
		# Late arrival plus leaving early, against the day's shift — the sheet's
		# "Late Time", and exactly the minutes the attendance report shows.
		if row.get("custom_late_excused"):
			# HR waived this day. The minutes stay on the row and in the reports;
			# they simply stop being charged.
			return 0.0
		measured = measure_day(row, is_holiday=bool(row.custom_worked_on_holiday))
		minutes = measured.late_minutes + measured.early_exit_minutes
		return _per_unit(unit, day=1.0 if minutes else 0.0, hours=minutes / 60)

	if condition in ("Early Entry Before", "Late Stay After", "Late Arrival After"):
		if condition == "Late Arrival After" and row.get("custom_late_excused"):
			return 0.0
		if condition == "Late Arrival After" and status == "Half Day":
			# Arriving more than two hours late already costs half the day's pay
			# (policy 1.2). Fining the same minutes again would charge the one
			# lateness twice; the fine is for lateness short of that line.
			return 0.0
		offset_seconds = flt(sc.custom_time_offset_hours) * 3600.0
		if condition == "Early Entry Before":
			seconds = flt(row.custom_early_entry)
		elif condition == "Late Stay After":
			seconds = flt(row.custom_late_exit)
		else:
			seconds = flt(row.custom_late_entry)
		if seconds <= 0 or seconds < offset_seconds:
			return 0.0
		return _per_unit(unit, day=1.0, hours=seconds / 3600.0)

	return 0.0


def _meals_for_day(row, sc, present_statuses) -> float:
	"""How many meals one attendance row earns (policy 1.3 / 2.3).

	Every number comes from the Meal Salary Component's own form, never from code:
	    Time Offset (Hours)          came this early / stayed this late -> 1 meal each
	    Holiday: Hours for 1 / 2     hours worked on a holiday -> 1 or 2 meals
	    Max Meals per Day            cap (0 = none)
	Seeded 1.5 / 6 / 8 / 2 by patches/setup_meal_rule_fields.py.

	A meal is earned by the extra time worked, not by turning up. Counting one
	per present day paid 132,525 against the sheet's 52,275 for Falgun 2082.
	"""
	if row.status not in present_statuses and row.status != "Half Day":
		return 0.0

	if row.custom_worked_on_holiday:
		worked = flt(row.working_hours)
		two, one = flt(sc.get("custom_holiday_hours_two_meals")), flt(sc.get("custom_holiday_hours_one_meal"))
		meals = 2 if two and worked >= two else 1 if one and worked >= one else 0
	else:
		offset = flt(sc.custom_time_offset_hours) * 3600.0
		meals = 0
		if offset:
			meals += flt(row.custom_early_entry) >= offset
			meals += flt(row.custom_late_exit) >= offset

	cap = cint(sc.get("custom_max_per_day"))
	return float(min(meals, cap) if cap else meals)


def _authorised_overtime_hours(employee: str, work_date) -> float:
	"""Hours authorised on a submitted Overtime Sheet and backed by the punches.

	Cached per request: the report asks once per employee per day.
	"""
	cache = getattr(frappe.local, "_agp_authorised_ot", None)
	if cache is None:
		cache = frappe.local._agp_authorised_ot = {}
	key = (employee, getdate(work_date))
	if key not in cache:
		cache[key] = flt(
			frappe.db.sql(
				"""select sum(r.worked_hours)
				from `tabOvertime Sheet Employee` r
				join `tabOvertime Sheet` s on s.name = r.parent
				where s.docstatus = 1 and r.employee = %s and s.work_date = %s
				  and r.entitlement = %s""",
				(employee, key[1], ENTITLEMENT_OVERTIME),
			)[0][0]
		)
	return cache[key]


#: The Labour Act's hourly wage: a month's basic over 30 days of 8 hours. The
#: sheet prices overtime at 1.5 times this, and a late minute at 1/60th of it.
#: Fallbacks only — the divisors are fields on the Salary Component, seeded with
#: these by patches/setup_ot_rate_fields.py. A blank field falls back here
#: rather than dividing by zero.
RATE_DAYS_PER_MONTH = 30
RATE_HOURS_PER_DAY = 8


def _assignment(employee: str, on_date):
	return frappe.db.get_value(
		"Salary Structure Assignment",
		{"employee": employee, "docstatus": 1, "from_date": ["<=", getdate(on_date)]},
		["base", "salary_structure"],
		as_dict=True,
		order_by="from_date desc",
	) or frappe._dict(base=0, salary_structure=None)


def _hourly_basic(employee: str, on_date, sc=None) -> float:
	"""The hourly wage: a month's basic over 30 days of 8 hours.

	Daily-wage labour is paid in cash day to day, outside payroll (decided
	2026-10-08), so every assignment's base here is a monthly basic.

	Both divisors come off the Salary Component that is being priced, so HR can
	restate the basis for overtime without touching the late fine, or either
	without a developer.
	"""
	days = flt(sc and sc.get("custom_rate_days_per_month")) or RATE_DAYS_PER_MONTH
	hours = flt(sc and sc.get("custom_rate_hours_per_day")) or RATE_HOURS_PER_DAY
	return flt(_assignment(employee, on_date).base) / days / hours


def _per_unit(unit: str, day: float, hours: float) -> float:
	if unit == "Per Hour":
		return flt(hours)
	if unit == "Flat per Period":
		return 1.0 if day > 0 else 0.0
	return flt(day)


def _employee_holiday_list(employee: str) -> str:
	emp = frappe.get_cached_doc("Employee", employee)
	if emp.holiday_list:
		return emp.holiday_list
	company = emp.company
	if not company:
		return ""
	return frappe.db.get_value("Company", company, "default_holiday_list") or ""


def set_holiday_flag(doc, _method=None):
	"""doc_event hook on Attendance.validate.

	Auto-populates the read-only `custom_worked_on_holiday` checkbox by checking
	whether the attendance_date matches a Holiday row in the employee's
	Holiday List (or the company's default Holiday List if the employee has none).
	"""
	if not (doc.employee and doc.attendance_date):
		doc.custom_worked_on_holiday = 0
		return

	emp = frappe.get_cached_doc("Employee", doc.employee)
	holiday_list = emp.holiday_list or (
		frappe.db.get_value("Company", emp.company, "default_holiday_list")
		if emp.company else None
	)

	doc.custom_worked_on_holiday = 1 if (
		holiday_list and frappe.db.exists("Holiday", {
			"parent": holiday_list,
			"holiday_date": doc.attendance_date,
		})
	) else 0


@frappe.whitelist()
def recompute_holiday_flags(start_date=None, end_date=None) -> dict:
	"""Re-evaluate `custom_worked_on_holiday` on existing Attendance rows.

	Run after editing a Holiday List, or as a one-time backfill on patch install.
	If no dates passed, scans every Attendance row.
	"""
	filters = {}
	if start_date and end_date:
		filters["attendance_date"] = ["between", [start_date, end_date]]
	rows = frappe.get_all(
		"Attendance",
		filters=filters,
		fields=["name", "employee", "attendance_date", "custom_worked_on_holiday"],
	)
	updated = 0
	for r in rows:
		if not r.employee or not r.attendance_date:
			continue
		holiday_list = _employee_holiday_list(r.employee)
		new_flag = 0
		if holiday_list and frappe.db.exists(
			"Holiday",
			{"parent": holiday_list, "holiday_date": r.attendance_date},
		):
			new_flag = 1
		if (r.custom_worked_on_holiday or 0) != new_flag:
			frappe.db.set_value(
				"Attendance",
				r.name,
				"custom_worked_on_holiday",
				new_flag,
				update_modified=False,
			)
			updated += 1
	frappe.db.commit()
	return {"scanned": len(rows), "updated": updated}


def _skip_for_eligibility(emp_doc, sc) -> bool:
	if sc.get("custom_ot_eligible_only") and not emp_doc.get("custom_ot_eligibility"):
		# Policy 2.2: overtime money and meals are for OT-eligible staff; admin
		# and officers take replacement leave instead.
		return True
	if sc.custom_condition_type in ("Late Time", "Late Arrival After"):
		# NGI's sheet types the late rate as 0 for its managers — CEO, AGM,
		# managers, assistant managers, the company secretary. That is a person-
		# level decision, so it is a tick on the Employee.
		return bool(emp_doc.get("custom_late_fine_exempt"))
	return False


def _attendance_period(sc, start_date, end_date):
	"""The days a component counts: the payroll's own BS month, or the one
	before it for a component whose attendance closes a month behind."""
	if sc.get("custom_attendance_month") != "Previous Month":
		return start_date, end_date
	from rdp_common_app.utils.bs_boundaries import get_bs_month_end, get_bs_month_start

	last_day = add_days(start_date, -1)
	return getdate(get_bs_month_start(last_day)), getdate(get_bs_month_end(last_day))


def get_attendance_driven_components() -> list:
	names = frappe.get_all(
		"Salary Component",
		filters={"custom_is_attendance_driven": 1, "disabled": 0},
		pluck="name",
	)
	return [frappe.get_cached_doc("Salary Component", n) for n in names]


def _attendance_rows(employee: str, start_date, end_date) -> list:
	return frappe.get_all(
		"Attendance",
		filters={
			"employee": employee,
			"attendance_date": ["between", [start_date, end_date]],
			"docstatus": 1,
		},
		fields=[
			"name",
			"attendance_date",
			"status",
			"working_hours",
			"custom_worked_on_holiday",
			"custom_late_entry",
			"custom_early_entry",
			"custom_early_exit",
			"custom_late_exit",
			"custom_late_excused",
			"in_time",
			"out_time",
		],
	)


def _savepoint_name(employee: str, component: str) -> str:
	"""A SQL-safe savepoint name for one employee/component attempt."""
	raw = f"naa_{employee}_{component}"
	return "".join(ch if ch.isalnum() else "_" for ch in raw)[:60]


def _resolve_rate(row, sc, employee=None, on_date=None, company=None):
	"""The employee's own rate, then the company's, then the component's basis.

	Most allowances pay a flat rate: tea at the company's 235 a day (NGN: 265),
	typed as Default Rate on the component's Accounts row for that company; NEW
	staff carry 40 on their own row. Overtime and the late fine are priced off
	each person's own basic instead — `Hourly Basic × Multiplier` — so they
	follow a pay rise without anyone retyping a rate.
	"""
	if row is not None and flt(row.get("rate")):
		return flt(row.get("rate"))

	company_rate = company_default_rate(company, sc.name)
	if company_rate:
		return company_rate

	if sc.get("custom_rate_basis") == "Hourly Basic × Multiplier" and employee:
		# Unrounded: the sheet multiplies the full-precision rate by the hours,
		# and rounding the rate first drifts the amount by a paisa.
		rate = _hourly_basic(employee, on_date, sc) * flt(sc.get("custom_rate_multiplier") or 1)
		return rate if rate else None

	default_rate = flt(getattr(sc, "custom_default_rate", 0))
	return default_rate if default_rate else None


def _employees_in_payroll_entry(pe) -> list:
	return frappe.get_all(
		"Payroll Employee Detail",
		filters={"parent": pe.name, "parenttype": "Payroll Entry"},
		pluck="employee",
	)


def _delete_existing_draft(employee: str, salary_component: str, payroll_date) -> None:
	"""Clear a previous run's row for this employee, component and month.

	Submitted ones are cancelled first: the calculator submits what it creates, so
	a re-run would otherwise leave the old amount standing beside the new one.
	Only rows this calculator made are touched — anything HR typed by hand keeps
	its own tag and is left alone.
	"""
	existing = frappe.get_all(
		"Additional Salary",
		filters={
			"employee": employee,
			"salary_component": salary_component,
			"payroll_date": payroll_date,
			"docstatus": ["<", 2],
			"custom_source": SOURCE_TAG,
		},
		fields=["name", "docstatus"],
	)
	for row in existing:
		if row.docstatus == 1:
			doc = frappe.get_doc("Additional Salary", row.name)
			doc.flags.ignore_permissions = True
			doc.cancel()
		frappe.delete_doc("Additional Salary", row.name, force=True, ignore_permissions=True)


def _make_additional_salary(
	employee: str,
	salary_component,
	amount: float,
	payroll_date,
	company: str,
	qty: float,
	rate: float,
):
	doc = frappe.new_doc("Additional Salary")
	doc.employee = employee
	doc.salary_component = salary_component.name
	doc.amount = amount
	doc.payroll_date = payroll_date
	doc.company = company
	doc.type = salary_component.type or "Earning"
	doc.is_recurring = 0
	doc.overwrite_salary_structure_amount = 0
	# Taxed in the month it is paid. Left to HRMS's default, a one-off is taxed
	# as if the rest of the year paid nothing: a labourer's 7,068.75 month drew
	# 6 of tax instead of the sheet's 1%, 70.69.
	doc.deduct_full_tax_on_selected_payroll_date = 1 if doc.type == "Earning" else 0
	doc.custom_source = SOURCE_TAG
	doc.notes = (
		f"Auto-generated by Nepal HRMS attendance allowance calculator. "
		f"qty={qty} × rate={rate} = {amount} "
		f"(condition: {salary_component.custom_condition_type}, unit: {salary_component.custom_unit or 'Per Day'})"
	)
	doc.flags.ignore_permissions = True
	doc.insert()
	# Submitted, not left as a draft: a draft Additional Salary is invisible to
	# the salary slip, so the first full payroll run produced slips with no tea
	# on them at all. Re-running replaces these, cancelling as it goes.
	doc.submit()
	return doc
