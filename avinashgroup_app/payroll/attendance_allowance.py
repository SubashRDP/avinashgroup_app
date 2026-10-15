"""Calculator: Attendance + per-employee rates → Additional Salary.

Per Payroll Entry:
1. List Salary Components where `custom_is_attendance_driven = 1` and not disabled.
2. For each (employee, component), skip anyone who does not get it — an
   allowance needs a row on their salary assignment (payroll/allowance.py); any
   other component a row in their salary structure. The late fine (Late Time)
   needs neither: everyone is fined except those ticked Late Fine Exempt.
   Overtime (Authorised Overtime) needs neither either: anyone OT eligible on a
   submitted Overtime Sheet is paid. And, for an "Only OT-Eligible Staff"
   component, anyone not OT eligible.
3. Evaluate the component's condition against the employee's submitted
   Attendance rows in the period — the payroll's BS month, or the one before
   it when the component's Attendance Month says so — and sum the qty.
4. Multiply qty × rate: the Rate on the person's assignment row, or, for a
   component priced Hourly Basic × Multiplier (overtime), the person's own
   basic per hour times the multiplier. The late fine is always priced that
   way, whatever its Unit and Rate Basis say: minutes late × basic per minute.
   Overtime always is too: sheet hours × hourly basic × 1.5 (`overtime_rate`,
   which the Monthly Attendance BS report shows beside the hours).
5. Create and submit an Additional Salary per (employee, component,
   payroll_date), tagged with `custom_source = "Nepal HRMS Attendance
   Allowance"`. Idempotent: earlier rows with the same tag are replaced.
"""

import frappe
from frappe import _
from frappe.utils import add_days, cint, date_diff, flt, getdate

from avinashgroup_app.hr.overtime import ENTITLEMENT_OVERTIME
from avinashgroup_app.hr.shift_day import holiday_hours_worked, measure_day
from avinashgroup_app.payroll.allowance import (
	COMPUTED_RATE_BASIS,
	get_employee_allowance_rows,
	structure_components,
)

SOURCE_TAG = "Nepal HRMS Attendance Allowance"

#: The late-fine condition: late arrival plus leaving early, fined per minute
#: off the person's basic, for everyone not Late Fine Exempt.
LATE_TIME = "Late Time"

#: The overtime condition: hours on a submitted Overtime Sheet, paid to anyone
#: OT eligible at 1.5 times their hourly basic (user, 2026-10-14; the Labour
#: Act's rate). No row on the assignment, Rate Basis or Multiplier to set.
AUTHORISED_OVERTIME = "Authorised Overtime"
OVERTIME_MULTIPLIER = 1.5

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
	# The engine writes with ignore_permissions, so the caller's rights are
	# checked here: someone who may read this entry and create Additional Salary.
	pe.check_permission("read")
	frappe.has_permission("Additional Salary", "create", throw=True)
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
		"cleared": len(result["cleared"]),
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


def refresh_slips_covering(employees, on_date) -> int:
	"""Re-save these employees' draft salary slips whose period covers `on_date`.

	For documents that post one Additional Salary after the slips exist
	(Payroll Adjustment, Leave Encashment): without it the draft slip shows the
	payment only when someone next saves it. Submitted slips are never touched.
	"""
	if not employees:
		return 0
	refreshed = 0
	for name in frappe.get_all(
		"Salary Slip",
		filters={
			"employee": ("in", list(employees)),
			"docstatus": 0,
			"start_date": ("<=", getdate(on_date)),
			"end_date": (">=", getdate(on_date)),
		},
		pluck="name",
	):
		slip = frappe.get_doc("Salary Slip", name)
		slip.flags.ignore_permissions = True
		slip.save()
		refreshed += 1
	return refreshed


