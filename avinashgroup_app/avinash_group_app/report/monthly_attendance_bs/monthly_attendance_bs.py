"""
Monthly Attendance BS
=====================
Monthly attendance grid keyed by Bikram Sambat (BS) month.

Filter resolution (override rule):
  1. Fiscal Year + BS Month → that month's dates from hr/bs_calendar.py
     (Nepal BS Period, company then global, else the Nepali calendar).
  2. Else from_date AND to_date → that AD range. See _resolve_period.

Storage layer is 100% AD: Attendance.attendance_date, Employee Checkin.time, etc.
BS is presentation only — row label = ad_to_bs(date).day + month name.

Columns:
  • Date (BS day + month name)
  • AD Date, Day-of-week
  • Employee + Name + Department
  • First IN / Last OUT — the day's first and last Employee Checkin, whatever the shift's
    check-in window. NOT Attendance.in_time / out_time: HRMS leaves a punch
    outside the window out of the attendance, so those read the second punch
    as IN or the second-last as OUT. Hours, Late, O.T. and the allowance
    columns still come from the Attendance row, which is what salary uses — so
    OUT minus IN need not equal Hours.
    HR Manager can correct either from the cell (hr/punch_correction.py);
    a corrected time is highlighted, its tooltip saying what the device read,
    who changed it and why.
  • Hours Worked — Attendance.working_hours (decimal) rendered as HH:MM
  • Status
  • Shift — the shift rostered on THAT date (hr.shift_day.ShiftRoster), so a
    mid-month shift change shows on the day it happened
  • Late In (min), Before ofc. Time (min) — measured against that shift by
    hr.shift_day.measure_day.
  • Late Excused — the Attendance's Late Excused tick, its reason as the
    tooltip. The minutes beside it stay shown but are not fined. HR Manager
    can tick or untick it from the cell (hr/late_excuse.py).
  • O.T. (hrs), O.T. Rate, O.T. Amount — the hours a submitted Overtime Sheet
    measured for that employee that day (hr.overtime.get_overtime_hours), the
    same hours pay reads; the rate is the person's hourly basic × 1.5
    (attendance_allowance.overtime_rate, the one pay uses). Blank otherwise.
    Not re-measured from the Attendance row: its stored deviations can lag a
    shift changed after the punches, and showed 0 against the sheet's 4.5.
  • On Leave (1/blank)
  • Worked on Holiday (1/blank)
  • One dynamic column per attendance-driven Salary Component, with the qty
    computed by the SAME rule the allowance engine uses (evaluate_rule).
  • Remarks (festival/leave text)  +  Holidays (weekly-off label only)

Summary cards are worded for the headcount (see _summary): one person's month
for a single employee, sums that name the people they cover for a roster.
"""

from datetime import timedelta

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, getdate, strip_html_tags, today

from avinashgroup_app.hr.overtime import get_overtime_hours
from avinashgroup_app.hr.leave_from_report import get_leave_notes
from avinashgroup_app.hr.punch_correction import get_edited_days, get_shift_corrections
from avinashgroup_app.hr.shift_day import ShiftRoster, measure_day
from avinashgroup_app.hr.utils import resolve_holiday_lists
from rdp_common_app.utils.bs_boundaries import (
	ad_to_bs,
	get_bs_month_days,
	get_bs_month_name,
)
from avinashgroup_app.hr.holiday_backdate import WORKED_STATUSES
from avinashgroup_app.hr.bs_calendar import bs_year_of, month_period, parse_bs_month
from avinashgroup_app.payroll.attendance_allowance import (
	evaluate_rule,
	get_attendance_driven_components,
	get_present_statuses,
	overtime_rate,
)


DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def execute(filters=None):
	filters = frappe._dict(filters or {})

	# Two shapes of the same month, behind one View filter. Summary is one row
	# per employee (the physical attendance sheet); Detail is one row per
	# employee per day. Both resolve the period and fetch employees the same
	# way, so keeping them as separate reports meant maintaining one filter set
	# twice — and the Summary report's own filters had drifted out of step with
	# what its code required, so it threw on open.
	#
	# Imported here, not at module scope: summary.py imports the shared helpers
	# from this module, so a top-level import would be circular.
	if (filters.get("view") or "Detail") == "Summary":
		from avinashgroup_app.avinash_group_app.report.monthly_attendance_bs.summary import (
			execute_summary,
		)

		return execute_summary(filters)

	ad_start, ad_end, bs_label, note = _resolve_period(filters)
	if ad_end < ad_start:
		frappe.throw(_("To Date cannot be before From Date"))

	employees = _get_employees(filters, ad_start, ad_end)
	components = get_attendance_driven_components()

	if not employees:
		return _columns(components), [], _note_html(note), None, _summary(_new_totals(), 0, bs_label, [])

	company = filters.get("company")
	att_map = _fetch_attendance(employees, ad_start, ad_end, company)
	punch_map = _fetch_punches(employees, ad_start, ad_end)
	# Employee.holiday_list is blank for nearly everyone; the list is set on the
	# Company and inherited. Resolve that fallback once for the whole roster.
	holiday_list_of = resolve_holiday_lists(employees)
	holiday_map = _fetch_holidays(holiday_list_of, ad_start, ad_end)
	leave_map = _fetch_leaves(employees, ad_start, ad_end, company)
	# Attendance carries its own shift, but days with no Attendance row have
	# none — so fall back to the roster rather than leaving the column blank on
	# exactly the days someone is asking about. Per day, not per month: a shift
	# change splits the assignment, and a month can hold two shifts.
	roster = ShiftRoster(employees, ad_start, ad_end)
	# Overtime shows only on a day a submitted Overtime Sheet names the person,
	# at the hours that sheet measured — what pay reads. Going by OT eligibility
	# alone counted every early arrival and late stay, asked for or not.
	ot_hours = get_overtime_hours(employees, ad_start, ad_end)
	ot_rates = _ot_rates(ot_hours, components)
	# Days whose first IN or last OUT HR set by hand (hr/punch_correction.py),
	# highlighted in the grid so a typed time never passes for a device reading.
	edited = get_edited_days([e.name for e in employees], ad_start, ad_end)
	shift_edits = get_shift_corrections([e.name for e in employees], ad_start, ad_end)
	# Leave HR gave from this report (hr/leave_from_report.py), told apart from
	# leave the employee applied for.
	leave_notes = get_leave_notes({a.leave_application for a in att_map.values() if a.get("leave_application")})

	data = []
	totals = _new_totals()
	working_days = []
	present_statuses = get_present_statuses()
	today_date = getdate(today())

	# Per-date values (BS label + weekday) are identical for every employee, and
	# ad_to_bs is expensive, so compute them once per distinct date up front.
	dates = [
		getdate(frappe.utils.add_days(ad_start, offset))
		for offset in range((ad_end - ad_start).days + 1)
	]
	date_info = {}
	for ad_date in dates:
		bs = ad_to_bs(ad_date)
		# `day_label`, not `bs_label`: the per-day label used to shadow the
		# period label resolved above, so the BS Period summary card showed the
		# last day of the month ("31 Shrawan") instead of the month itself.
		day_label = f"{bs.day:02d} {get_bs_month_name(bs.month)}"
		weekday = DAY_NAMES[ad_date.weekday()]
		date_info[ad_date] = (day_label, weekday)

	for emp in employees:
		emp_holidays = holiday_map.get(holiday_list_of.get(emp.name), {})
		employed = employed_dates(emp, dates)
		working_days.append(sum(1 for d in employed if d not in emp_holidays))
		for ad_date in dates:
			day_label, weekday = date_info[ad_date]
			row = _build_row(
				emp, ad_date, day_label, weekday, att_map, emp_holidays, leave_map,
				components, roster, punch_map,
				ot_hours.get((emp.name, ad_date), 0.0), ot_rates.get((emp.name, ad_date), 0.0),
				edited.get((emp.name, ad_date)),
			)
			row["shift_edit_note"] = shift_edits.get((emp.name, ad_date))
			att = att_map.get((emp.name, ad_date))
			row["leave_note"] = leave_notes.get(att.leave_application) if att and att.get("leave_application") else None
			data.append(row)
			_accumulate(
				totals, row, present_statuses,
				counts_as_missing=ad_date in employed and ad_date < today_date,
			)
			# Unrounded per day, rounded once at the end, as pay does: summing the
			# rounded daily amounts drifted a paisa from the slip.
			totals["ot_amount"] += ot_hours.get((emp.name, ad_date), 0.0) * ot_rates.get((emp.name, ad_date), 0.0)

	return (
		_columns(components),
		data,
		_note_html(note),
		_chart(data, len(employees)),
		_summary(totals, len(employees), bs_label, working_days),
	)


# ---------------------------------------------------------------------------
# Period resolution
# ---------------------------------------------------------------------------

