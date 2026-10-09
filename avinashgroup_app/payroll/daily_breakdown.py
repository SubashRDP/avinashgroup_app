"""The salary slip, day by day: what each day earned and cost, to the net pay.

A slip shows monthly totals: Basic, tea, meal, overtime, late fine, SSF, tax.
An employee asking "why is my tea 2,115 and not 2,350?" or "where did 1,500
go?" had no answer on the slip itself. This builds the slip's Daily Breakdown
table (`custom_daily_breakdown`, child Salary Slip Day): one row per day of the
slip's period with that day's attendance, its share of fixed pay, the tea,
meals and overtime it earned, the late fine it cost, and a running balance;
then month-end rows for what is monthly (SSF, tax, advances, arrears).

It reconciles to the slip by construction, never by a second calculation:

  * fixed pay — the slip's own daily rate (its prorated non-additional
    earnings ÷ its payment days) times each day's weight (absent 0, half day
    0.5, leave without pay 0, holiday and paid leave 1, unmarked per Payroll
    Settings);
  * attendance items — each Additional Salary that Prepare Payroll Inputs
    posted, spread over the days by the same rule that counted it
    (attendance_allowance.evaluate_rule), at that line's own unit amount;
  * a Rounding row when paisa remain, so the last balance is net pay. A
    bigger gap is labelled Adjustment: the days' weights disagree with the
    slip's payment days (attendance changed after the slip was made), and it
    shows instead of hiding inside every day.

Hook: doc_events → Salary Slip → validate, last in the chain (it needs the
final net pay). Rebuilt on every save, so the table is frozen at submit with
the slip. It only describes the slip: a failure is logged against the slip and
never blocks a save. Printed by templates/print_formats/salary_slip_bs.html.
"""

import frappe
from frappe.utils import add_days, date_diff, flt, format_time, getdate

from rdp_common_app.utils.bs_boundaries import ad_to_bs, get_bs_month_name

from avinashgroup_app.hr.utils import resolve_holiday_lists
from avinashgroup_app.payroll.attendance_allowance import (
	SOURCE_TAG,
	_attendance_period,
	evaluate_rule,
)

DAY = "Day"
MONTH_END = "Month End"
#: Attendance fields the day rows and the attendance rules read.
ATTENDANCE_FIELDS = (
	"name",
	"attendance_date",
	"status",
	"leave_type",
	"half_day_status",
	"working_hours",
	"custom_worked_on_holiday",
	"custom_late_entry",
	"custom_early_entry",
	"custom_early_exit",
	"custom_late_exit",
	"custom_late_excused",
	"in_time",
	"out_time",
)


def build_daily_breakdown(doc, method=None):
	"""Hook: Salary Slip validate (last). Never blocks the save."""
	if doc.docstatus == 2 or not doc.employee or not doc.start_date or not doc.end_date:
		return
	if not doc.meta.has_field("custom_daily_breakdown"):
		return
	try:
		doc.set("custom_daily_breakdown", breakdown_rows(doc))
	except Exception:
		frappe.log_error(title=f"Daily breakdown failed for {doc.name or doc.employee}", message=frappe.get_traceback())