def create_additional_salaries(payroll_entry, commit: bool = True) -> dict:
	"""Post the month's attendance-driven pay as Additional Salary. `commit=False`
	when called inside another document's submit, so that submit stays atomic."""
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
	cleared: list[dict] = []
	for employee in employees:
		emp_doc = frappe.get_cached_doc("Employee", employee)
		emp_rows = get_employee_allowance_rows(employee, end_date)
		for sc in components:
			qty, rate, amount = _priced(employee, emp_doc, sc, emp_rows.get(sc.name), start_date, end_date)

			# A savepoint is a SQL identifier, so anything but letters, digits and
			# underscores has to go: "Tea & Conveyance" made MariaDB reject the
			# whole statement and no allowance was ever written.
			savepoint = _savepoint_name(employee, sc.name)
			frappe.db.savepoint(savepoint)
			try:
				# The last press's row goes first, whatever this press finds: when a
				# corrected attendance, a stopped allowance or a lost eligibility
				# brings the amount to nothing, the old figure must not stay paid.
				removed = _delete_existing_draft(employee, sc.name, payroll_date)
				if not amount:
					if removed:
						cleared.append({"employee": employee, "salary_component": sc.name, "removed": removed})
					continue
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

	if commit:
		frappe.db.commit()
	if skipped:
		frappe.msgprint(
			_("{0} record(s) skipped (see Error Log for details).").format(len(skipped)),
			indicator="orange",
			alert=True,
		)
	return {"created": created, "skipped": skipped, "cleared": cleared}


def _priced(employee: str, emp_doc, sc, row, start_date, end_date) -> tuple:
	"""(qty, rate, amount) this person earns from the component this month; amount 0 when nothing."""
	if not _gets(employee, sc, row, end_date) or _skip_for_eligibility(emp_doc, sc):
		return 0, None, 0
	period = _attendance_period(sc, start_date, end_date)
	rate = _resolve_rate(row, sc, employee, end_date, month_days=date_diff(period[1], period[0]) + 1)
	if rate is None:
		return 0, None, 0
	qty = _qty_for_employee(employee, sc, *period)
	if qty <= 0:
		return qty, rate, 0
	return qty, rate, max(flt(qty * rate, 2), 0)


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

	# Overtime, the late fine and meals count hours or meals and hide Unit on
	# the form; a Unit left over from before must not turn them into a flat 1.
	if sc.custom_condition_type not in (AUTHORISED_OVERTIME, LATE_TIME, "Meal Entitlement") and (
		sc.custom_unit or "Per Day"
	) == "Flat per Period":
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
		return _meals_for_day(row, sc, present_statuses, employee)

	if condition == AUTHORISED_OVERTIME:
		# Policy 5.1: the per-day Overtime Sheet decides who is paid overtime and
		# for which day; the punches decide how many hours, exact to the
		# second (settlement never rounds).
		return _authorised_overtime_hours(employee, row.attendance_date)

	if condition == LATE_TIME:
		# Late arrival plus leaving early, against the day's shift — the sheet's
		# "Late Time", and exactly the minutes the attendance report shows.
		if row.get("custom_late_excused"):
			# HR waived this day. The minutes stay on the row and in the reports;
			# they simply stop being charged.
			return 0.0
		measured = measure_day(row, is_holiday=bool(row.custom_worked_on_holiday))
		# Always in hours, minute for minute — never a whole day for any
		# lateness — whatever the component's Unit says (user, 2026-10-14).
		return (measured.late_minutes + measured.early_exit_minutes) / 60

	if condition in ("Early Entry Before", "Late Stay After", "Late Arrival After"):
		if condition == "Late Arrival After" and row.get("custom_late_excused"):
			return 0.0
		if condition == "Late Arrival After" and row.custom_worked_on_holiday:
			# A holiday has no start time to be late for (shift_day.measure_day,
			# the late fine, the half-day rule all agree).
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