def _resolve_period(filters):
	"""Return (ad_start, ad_end, bs_label, assumption_note).

	This used to throw "Select Fiscal Year + BS Month or From Date + To Date"
	whenever the filters were not one of two exact shapes. That is a refusal
	dressed as an error: a fiscal year on its own, or a single date, says
	perfectly clearly which month is wanted. The report now resolves the most
	sensible period it can and reports what it assumed, so it always runs.

	Priority, most specific first:

	  1. Fiscal Year + BS Month  — the intended pair, honoured exactly.
	  2. From Date + To Date     — an explicit AD range.
	  3. One date only           — that date's BS month.
	  4. Fiscal Year only        — the running BS month if it falls inside that
	                               year, otherwise the year's closing month.
	  5. BS Month only           — that month of the fiscal year covering today.
	  6. Nothing at all          — the running BS month.

	Fiscal Year + BS Month is checked before the dates because Frappe's Date
	widgets retain values across runs; without that order a stale date pair
	would silently override a freshly picked month.

	`assumption_note` is None when the filters were unambiguous, and otherwise a
	short sentence naming what was chosen — surfaced above the report rather
	than left for the reader to infer from the numbers.
	"""
	company = filters.get("company")

	def month_range(bs_year, bs_month, note=None):
		# Nepal BS Period (company, then global), else the calendar: the same
		# dates a Payroll Entry for this month uses. See hr/bs_calendar.py.
		period = month_period(company, bs_year, bs_month)
		return period.start_date, period.end_date, period.label, note

	bs_year_for = bs_year_of

	# 1. the intended pair
	if filters.get("fiscal_year") and filters.get("bs_month"):
		bs_month = _parse_bs_month(filters.bs_month)
		return month_range(bs_year_for(filters.fiscal_year, bs_month), bs_month)

	# 2. an explicit AD range
	if filters.get("from_date") and filters.get("to_date"):
		ad_start = getdate(filters.from_date)
		ad_end = getdate(filters.to_date)
		if ad_end < ad_start:
			ad_start, ad_end = ad_end, ad_start
		bs_s, bs_e = ad_to_bs(ad_start), ad_to_bs(ad_end)
		if bs_s.year == bs_e.year and bs_s.month == bs_e.month:
			label = f"{get_bs_month_name(bs_s.month)} {bs_s.year}"
		else:
			label = (
				f"{bs_s.day} {get_bs_month_name(bs_s.month)} → "
				f"{bs_e.day} {get_bs_month_name(bs_e.month)} {bs_e.year}"
			)
		return ad_start, ad_end, label, None

	# 3. one date only — take that date's BS month
	lone = filters.get("from_date") or filters.get("to_date")
	if lone:
		bs = ad_to_bs(getdate(lone))
		which = _("From Date") if filters.get("from_date") else _("To Date")
		return month_range(
			bs.year,
			bs.month,
			_("Only {0} was set, so the whole of {1} {2} is shown.").format(
				which, get_bs_month_name(bs.month), bs.year
			),
		)

	today_bs = ad_to_bs(getdate(today()))

	# 4. fiscal year only — the running month if it belongs to that year
	if filters.get("fiscal_year"):
		fy = frappe.get_cached_doc("Fiscal Year", filters.fiscal_year)
		if getdate(fy.year_start_date) <= getdate(today()) <= getdate(fy.year_end_date):
			return month_range(
				today_bs.year,
				today_bs.month,
				_("No BS Month was set, so the current month ({0} {1}) is shown.").format(
					get_bs_month_name(today_bs.month), today_bs.year
				),
			)
		# a closed year: its last month is the one anybody means
		closing = ad_to_bs(getdate(fy.year_end_date))
		return month_range(
			closing.year,
			closing.month,
			_("No BS Month was set, so the last month of {0} ({1} {2}) is shown.").format(
				filters.fiscal_year, get_bs_month_name(closing.month), closing.year
			),
		)

	# 5. BS month only — place it in the fiscal year covering today
	if filters.get("bs_month"):
		bs_month = _parse_bs_month(filters.bs_month)
		fy_name = frappe.db.get_value(
			"Fiscal Year",
			{
				"year_start_date": ("<=", today()),
				"year_end_date": (">=", today()),
				"disabled": 0,
			},
			"name",
		)
		bs_year = bs_year_for(fy_name, bs_month) if fy_name else today_bs.year
		return month_range(
			bs_year,
			bs_month,
			_("No Fiscal Year was set, so {0} {1} is shown.").format(
				get_bs_month_name(bs_month), bs_year
			),
		)

	# 6. nothing at all
	return month_range(
		today_bs.year,
		today_bs.month,
		_("No period was set, so the current month ({0} {1}) is shown.").format(
			get_bs_month_name(today_bs.month), today_bs.year
		),
	)


@frappe.whitelist()
def get_ad_range(fiscal_year=None, bs_month=None, company=None):
	"""AD dates for a BS fiscal year + month, for the filter autofill.

	The report's own resolver does the work, so the dates shown in the From/To
	filters are the exact dates the report will use — including any Nepal BS
	Period company override, which shifts month boundaries away from the
	calendar ones.
	"""
	ad_start, ad_end, label, _note = _resolve_period(
		frappe._dict(
			{"fiscal_year": fiscal_year, "bs_month": bs_month, "company": company}
		)
	)
	return {"from_date": str(ad_start), "to_date": str(ad_end), "label": label}


_parse_bs_month = parse_bs_month


# ---------------------------------------------------------------------------
# Employee fetch (company-scoped by User Permissions — see the note below)
# ---------------------------------------------------------------------------

def _get_employees(filters, ad_start, ad_end):
	emp_filters = [["Employee", "status", "=", filters.get("status") or "Active"]]
	if filters.get("company"):
		emp_filters.append(["Employee", "company", "=", filters.company])
	if filters.get("department"):
		emp_filters.append(["Employee", "department", "=", filters.department])
	if filters.get("branch"):
		emp_filters.append(["Employee", "branch", "=", filters.branch])
	if filters.get("designation"):
		emp_filters.append(["Employee", "designation", "=", filters.designation])
	if filters.get("employee"):
		emp_filters.append(["Employee", "name", "=", filters.employee])
	if filters.get("shift"):
		# Shift lives on Shift Assignment, not on the Employee: default_shift is
		# blank for everyone here and the assignment is what auto-attendance
		# actually reads. Resolve the roster first, then filter by name.
		on_shift = _employees_on_shift(filters.shift, ad_start, ad_end)
		# An empty list must still filter, or "no one on this shift" would
		# silently return everyone.
		emp_filters.append(["Employee", "name", "in", on_shift or [""]])

	emp_filters.append(["Employee", "date_of_joining", "<=", ad_end])

	# Either still employed (no relieving date) or relieved after the period start.
	emp_or_filters = [
		["Employee", "relieving_date", "is", "not set"],
		["Employee", "relieving_date", ">", ad_start],
	]

	# frappe.get_list, NOT get_all: get_all hardcodes ignore_permissions=True
	# (frappe/__init__.py), so it returns every company's staff to anyone who
	# can open the report. get_list applies User Permissions — Company, and
	# also Department/Branch where those are set. limit_page_length=0 because
	# get_list otherwise stops at 20 rows.
	return frappe.get_list(
		"Employee",
		filters=emp_filters,
		or_filters=emp_or_filters,
		limit_page_length=0,
		fields=[
			"name", "employee_name", "employee_number",
			"company", "department", "designation", "branch",
			"holiday_list", "default_shift",
			"date_of_joining", "relieving_date",
		],
		order_by="employee_name asc",
	)