def breakdown_rows(doc) -> list:
	start, end = getdate(doc.start_date), getdate(doc.end_date)
	days = [add_days(start, i) for i in range(date_diff(end, start) + 1)]
	attendance = {getdate(a.attendance_date): a for a in fetch_attendance(doc.employee, start, end)}
	holidays = fetch_holidays(doc.employee, start, end)
	weights = {d: paid_weight(doc, d, attendance.get(d), d in holidays) for d in days}

	# Fixed pay: the slip's own prorated earnings, spread by paid weight.
	fixed_total = sum(
		flt(e.amount) for e in doc.earnings if not e.additional_salary and not e.get("statistical_component")
	)
	payment_days = flt(doc.payment_days) or sum(weights.values())
	daily_rate = fixed_total / payment_days if payment_days else 0
	fixed = {d: daily_rate * weights[d] for d in days}

	earned = {d: 0.0 for d in days}
	deducted = {d: 0.0 for d in days}
	details = {d: [] for d in days}
	month_end = []

	tagged = attendance_additional_salaries(doc)
	for table, sign in (("earnings", 1), ("deductions", -1)):
		for row in doc.get(table):
			if row.get("statistical_component") or row.get("do_not_include_in_total") or not flt(row.amount):
				continue
			if table == "earnings" and not row.additional_salary:
				continue  # fixed pay, spread above
			if row.additional_salary in tagged and spread_over_days(
				doc, row, sign, attendance, days, earned, deducted, details
			):
				continue
			month_end.append((row.salary_component, flt(row.amount) if sign > 0 else 0, flt(row.amount) if sign < 0 else 0))

	if flt(doc.get("total_loan_repayment")):
		month_end.append(("Loan Repayment", 0, flt(doc.total_loan_repayment)))

	rows, balance = [], 0.0
	for d in days:
		att = attendance.get(d)
		day_total = flt(fixed[d], 2) + flt(earned[d], 2) - flt(deducted[d], 2)
		balance += day_total
		rows.append(
			{
				"line_type": DAY,
				"date": d,
				"miti": miti_label(d),
				"weekday": d.strftime("%a"),
				"attendance": attendance_label(doc, d, att, holidays.get(d)),
				"paid_day": weights[d],
				"fixed_pay": flt(fixed[d], 2),
				"earned": flt(earned[d], 2),
				"deducted": flt(deducted[d], 2),
				"detail": " · ".join(details[d]),
				"day_total": flt(day_total, 2),
				"balance": flt(balance, 2),
				"currency": doc.currency,
			}
		)
	for label, plus, minus in month_end:
		balance += plus - minus
		rows.append(month_end_row(doc, label, plus, minus, balance))

	difference = flt(flt(doc.net_pay) - balance, 2)
	if abs(difference) >= 0.01:
		balance += difference
		label = "Rounding" if abs(difference) < 1 else "Adjustment: attendance differs from the slip's payment days"
		rows.append(month_end_row(doc, label, max(difference, 0), max(-difference, 0), balance))
	return rows


def month_end_row(doc, label, plus, minus, balance) -> dict:
	return {
		"line_type": MONTH_END,
		"attendance": label,
		"earned": flt(plus, 2),
		"deducted": flt(minus, 2),
		"day_total": flt(plus - minus, 2),
		"balance": flt(balance, 2),
		"currency": doc.currency,
	}


def spread_over_days(doc, row, sign, attendance, days, earned, deducted, details) -> bool:
	"""Put one attendance-posted line on the days that earned it.

	Returns False (the line goes to month end) when it counted another month's
	attendance, or no day of this period produced a quantity.
	"""
	sc = frappe.get_cached_doc("Salary Component", row.salary_component)
	if tuple(map(getdate, _attendance_period(sc, getdate(doc.start_date), getdate(doc.end_date)))) != (
		getdate(doc.start_date),
		getdate(doc.end_date),
	):
		return False
	qty = {d: flt(evaluate_rule(attendance[d], sc, doc.employee)) for d in days if d in attendance}
	total = sum(qty.values())
	if not total:
		return False
	unit = flt(row.amount) / total
	target = earned if sign > 0 else deducted
	for d, q in qty.items():
		if not q:
			continue
		amount = q * unit
		target[d] += amount
		details[d].append(describe(sc, q, unit, amount, sign))
	return True