def _meals_for_day(row, sc, present_statuses, employee: str) -> float:
	"""How many meals one attendance row earns.

	A meal is part of overtime the company asked for, not of turning up early
	or staying late on one's own (the user's rule of 2026-10-09; policy 1.3,
	2.2, 2.3, 5.1):

	  * only an OT-eligible employee (Employee → OT Eligible), and only on a
	    day a submitted Overtime Sheet names them with the Overtime entitlement;
	  * a working day: called in Time Offset (1.5 h) or more before the shift →
	    1 meal; kept that long after it → 1 meal;
	  * a holiday worked on such a sheet: by the hours worked, first IN to last
	    OUT — 8 h → 2 meals, 6 h → 1, less → none (HOLIDAY_MEAL_HOURS);
	  * never more than Max Meals per Day (2).

	Early and late are the day's own measures against its shift
	(`custom_early_entry` / `custom_late_exit`, biometric/attendance_override.py).
	"""
	if row.status not in present_statuses and row.status != "Half Day":
		return 0.0
	if not frappe.get_cached_value("Employee", employee, "custom_ot_eligibility"):
		return 0.0
	if not _on_overtime_sheet(employee, row.attendance_date):
		return 0.0

	if row.custom_worked_on_holiday:
		meals = holiday_meals(holiday_hours_worked(row))
	else:
		offset = flt(sc.custom_time_offset_hours) * 3600.0
		meals = 0
		if offset:
			meals += flt(row.custom_early_entry) >= offset
			meals += flt(row.custom_late_exit) >= offset

	cap = cint(sc.get("custom_max_per_day"))
	return float(min(meals, cap) if cap else meals)


#: Meals for a holiday worked on an authorised Overtime Sheet, by the hours
#: actually worked, first IN to last OUT (user, 2026-10-15): 8 hours or more → 2,
#: 6 or more → 1, less → none. Replaced a flat 2 (2026-10-09). Highest first.
#: The hours are exact, as the overtime they come with is: 7:53 is under 8 hours,
#: so one meal (user, 2026-10-15: overtime never rounds up or down).
HOLIDAY_MEAL_HOURS = ((8, 2), (6, 1))


def holiday_meals(hours: float) -> int:
	"""Meals earned by `hours` worked on a holiday (HOLIDAY_MEAL_HOURS)."""
	for threshold, meals in HOLIDAY_MEAL_HOURS:
		if flt(hours) >= threshold:
			return meals
	return 0


def _on_overtime_sheet(employee: str, work_date) -> bool:
	"""Whether a submitted Overtime Sheet names the employee on that date with
	the Overtime entitlement — the company called them in (policy 5.1).

	A row is enough: a holiday authorisation counts before its hours are
	settled. Cached per request: the report asks once per employee per day.
	"""
	cache = getattr(frappe.local, "_agp_on_ot_sheet", None)
	if cache is None:
		cache = frappe.local._agp_on_ot_sheet = {}
	key = (employee, getdate(work_date))
	if key not in cache:
		cache[key] = bool(
			frappe.db.sql(
				"""select 1
				from `tabOvertime Sheet Employee` r
				join `tabOvertime Sheet` s on s.name = r.parent
				where s.docstatus = 1 and r.employee = %s and s.work_date = %s
				  and r.entitlement = %s
				limit 1""",
				(employee, key[1], ENTITLEMENT_OVERTIME),
			)
		)
	return cache[key]


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


#: The hourly wage is a month's basic over the days of that BS month (29–32) and
#: 8 hours a day — the same month length the slip prorates Basic by (decided by
#: the user 2026-10-12; the client's Excel sheets used a flat 30). Overtime is
#: 1.5 times it, a late minute 1/60th of it. "Rate: Days per Month" on the Salary
#: Component, when filled, fixes the days instead (30 restores the sheets' rule);
#: "Rate: Hours per Day" blank falls back to 8.
RATE_HOURS_PER_DAY = 8


def _assignment(employee: str, on_date):
	return frappe.db.get_value(
		"Salary Structure Assignment",
		{"employee": employee, "docstatus": 1, "from_date": ["<=", getdate(on_date)]},
		["base", "salary_structure"],
		as_dict=True,
		order_by="from_date desc",
	) or frappe._dict(base=0, salary_structure=None)