# ---------------------------------------------------------------------------
# Bulk fetches
# ---------------------------------------------------------------------------

def _employees_on_shift(shift, ad_start, ad_end):
	"""Employees assigned to `shift` at any point in the period.

	A Shift Assignment with no end date is open-ended, so it counts as long as
	it started on or before the period ends.
	"""
	rows = frappe.get_all(
		"Shift Assignment",
		filters={
			"shift_type": shift,
			"docstatus": 1,
			"start_date": ["<=", ad_end],
		},
		or_filters=[
			["end_date", "is", "not set"],
			["end_date", ">=", ad_start],
		],
		pluck="employee",
		limit_page_length=0,
	)
	# Employees whose default shift is this one, with no assignment at all.
	rows += frappe.get_all(
		"Employee", filters={"default_shift": shift}, pluck="name", limit_page_length=0
	)
	return list(set(rows))


def _fetch_attendance(employees, ad_start, ad_end, company=None):
	"""Return {(employee, date): attendance_dict}."""
	emp_names = [e.name for e in employees]
	if not emp_names:
		return {}
	att_filters = {
		"employee": ["in", emp_names],
		"attendance_date": ["between", [ad_start, ad_end]],
		"docstatus": ["<", 2],
	}
	if company:
		att_filters["company"] = company
	rows = frappe.get_all(
		"Attendance",
		filters=att_filters,
		fields=[
			"name", "employee", "attendance_date",
			"status", "in_time", "out_time", "working_hours",
			"late_entry", "early_exit", "shift",
			"custom_worked_on_holiday",
			"custom_late_entry", "custom_early_entry",
			"custom_early_exit", "custom_late_exit",
			"custom_late_excused", "custom_late_excuse_reason",
			"leave_application",
		],
	)
	out = {}
	for r in rows:
		out[(r.employee, getdate(r.attendance_date))] = r
	return out


def _fetch_punches(employees, ad_start, ad_end):
	"""Return {(employee, date): (first punch, last punch or None)}.

	Straight from Employee Checkin, by calendar day. Every punch counts: no
	shift window, no log_type, no skip_auto_attendance. A day with a single
	punch has an IN and no OUT.
	"""
	emp_names = [e.name for e in employees]
	if not emp_names:
		return {}
	rows = frappe.db.sql(
		"""select employee, date(`time`) as punch_date,
			min(`time`) as first_punch, max(`time`) as last_punch, count(*) as punches
		from `tabEmployee Checkin`
		where employee in %(names)s
		  and `time` >= %(start)s and `time` < %(end)s
		group by employee, date(`time`)""",
		{"names": emp_names, "start": ad_start, "end": frappe.utils.add_days(ad_end, 1)},
		as_dict=True,
	)
	return {
		(r.employee, getdate(r.punch_date)): (r.first_punch, r.last_punch if r.punches > 1 else None)
		for r in rows
	}


def _fetch_holidays(holiday_list_of, ad_start, ad_end):
	"""Return {holiday_list_name: {date: {description, weekly_off}}}.

	Takes the resolved {employee: holiday list} map rather than the employees,
	so the company fallback is already applied — reading Employee.holiday_list
	here saw a blank for 106 of 107 people and loaded no holidays at all.
	"""
	lists = list({hl for hl in holiday_list_of.values() if hl})
	if not lists:
		return {}
	rows = frappe.get_all(
		"Holiday",
		filters={
			"parent": ["in", lists],
			"holiday_date": ["between", [ad_start, ad_end]],
		},
		fields=["parent", "holiday_date", "description", "weekly_off"],
	)
	out = {}
	for r in rows:
		out.setdefault(r.parent, {})[getdate(r.holiday_date)] = r
	return out


def _fetch_leaves(employees, ad_start, ad_end, company=None):
	"""Return {(employee, date): leave_type}."""
	emp_names = [e.name for e in employees]
	if not emp_names:
		return {}
	leave_filters = {
		"employee": ["in", emp_names],
		"status": "Approved",
		"docstatus": 1,
		"from_date": ["<=", ad_end],
		"to_date": [">=", ad_start],
	}
	if company:
		leave_filters["company"] = company
	rows = frappe.get_all(
		"Leave Application",
		filters=leave_filters,
		fields=["employee", "from_date", "to_date", "leave_type"],
	)
	out = {}
	for r in rows:
		fd = getdate(r.from_date)
		td = getdate(r.to_date)
		for offset in range((td - fd).days + 1):
			out[(r.employee, getdate(frappe.utils.add_days(fd, offset)))] = r.leave_type
	return out