def describe(sc, qty, unit, amount, sign) -> str:
	"""'Tea 235', 'Meal 2 × 75 = 150', 'Overtime 1.5 h = 412.50', 'Late Fine 40 min −42.10'."""
	name = sc.name
	money = f"{'−' if sign < 0 else ''}{flt(amount, 2):,.2f}".replace(".00", "")
	if sc.get("custom_condition_type") in ("Late Time", "Late Arrival After"):
		return f"{name} {round(qty * 60)} min {money}"
	if (sc.get("custom_unit") or "Per Day") == "Per Hour":
		return f"{name} {flt(qty, 2):g} h = {money}"
	if qty == 1:
		return f"{name} {money}"
	return f"{name} {flt(qty, 2):g} × {flt(unit, 2):,.2f}".replace(".00", "") + f" = {money}"


def attendance_additional_salaries(doc) -> set:
	"""Additional Salary rows on the slip that Prepare Payroll Inputs posted."""
	names = [r.additional_salary for r in (*doc.earnings, *doc.deductions) if r.additional_salary]
	if not names:
		return set()
	return set(
		frappe.get_all(
			"Additional Salary", filters={"name": ["in", names], "custom_source": SOURCE_TAG}, pluck="name"
		)
	)


def paid_weight(doc, day, att, is_holiday) -> float:
	"""How much of a day the slip pays, by the rules its payment days use."""
	joining = doc.get("date_of_joining") or frappe.get_cached_value("Employee", doc.employee, "date_of_joining")
	relieving = doc.get("relieving_date") or frappe.get_cached_value("Employee", doc.employee, "relieving_date")
	if (joining and day < getdate(joining)) or (relieving and day > getdate(relieving)):
		return 0.0
	if is_holiday:
		return 1.0  # holidays are paid (Payroll Settings: include holidays)
	if not att:
		unmarked = frappe.db.get_single_value("Payroll Settings", "consider_unmarked_attendance_as")
		return 1.0 if unmarked == "Present" else 0.0
	if att.status == "Absent":
		return 0.0
	if att.status == "On Leave":
		return 0.0 if is_lwp(att.leave_type) else 1.0
	if att.status == "Half Day":
		if att.leave_type and not is_lwp(att.leave_type):
			return 1.0  # the other half is paid leave
		return 0.5
	return 1.0


def attendance_label(doc, day, att, holiday) -> str:
	if holiday is not None and not (att and att.status in ("Present", "Half Day", "Work From Home")):
		return f"Holiday: {holiday}" if holiday else "Holiday"
	if not att:
		joining = frappe.get_cached_value("Employee", doc.employee, "date_of_joining")
		if joining and day < getdate(joining):
			return "Not yet joined"
		return "Not marked"
	punches = ""
	if att.in_time or att.out_time:
		punches = f" {format_time(att.in_time, 'HH:mm') if att.in_time else '?'}–{format_time(att.out_time, 'HH:mm') if att.out_time else '?'}"
	if att.status == "On Leave":
		return f"Leave: {att.leave_type or ''}".strip()
	label = att.status + punches
	if holiday is not None:
		label += " (holiday)"
	return label


def miti_label(day) -> str:
	bs = ad_to_bs(getdate(day))
	return f"{bs.day:02d} {get_bs_month_name(bs.month)}"


def is_lwp(leave_type) -> bool:
	return bool(leave_type and frappe.get_cached_value("Leave Type", leave_type, "is_lwp"))


def fetch_attendance(employee, start, end) -> list:
	return frappe.get_all(
		"Attendance",
		filters={"employee": employee, "attendance_date": ["between", [start, end]], "docstatus": 1},
		fields=list(ATTENDANCE_FIELDS),
	)


def fetch_holidays(employee, start, end) -> dict:
	"""{date: description} of the employee's holidays in the period."""
	emp = frappe.get_cached_value("Employee", employee, ["holiday_list", "company"], as_dict=True)
	holiday_list = resolve_holiday_lists([frappe._dict(name=employee, **emp)]).get(employee)
	if not holiday_list:
		return {}
	return {
		getdate(h.holiday_date): (h.description or "").strip()
		for h in frappe.get_all(
			"Holiday",
			filters={"parent": holiday_list, "holiday_date": ["between", [start, end]]},
			fields=["holiday_date", "description"],
		)
	}