def _hourly_basic(employee: str, on_date, sc=None, month_days: int | None = None) -> float:
	"""The hourly wage: a month's basic over the month's days of 8 hours.

	`month_days` is the length of the BS month whose attendance is being priced
	(29–32). A fixed "Rate: Days per Month" on the component overrides it.

	Daily-wage labour is paid in cash day to day, outside payroll (decided
	2026-10-08), so every assignment's base here is a monthly basic.

	Both divisors come off the Salary Component that is being priced, so HR can
	restate the basis for overtime without touching the late fine, or either
	without a developer.
	"""
	days = flt(sc and sc.get("custom_rate_days_per_month")) or flt(month_days)
	if not days:
		frappe.throw(_("Cannot work out the hourly wage for {0}: no month length given").format(employee))
	hours = flt(sc and sc.get("custom_rate_hours_per_day")) or RATE_HOURS_PER_DAY
	return flt(_assignment(employee, on_date).base) / days / hours


def overtime_rate(employee: str, on_date, month_days: int, sc=None) -> float:
	"""One overtime hour: the person's hourly basic × 1.5. 0 without a salary assignment.

	The one place overtime is priced, read by `_resolve_rate` for pay and by the
	Monthly Attendance BS report for its O.T. Rate and O.T. Amount columns, so
	the two never disagree. `month_days` is the BS month's length (29–32); the
	component's "Rate: Days / Hours" still override 30-odd days and 8 hours.
	"""
	return _hourly_basic(employee, on_date, sc, month_days) * OVERTIME_MULTIPLIER


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


def resync_holiday_flags(doc, method=None):
	"""doc_event hook on Holiday List.on_update: keep `custom_worked_on_holiday`
	true to the list after the list itself is edited.

	The flag is written once, when the Attendance is saved, and copies whether
	the date was a holiday THEN. Adding a festival to the list afterwards, or
	moving it, left every row on that date describing a working day — so the
	holiday tea/meal rules, holiday OT and the Work On Holiday report missed the
	people who came in (Bheshraj NGI-EMP-00009: Janai Purnima and Janmasthami
	worked, flags 0, because the list was edited after his Bhadra attendance).
	Holiday Bulk Update already follows up a past date (hr/holiday_backdate.py);
	this covers an edit made on the list itself, in either direction.

	Only the dates that changed, only up to today (later dates have no
	attendance yet), only employees this list applies to (their own list, else
	their company's default). A flag write, nothing else: status and absences on
	those days stay holiday_backdate's and Attendance Fix's business. A submitted
	salary slip is not recalculated by this; it is what was paid.
	"""
	before = doc.get_doc_before_save()
	old = {getdate(h.holiday_date) for h in (before.holidays if before else [])}
	new = {getdate(h.holiday_date) for h in doc.holidays}
	changed = sorted(d for d in old ^ new if d <= getdate())
	if not changed:
		return

	companies = frappe.get_all("Company", filters={"default_holiday_list": doc.name}, pluck="name")
	employees = frappe.get_all(
		"Employee",
		or_filters=[["holiday_list", "=", doc.name]]
		+ ([["company", "in", companies]] if companies else []),
		fields=["name", "holiday_list"],
	)
	names = [e.name for e in employees if not e.holiday_list or e.holiday_list == doc.name]
	if not names:
		return
	rows = frappe.get_all(
		"Attendance",
		filters={"employee": ("in", names), "attendance_date": ("in", changed), "docstatus": ("<", 2)},
		fields=["name", "attendance_date", "custom_worked_on_holiday"],
	)
	for r in rows:
		flag = 1 if getdate(r.attendance_date) in new else 0
		if cint(r.custom_worked_on_holiday) != flag:
			frappe.db.set_value("Attendance", r.name, "custom_worked_on_holiday", flag, update_modified=False)


@frappe.whitelist()
def recompute_holiday_flags(start_date=None, end_date=None) -> dict:
	"""Re-evaluate `custom_worked_on_holiday` on existing Attendance rows.

	Run after editing a Holiday List, or as a one-time backfill on patch install.
	If no dates passed, scans every Attendance row.
	"""
	# Writes with set_value (no permission check), so the caller's is checked here.
	frappe.has_permission("Attendance", "write", throw=True)
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
	# The late fine is for everyone not exempt, so a tick left on it (the form
	# no longer shows the box there) must not narrow it to OT-eligible staff.
	condition = sc.get("custom_condition_type")
	ot_only = condition == AUTHORISED_OVERTIME or (
		condition != LATE_TIME and sc.get("custom_ot_eligible_only")
	)
	if ot_only and not emp_doc.get("custom_ot_eligibility"):
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