def _build_row(
	emp, ad_date, bs_label, weekday, att_map, emp_holidays, leave_map, components, roster,
	punch_map=None, ot_hours=0.0, ot_rate=0.0, edited=None,
):
	holiday = emp_holidays.get(ad_date)
	leave_type = leave_map.get((emp.name, ad_date))
	att = att_map.get((emp.name, ad_date))
	punches = (punch_map or {}).get((emp.name, ad_date))

	in_time_str = ""
	out_time_str = ""
	working_hours = ""
	status = ""
	measured = measure_day(None)
	work_in_holiday = 0
	leave_flag = 0
	remarks = ""
	holidays_col = ""
	holiday_label = ""

	# Holidays column = weekly-off label only.
	# Remarks column = festival description (when not a weekly off).
	if holiday:
		desc = strip_html_tags(holiday.get("description") or "").strip()
		holiday_label = (desc or weekday.upper()).upper()
		if holiday.get("weekly_off"):
			# Weekly off → both columns get the label (matches NGK sheet layout)
			holidays_col = holiday_label
			remarks = holiday_label
		else:
			# Festival / one-off holiday → only Remarks
			remarks = holiday_label or "HOLIDAY"

	if leave_type:
		leave_flag = 1
		if not remarks:
			remarks = f"LEAVE — {leave_type}".upper()

	if att:
		status = att.status or ""
		# A leave or holiday row with no time worked has no hours to show.
		working_hours = _fmt_hours(att.working_hours) if flt(att.working_hours) or punches else ""
		if not punches:
			# Attendance keyed in by hand has times but no punches behind them.
			in_time_str = _fmt_time(att.in_time)
			out_time_str = _fmt_time(att.out_time)
		work_in_holiday = 1 if worked_on_holiday(att, bool(holiday)) else 0
		# Against the shift of the day. This used to need HRMS's `late_entry`
		# flag, which nothing on this site sets — so Late read 0 for everyone.
		measured = measure_day(att, is_holiday=bool(holiday))
		# Holiday-aware status: tag holiday name on both worked and absent rows
		if holiday:
			if status in ("Present", "Half Day"):
				status = f"Worked on Holiday ({holiday_label})"
			elif status == "Absent":
				status = f"Holiday ({holiday_label})"
	else:
		if holiday:
			status = f"Holiday ({holiday_label})" if holiday_label else "Holiday"
		elif leave_type:
			status = "On Leave"
		else:
			status = "Not Marked"

	in_note = out_note = None
	if punches:
		# The punches themselves, on every kind of day — also one with no
		# Attendance row yet, or marked Absent.
		in_time_str = _fmt_time(punches[0])
		out_time_str = _fmt_time(punches[1])
		if edited:
			in_note = edited.get(punches[0])
			out_note = edited.get(punches[1]) if punches[1] else None

	stale = _marked_off_punches(att, punches)
	if stale:
		remarks = f"{remarks} · {stale}" if remarks else stale

	# Dynamic allowance columns — per-day qty (days/hours per the component's unit).
	component_values = {}
	if att and components:
		for sc in components:
			try:
				qty = evaluate_rule(att, sc, emp.name)
			except Exception:
				qty = 0
			component_values[_component_fieldname(sc.name)] = flt(qty) if qty else 0

	row = {
		"bs_date": bs_label,
		"ad_date": ad_date,
		"day": weekday,
		"employee": emp.name,
		"employee_name": emp.employee_name,
		"shift": (att.shift if att else None) or roster.shift_on(emp.name, ad_date),
		"department": emp.department,
		"in_time": in_time_str,
		"out_time": out_time_str,
		"working_hours": working_hours,
		"status": status,
		"late_minutes": measured.late_minutes,
		"before_office_minutes": measured.early_exit_minutes,
		# Excused: the minutes stay shown, but are not fined and do not make a
		# half day. HR Manager can tick it from the cell (hr/late_excuse.py).
		"late_excused": 1 if att and att.custom_late_excused else 0,
		"late_excuse_reason": (att.custom_late_excuse_reason or "") if att else "",
		"attendance": att.name if att else None,
		"ot_hours": flt(ot_hours),
		"ot_rate": flt(ot_rate, 2) if ot_hours else 0,
		"ot_amount": flt(flt(ot_hours) * flt(ot_rate), 2),
		"leave_count": leave_flag,
		"work_in_holiday": work_in_holiday,
		"remarks": remarks,
		"holidays_col": holidays_col,
		# Not columns. The edit notes drive the highlight and its tooltip; the
		# raw status and holiday flag let the summary count without re-parsing
		# the display status ("Worked on Holiday (DASHAIN)").
		"in_edit_note": in_note,
		"out_edit_note": out_note,
		"att_status": att.status if att else None,
		"marked_off_punches": 1 if stale else 0,
		"is_holiday": 1 if holiday else 0,
	}
	row.update(component_values)
	return row


#: How far the attendance's in/out may sit from the day's first/last punch
#: before the row says so. HRMS stores the punch time itself, so any real
#: difference means a punch was left out when the day was marked.
STALE_MARK_MINUTES = 1


def _marked_off_punches(att, punches):
	"""A remark when the attendance was marked from other times than the day's
	first and last punch, or "".

	First IN / Last OUT show the punches, but status, hours and late minutes
	come from the attendance. Days bulk-marked while a shift's check-in window
	was 0 dropped the early punch — Anesh Tandukar, 19 Aug: in 05:59, marked
	from his 13:05 lunch punch, so a Half Day "4 h late" sat beside a 05:59
	First IN with nothing to say why. Re-marking the day (✎ on First IN) fixes it.
	"""
	if not (att and punches and att.in_time) or att.get("leave_application"):
		return ""
	first, last = punches
	slack = timedelta(minutes=STALE_MARK_MINUTES)
	dropped_in = get_datetime(first) < get_datetime(att.in_time) - slack
	# No out-time at all while a later punch exists drops the OUT just the same.
	dropped_out = bool(last) and (
		not att.out_time or get_datetime(last) > get_datetime(att.out_time) + slack
	)
	if not (dropped_in or dropped_out):
		return ""
	return _("Marked from {0} – {1}, not the first and last punch: re-mark the day").format(
		_fmt_time(att.in_time)[:5], _fmt_time(att.out_time)[:5] or "—"
	)


