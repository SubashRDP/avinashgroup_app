"""One day's attendance, measured against the shift the person was rostered on.

Late time, early leaving and overtime all mean "against the shift" — 09:08 is
eight minutes late on the 9 AM shift and a full hour and eight minutes early on
the 12 PM one. The attendance sheet, the monthly summary and overtime pay must
all answer the same question the same way, so they all come here.

The minutes themselves are already on the Attendance row. `custom_late_entry`,
`custom_early_entry`, `custom_early_exit` and `custom_late_exit` are written on
validate against that row's own shift (`biometric.attendance_override`), which
is the shift HRMS rostered for that date. This module only decides which of them
count on which kind of day, and rounds overtime the way the sheet does.

What the Chaitra 2082 attendance cards show, and what is reproduced here:

  Late Time       minutes after the shift starts, on a working day the person
                  worked in full. No grace: 09:08 is 8. A holiday has no start
                  time to be late for, and a half day is already its own penalty.
  Before ofc.Time minutes before the shift ends, same days. The sheet adds the
                  two together as the month's "Late Time".
  O.T.            on a working day, the hours before the shift starts and after
                  it ends; on a holiday, every hour worked. Rounded to the nearest
                  half hour — 7:53 is 8, 7:34 is 7.5, 5:59 is 6. Only for staff
                  whose category is overtime-eligible; everyone else is paid for
                  holiday work in replacement leave instead.

The one thing the sheet has that this does not is a hand-kept exception written
at the foot of the Chaitra summary ("up to 12.18, after 5pm counts as 2 hours").
That is a one-off agreement for a fortnight, not a rule; put it through the
Overtime Sheet, where authorised hours can be typed over.
"""

import math

import frappe
from frappe.utils import flt, get_datetime, getdate

#: The statuses in which somebody actually came to work.
WORKED_STATUSES = ("Present", "Work From Home", "Half Day")


def round_to_half_hour(hours):
	"""Nearest half hour, halves rounding up — never banker's rounding."""
	return math.floor(flt(hours) * 2 + 0.5) / 2


def overtime_eligibility(employees):
	"""{employee: bool} from each person's Employee Category.

	No category means no overtime: eligibility is something a category grants,
	not something an unfilled field should hand out.
	"""
	names = [e if isinstance(e, str) else e.name for e in employees]
	if not names:
		return {}
	rows = frappe.db.sql(
		"""select e.name, ifnull(c.ot_eligible, 0)
		from `tabEmployee` e
		left join `tabEmployee Category` c on c.name = e.custom_employee_category
		where e.name in %(names)s""",
		{"names": names},
	)
	return {name: bool(eligible) for name, eligible in rows}


class ShiftRoster:
	"""Which shift each employee was on, day by day, for a period.

	Shift changes split an assignment in two (`hr.shift_change`), so a month
	can hold two shifts for one person. Resolving once per employee — as the
	reports used to — shows whichever assignment happened to sort last for the
	whole month. This answers per date, with HRMS's own precedence: a dated
	Shift Assignment, then the Employee's Default Shift.
	"""

	def __init__(self, employees, start, end):
		start, end = getdate(start), getdate(end)
		names = [e if isinstance(e, str) else e.name for e in employees]
		self._default = {}
		self._spans = {}
		if not names:
			return

		self._default = dict(
			frappe.db.sql(
				"select name, default_shift from `tabEmployee` where name in %(names)s",
				{"names": names},
			)
		)
		for employee, shift_type, span_start, span_end in frappe.db.sql(
			"""select employee, shift_type, start_date, end_date
			from `tabShift Assignment`
			where employee in %(names)s and docstatus = 1 and status = 'Active'
			  and start_date <= %(end)s and (end_date is null or end_date >= %(start)s)
			order by start_date""",
			{"names": names, "start": start, "end": end},
		):
			self._spans.setdefault(employee, []).append(
				(getdate(span_start), getdate(span_end) if span_end else None, shift_type)
			)

	def shift_on(self, employee, day):
		day = getdate(day)
		found = None
		# Latest-starting assignment covering the day wins, as in get_shift_window.
		for span_start, span_end, shift_type in self._spans.get(employee, ()):
			if span_start <= day and (span_end is None or span_end >= day):
				found = shift_type
		return found or self._default.get(employee)


def measure_day(att, is_holiday=False, ot_eligible=False):
	"""Late minutes, early-leaving minutes and overtime hours for one row.

	`att` is an Attendance row (dict or doc) carrying status, working_hours,
	in_time, out_time and the four custom_* deviation fields.
	"""
	out = frappe._dict(late_minutes=0, early_exit_minutes=0, ot_hours=0.0)
	if not att or att.get("status") not in WORKED_STATUSES:
		return out

	holiday = bool(is_holiday or att.get("custom_worked_on_holiday"))

	if not holiday and att.get("status") != "Half Day":
		out.late_minutes = int(round(flt(att.get("custom_late_entry")) / 60))
		out.early_exit_minutes = int(round(flt(att.get("custom_early_exit")) / 60))

	if ot_eligible:
		if holiday:
			hours = flt(att.get("working_hours")) or _punched_hours(att)
		else:
			hours = (flt(att.get("custom_early_entry")) + flt(att.get("custom_late_exit"))) / 3600
		out.ot_hours = round_to_half_hour(hours)

	return out


def _punched_hours(att):
	if not (att.get("in_time") and att.get("out_time")):
		return 0.0
	seconds = (get_datetime(att.get("out_time")) - get_datetime(att.get("in_time"))).total_seconds()
	return max(seconds, 0) / 3600