def _gets(employee: str, sc, row, on_date) -> bool:
	"""Whether this person is paid the component at all.

	The late fine (Late Time): everyone. Its only exception is Late Fine Exempt
	on the Employee, checked in `_skip_for_eligibility` (user, 2026-10-14: no
	tag to forget on a structure). An allowance: a row on their salary
	assignment — no row, not paid. Any other attendance component: a row in
	their salary structure's Deductions tags it.
	"""
	if sc.get("custom_condition_type") in (LATE_TIME, AUTHORISED_OVERTIME):
		# Overtime's own gate is OT eligibility (`_skip_for_eligibility`) and the
		# Overtime Sheet (the quantity is 0 without one).
		return True
	if sc.get("custom_is_allowance"):
		return row is not None
	return sc.name in structure_components(employee, on_date)


def _resolve_rate(row, sc, employee=None, on_date=None, month_days=None):
	"""The rate per unit: the person's own Rate, or worked out from their basic.

	Tea and meal pay the Rate on the person's assignment row (235 a day at NGI,
	40 for new staff). Overtime and the late fine are priced off each person's
	own basic instead — `Hourly Basic × Multiplier` — so they follow a pay rise
	without anyone retyping a rate. None when there is nothing to price by.

	The late fine is always priced off the basic, at its multiplier (blank = 1),
	so a component left on Fixed Rate still charges what lateness costs: an
	hour's basic per hour late, i.e. basic ÷ month days ÷ 8 ÷ 60 per minute.
	"""
	if sc.get("custom_condition_type") == AUTHORISED_OVERTIME and employee:
		rate = overtime_rate(employee, on_date, month_days, sc)
		return rate if rate else None

	computed = sc.get("custom_rate_basis") == COMPUTED_RATE_BASIS or sc.get("custom_condition_type") == LATE_TIME
	if computed and employee:
		# Unrounded: the sheet multiplies the full-precision rate by the hours,
		# and rounding the rate first drifts the amount by a paisa.
		rate = _hourly_basic(employee, on_date, sc, month_days) * flt(sc.get("custom_rate_multiplier") or 1)
		return rate if rate else None

	if row is not None and flt(row.get("rate")):
		return flt(row.get("rate"))

	return None


def _employees_in_payroll_entry(pe) -> list:
	return frappe.get_all(
		"Payroll Employee Detail",
		filters={"parent": pe.name, "parenttype": "Payroll Entry"},
		pluck="employee",
	)


def _delete_existing_draft(employee: str, salary_component: str, payroll_date) -> int:
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
		# A draft slip made from the old row still links it, and could then never
		# be saved or submitted again ("Could not find Additional Salary"). Drop
		# that line; the slip's next save adds the new row's line in its place.
		frappe.db.sql(
			"""delete sd from `tabSalary Detail` sd
			join `tabSalary Slip` ss on ss.name = sd.parent and sd.parenttype = 'Salary Slip'
			where sd.additional_salary = %s and ss.docstatus = 0""",
			row.name,
		)
		if row.docstatus == 1:
			doc = frappe.get_doc("Additional Salary", row.name)
			doc.flags.ignore_permissions = True
			doc.cancel()
		frappe.delete_doc("Additional Salary", row.name, force=True, ignore_permissions=True)
	return len(existing)


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
	# Kept for the salary sheet (OT hours, meals, late hours): Avinas Salary
	# Statement reads them. Patch setup_additional_salary_quantity.
	doc.custom_quantity = qty
	doc.custom_rate = rate
	doc.flags.ignore_permissions = True
	doc.insert()
	# Submitted, not left as a draft: a draft Additional Salary is invisible to
	# the salary slip, so the first full payroll run produced slips with no tea
	# on them at all. Re-running replaces these, cancelling as it goes.
	doc.submit()
	return doc