def _ot_rates(ot_hours, components):
	"""{(employee, date): one overtime hour's pay} for the days that have overtime.

	The rate pay uses (attendance_allowance.overtime_rate): the person's basic ÷
	the BS month's days ÷ 8 × 1.5, with the Overtime component's own "Rate: Days
	/ Hours" overrides. Worked out once per person per BS month. 0 for someone
	with no salary assignment — the hours still show, priced at nothing.
	"""
	sc = next((c for c in components if c.get("custom_condition_type") == "Authorised Overtime"), None)
	cache, out = {}, {}
	for employee, ad_date in ot_hours:
		bs = ad_to_bs(ad_date)
		key = (employee, bs.year, bs.month)
		if key not in cache:
			try:
				cache[key] = overtime_rate(employee, ad_date, get_bs_month_days(bs.year, bs.month), sc)
			except Exception:
				frappe.log_error(title=f"Monthly Attendance BS: overtime rate for {employee}", message=frappe.get_traceback())
				cache[key] = 0.0
		out[(employee, ad_date)] = cache[key]
	return out


def worked_on_holiday(att, is_holiday):
	"""Worked on a holiday: came in (Present, Half Day, WFH) on a date the
	employee's holiday list (own, else company default) carries. Both views.

	The holiday list, not Attendance.custom_worked_on_holiday. The flag is a
	copy taken when the row was saved, and goes stale when the list is edited
	later: on demo Bheshraj worked Janai Purnima and Janmasthami, both on his
	list, with the flag 0 on both rows. The Detail view counted them from the
	list and the Summary view missed them from the flag, so the two said 2 and
	0. The list is what the day was; payroll's flag is now kept to it by
	attendance_allowance.resync_holiday_flags on every Holiday List save.
	"""
	return bool(att and is_holiday and att.status in WORKED_STATUSES)


def _new_totals():
	return {
		"present": 0.0, "half_day": 0, "absent": 0, "not_marked": 0, "holiday": 0,
		"leave": 0, "late_min": 0, "ot_hours": 0.0, "ot_amount": 0.0,
		"excused_min": 0, "excused_days": 0,
	}


def employed_dates(emp, dates):
	"""The dates the employee was on the books: from joining, until relieving."""
	joined = getdate(emp.date_of_joining) if emp.get("date_of_joining") else None
	left = getdate(emp.relieving_date) if emp.get("relieving_date") else None
	return {d for d in dates if (not joined or d >= joined) and (not left or d <= left)}


def _accumulate(totals, row, present_statuses, counts_as_missing):
	"""Add one day to the totals.

	Present Days counts a Half Day as half, the way the Summary view and the
	salary slip do; it used to count it as a whole day. A holiday the person
	came in on is Worked on Holiday only: it is not a working day, so it adds
	neither a present day nor a half day (a holiday's Half Day was a late-rule
	leftover, and inflated Present Days past the month's working days).
	"""
	totals["late_min"] += row["late_minutes"] + row["before_office_minutes"]
	if row.get("late_excused"):
		totals["excused_min"] += row["late_minutes"] + row["before_office_minutes"]
		totals["excused_days"] += 1
	totals["ot_hours"] += row["ot_hours"]
	att_status = row.get("att_status")
	if row.get("is_holiday"):
		pass
	elif att_status in present_statuses:
		totals["present"] += 1
	elif att_status == "Half Day":
		totals["present"] += 0.5
		totals["half_day"] += 1
	elif att_status == "Absent" and not row.get("is_holiday"):
		totals["absent"] += 1
	if row["work_in_holiday"]:
		totals["holiday"] += 1
	if row["leave_count"]:
		totals["leave"] += 1
	if row["status"] == "Not Marked" and counts_as_missing:
		totals["not_marked"] += 1


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def _fmt_time(dt):
	if not dt:
		return ""
	if hasattr(dt, "strftime"):
		return dt.strftime("%H:%M:%S")
	s = str(dt)
	return s.split(" ")[-1] if " " in s else s


def _fmt_hours(hours):
	"""Decimal hours (6.8303) → clock string ('06:49').

	Truncates rather than rounds, so the value never reads as more time than
	was actually worked. Rounded to 6dp first to absorb float noise that would
	otherwise turn 8.0 hours into 07:59.
	"""
	total_minutes = int(round(flt(hours) * 60, 6))
	if total_minutes < 0:
		total_minutes = 0
	return f"{total_minutes // 60:02d}:{total_minutes % 60:02d}"


def _component_fieldname(component_name):
	"""Stable column fieldname derived from Salary Component name."""
	slug = "".join(c.lower() if c.isalnum() else "_" for c in component_name).strip("_")
	return f"sc_{slug}"


# ---------------------------------------------------------------------------
# Columns + summary
# ---------------------------------------------------------------------------

def _columns(components):
	# The first two columns are FROZEN by the report JS (FROZEN_FIELDS in
	# monthly_attendance_bs.js) so they stay on screen while the rest scrolls.
	# Freezing needs them contiguous and leading, which is why AD Date sits
	# third: the grid is read in BS, so AD Date is allowed to scroll away rather
	# than spend 100px of the frozen block. Reordering the first two breaks the
	# freeze silently.
	base = [
		{"label": _("BS Date"), "fieldname": "bs_date", "fieldtype": "Data", "width": 110},
		# Name over ID in one cell, the whole cell a link to the Employee. Data,
		# not Link: a Link fieldtype renders its own anchor around the ID alone,
		# and we need the anchor to wrap both lines. The JS formatter builds it
		# from `employee` + `employee_name`, both of which stay on every row.
		{"label": _("Employee"), "fieldname": "employee", "fieldtype": "Data", "width": 190},
		{"label": _("AD Date"), "fieldname": "ad_date", "fieldtype": "Date", "width": 100},
		{"label": _("Day"), "fieldname": "day", "fieldtype": "Data", "width": 60},
		{"label": _("Shift"), "fieldname": "shift", "fieldtype": "Link", "options": "Shift Type", "width": 120},
		{"label": _("Department"), "fieldname": "department", "fieldtype": "Link", "options": "Department", "width": 130},
		{"label": _("First IN"), "fieldname": "in_time", "fieldtype": "Data", "width": 95},
		{"label": _("Last OUT"), "fieldname": "out_time", "fieldtype": "Data", "width": 95},
		{"label": _("Hours Worked"), "fieldname": "working_hours", "fieldtype": "Data", "width": 80, "align": "right"},
		{"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 95},
		{"label": _("Late In (min)"), "fieldname": "late_minutes", "fieldtype": "Int", "width": 80},
		{"label": _("Before ofc. Time (min)"), "fieldname": "before_office_minutes", "fieldtype": "Int", "width": 130},
		{"label": _("Late Excused"), "fieldname": "late_excused", "fieldtype": "Check", "width": 100},
		{"label": _("O.T. (hrs)"), "fieldname": "ot_hours", "fieldtype": "Float", "width": 80, "precision": 2},
		{"label": _("O.T. Rate"), "fieldname": "ot_rate", "fieldtype": "Currency", "width": 90},
		{"label": _("O.T. Amount"), "fieldname": "ot_amount", "fieldtype": "Currency", "width": 100},
		{"label": _("On Leave"), "fieldname": "leave_count", "fieldtype": "Check", "width": 65},
		{"label": _("Worked on Holiday"), "fieldname": "work_in_holiday", "fieldtype": "Check", "width": 110},
	]
	# Dynamic allowance columns — one per attendance-driven Salary Component.
	# Value is the per-day qty (days/hours per the component's unit).
	for sc in components:
		base.append({
			"label": sc.name,
			"fieldname": _component_fieldname(sc.name),
			"fieldtype": "Float",
			"width": 95,
			"precision": 2,
		})
	base.append({"label": _("Remarks"), "fieldname": "remarks", "fieldtype": "Data", "width": 160})
	base.append({"label": _("Holidays"), "fieldname": "holidays_col", "fieldtype": "Data", "width": 110})
	return base


def _summary(totals, employee_count, bs_label, working_days):
	"""The cards above the grid, worded for how many people they add up.

	For one employee they read as that person's month: "Present Days 24". For a
	roster the same numbers are sums over everybody, and "Total Days Worked 2,410"
	read as if one person had worked it — so every summed card names the people
	it adds up, an average per employee sits beside Present Days, and Working
	Days in Month, which is the same for everyone, is shown once rather than
	multiplied by the headcount.

	"Late Time" is late arrival plus leaving early, as on the sheet's card
	(Late Time = Late + Before ofc. Time).
	"""
	n = employee_count
	cards = [{"value": bs_label, "label": _("BS Period"), "datatype": "Data"}]
	if n != 1:
		cards.append({"value": n, "label": _("Employees"), "datatype": "Int"})
	if not n:
		return cards

	# Present Days is every day the person came: the working days they were
	# present plus the holidays they came in on, shown split beside it.
	came = totals["present"] + totals["holiday"]
	cards.append(working_days_card(working_days))
	cards.append({"value": flt(came, 1), "label": per_scope(_("Present Days"), n), "datatype": "Float"})
	cards.append({"value": flt(totals["present"], 1), "label": per_scope(_("Working Days Present"), n), "datatype": "Float"})
	cards.append({"value": totals["holiday"], "label": per_scope(_("Worked on Holiday"), n), "datatype": "Int"})
	if n > 1:
		cards.append({
			"value": flt(came / n, 1),
			"label": _("Present Days per Employee (avg)"),
			"datatype": "Float",
		})
	if totals["half_day"]:
		cards.append({"value": totals["half_day"], "label": per_scope(_("Half Days (counted ½)"), n), "datatype": "Int"})
	cards.extend([
		{"value": totals["absent"], "label": per_scope(_("Absent Days"), n), "datatype": "Int"},
		{"value": totals["leave"], "label": per_scope(_("Leave Days"), n), "datatype": "Int"},
	])
	if totals["not_marked"]:
		cards.append({"value": totals["not_marked"], "label": per_scope(_("Not Marked Days"), n), "datatype": "Int"})
	cards.extend([
		{"value": totals["late_min"], "label": per_scope(_("Late Time (min)"), n), "datatype": "Int"},
	])
	if totals["excused_days"]:
		cards.append({
			"value": totals["excused_min"],
			"label": per_scope(_("Late Time Excused (min)"), n),
			"datatype": "Int",
		})
	cards.extend([
		{"value": flt(totals["ot_hours"], 2), "label": per_scope(_("O.T. Hours"), n), "datatype": "Float"},
		{"value": flt(totals["ot_amount"], 2), "label": per_scope(_("O.T. Amount"), n), "datatype": "Currency"},
	])
	return cards


def per_scope(label, employee_count):
	"""A card label that says whose figure it is. Shared with the Summary view."""
	if employee_count == 1:
		return label
	return _("{0} — all {1} employees").format(label, employee_count)


def working_days_card(working_days):
	"""Days in the period less each person's holidays, shown once.

	Almost always one number for everybody. Women carry their own holiday list
	(Teej), and someone who joined or left mid-month has fewer, so a roster can
	hold a spread — shown as "26-27" rather than averaged into a fraction.
	"""
	distinct = sorted(set(working_days))
	if len(working_days) == 1:
		return {"value": distinct[0], "label": _("Working Days in Month"), "datatype": "Int"}
	if len(distinct) == 1:
		return {"value": distinct[0], "label": _("Working Days in Month (each)"), "datatype": "Int"}
	return {
		"value": f"{distinct[0]}–{distinct[-1]}",
		"label": _("Working Days in Month (each)"),
		"datatype": "Data",
	}


def _chart(rows, employee_count=None):
	"""One chart, two stories — which one depends on how many people are shown.

	For a whole roster the question is "what did this DAY look like": a stacked
	mix of Present / Half Day / Leave / Absent, where a spike of red on one date
	reads instantly and is invisible in three thousand grid rows.

	For a single employee that same chart is 31 bars all exactly one unit tall,
	whose only information is colour, on a y-axis reading 0 / 0.5 / 1. So for one
	person it plots HOURS WORKED instead: the shape of their month, with short
	days and absences visible as dips rather than as a colour you have to decode
	against a legend.

	Labels are the BS day number alone. "01 Shrawan" repeated 31 times does not
	fit the axis and renders as "0 ...", and the month is already named in the
	BS Period tile directly above the chart.
	"""
	if not rows:
		return None

	day_label = lambda r: (r.get("bs_date") or "").split(" ")[0]

	if employee_count == 1:
		return _hours_chart(rows, day_label)
	return _status_mix_chart(rows, day_label)


def _hours_chart(rows, day_label):
	"""Hours worked per day for one employee."""
	labels, hours = [], []
	for r in rows:
		label = day_label(r)
		if not label:
			continue
		labels.append(label)
		# working_hours is preformatted "HH:MM" for the grid; parse it back so
		# the axis is in decimal hours rather than a string.
		raw = r.get("working_hours") or ""
		if ":" in str(raw):
			h, m = str(raw).split(":")[:2]
			hours.append(round(int(h) + int(m) / 60.0, 2))
		else:
			hours.append(flt(raw))

	if not any(hours):
		return None

	return {
		"data": {"labels": labels, "datasets": [{"name": _("Hours Worked"), "values": hours}]},
		"type": "bar",
		"colors": ["#2b8a5e"],
		"axisOptions": {"xIsSeries": 1},
		"height": 260,
	}


def _status_mix_chart(rows, day_label):
	"""Stacked Present / Half Day / Leave / Absent / Holiday per day."""
	# Holiday is a bucket, not a gap: without it a Saturday drew nothing and the
	# chart read as missing data rather than as a day nobody was meant to work.
	BUCKETS = (
		(_("Present"), "#2b8a5e"),
		(_("Half Day"), "#c98a12"),
		(_("On Leave"), "#4b7bb5"),
		(_("Absent"), "#c0453a"),
		(_("Holiday"), "#c9c4bd"),
	)
	names = [n for n, _c in BUCKETS]

	order, by_day = [], {}
	for r in rows:
		label = day_label(r)
		if not label:
			continue
		if label not in by_day:
			by_day[label] = dict.fromkeys(names, 0)
			order.append(label)
		bucket = by_day[label]
		status = (r.get("status") or "").split(" (")[0]
		if status in bucket:
			bucket[status] += 1
		elif status == "Work From Home":
			bucket[_("Present")] += 1

	if not order or not any(sum(by_day[d].values()) for d in order):
		return None

	# Drop buckets nothing landed in, so the legend names what actually happened
	# instead of listing every status the report knows about.
	datasets, colors = [], []
	for name, color in BUCKETS:
		values = [by_day[d][name] for d in order]
		if any(values):
			datasets.append({"name": name, "values": values})
			colors.append(color)

	return {
		"data": {"labels": order, "datasets": datasets},
		"type": "bar",
		"barOptions": {"stacked": 1},
		"colors": colors,
		"axisOptions": {"xIsSeries": 1, "shortenYAxisNumbers": 1},
		"height": 260,
	}


def _note_html(note):
	"""Frappe renders the report `message` slot above the grid. Used only to say
	what the report assumed when the filters left it a choice — silent when they
	did not, so the banner keeps meaning something."""
	if not note:
		return None
	return (
		'<div style="padding:8px 12px;background:#FAF6EC;border-left:3px solid #C9A227;'
		'border-radius:0 4px 4px 0;color:#6B5A1E;font-size:13px">{0}</div>'
	).format(note)
