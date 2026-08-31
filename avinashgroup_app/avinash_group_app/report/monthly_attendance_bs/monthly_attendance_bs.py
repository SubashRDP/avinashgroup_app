"""
Monthly Attendance BS
=====================
Monthly attendance grid keyed by Bikram Sambat (BS) month.

Filter resolution (override rule):
  1. If from_date AND to_date provided → use that AD range.
  2. Else use bs_year + bs_month → resolve via Nepal BS Period (company override)
     or fall back to get_bs_month_range(year, month).

Storage layer is 100% AD: Attendance.attendance_date, Employee Checkin.time, etc.
BS is presentation only — row label = ad_to_bs(date).day + month name.

Columns:
  • Date (BS day + month name)
  • AD Date, Day-of-week
  • Employee + Name + Department
  • IN / OUT (from Attendance.in_time / out_time)
  • Hours — Attendance.working_hours (decimal) rendered as HH:MM
  • Status
  • Late (min): max(0, in_time - shift.start_time) when Attendance.late_entry=1
  • Before Office (min): max(0, shift.end_time - out_time)  — *early exit*, not early arrival
  • Leave (1/blank)
  • Work In Holiday (1/blank)
  • One dynamic column per attendance-driven Salary Component, with the qty
    computed by the SAME rule the allowance engine uses (evaluate_rule).
  • Remarks (festival/leave text)  +  Holidays (weekly-off label only)
"""

import frappe
from frappe import _
from frappe.utils import getdate, flt, strip_html_tags, today

from avinashgroup_app.hr.utils import resolve_holiday_lists
from rdp_common_app.utils.bs_boundaries import (
	ad_to_bs,
	get_bs_month_range,
	get_bs_month_name,
	BS_MONTH_NAMES,
)
from rdp_common_app.nepal_hrms_common.doctype.nepal_bs_period.nepal_bs_period import (
	get_user_defined_period,
)
from avinashgroup_app.payroll.attendance_allowance import (
	evaluate_rule,
	get_attendance_driven_components,
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
		return _columns(components), [], _note_html(note), None, _summary(0, 0, 0, 0, 0, bs_label)

	company = filters.get("company")
	att_map = _fetch_attendance(employees, ad_start, ad_end, company)
	# Employee.holiday_list is blank for nearly everyone; the list is set on the
	# Company and inherited. Resolve that fallback once for the whole roster.
	holiday_list_of = resolve_holiday_lists(employees)
	holiday_map = _fetch_holidays(holiday_list_of, ad_start, ad_end)
	leave_map = _fetch_leaves(employees, ad_start, ad_end, company)
	shift_cache = {}
	# Attendance carries its own shift, but days with no Attendance row have
	# none — so fall back to the roster rather than leaving the column blank on
	# exactly the days someone is asking about.
	roster = _shift_roster(employees, ad_start, ad_end)

	data = []
	totals = {"office": 0, "holiday": 0, "leave": 0, "late_min": 0}

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
		for ad_date in dates:
			day_label, weekday = date_info[ad_date]
			row = _build_row(
				emp, ad_date, day_label, weekday, att_map, emp_holidays, leave_map,
				components, shift_cache, roster,
			)
			data.append(row)
			_accumulate(totals, row)

	return (
		_columns(components),
		data,
		_note_html(note),
		_chart(data, len(employees)),
		_summary(
			totals["office"],
			totals["holiday"],
			totals["office"] + totals["holiday"],
			totals["leave"],
			totals["late_min"],
			bs_label,
		),
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
		raw_start, raw_end = get_bs_month_range(bs_year, bs_month)
		label = f"{get_bs_month_name(bs_month)} {bs_year}"
		if company:
			custom = get_user_defined_period(raw_start, company)
			if custom and custom.bs_year == bs_year and custom.bs_month == bs_month:
				return custom.start_date, custom.end_date, label, note
		return raw_start, raw_end, label, note

	def bs_year_for(fy_name, bs_month):
		"""A fiscal year starts on Shrawan 1. Months 4-12 belong to its opening
		BS year; months 1-3 (Baisakh–Ashadh) roll into the next one."""
		fy = frappe.get_cached_doc("Fiscal Year", fy_name)
		opening = ad_to_bs(getdate(fy.year_start_date)).year
		return opening if bs_month >= 4 else opening + 1

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


def _parse_bs_month(value):
	"""Accept '7', 7, '07 - Kartik', 'Kartik' — return int 1-12."""
	if value is None or value == "":
		frappe.throw(_("BS Month is required."))
	if isinstance(value, int):
		return value
	s = str(value).strip()
	digits = ""
	for ch in s:
		if ch.isdigit():
			digits += ch
		else:
			break
	if digits:
		return int(digits)
	low = s.lower()
	for num, name in BS_MONTH_NAMES.items():
		if name.lower() == low:
			return num
	frappe.throw(_("Could not parse BS Month: {0}").format(value))


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

def _shift_roster(employees, ad_start, ad_end):
	"""{employee: shift} from Shift Assignment, for days with no Attendance."""
	emp_names = [e.name for e in employees]
	if not emp_names:
		return {}
	roster = {}
	for row in frappe.get_all(
		"Shift Assignment",
		filters={
			"employee": ["in", emp_names],
			"docstatus": 1,
			"start_date": ["<=", ad_end],
		},
		or_filters=[["end_date", "is", "not set"], ["end_date", ">=", ad_start]],
		fields=["employee", "shift_type"],
		order_by="start_date asc",
		limit_page_length=0,
	):
		roster[row.employee] = row.shift_type
	return roster


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
		],
	)
	out = {}
	for r in rows:
		out[(r.employee, getdate(r.attendance_date))] = r
	return out


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


def _shift_window(shift_name, cache):
	"""Return (start_seconds, end_seconds) for shift, or (None, None)."""
	if not shift_name:
		return (None, None)
	if shift_name in cache:
		return cache[shift_name]
	row = frappe.db.get_value(
		"Shift Type", shift_name, ["start_time", "end_time"], as_dict=True
	)
	if not row:
		cache[shift_name] = (None, None)
		return (None, None)
	out = (_to_seconds(row.start_time), _to_seconds(row.end_time))
	cache[shift_name] = out
	return out


def _to_seconds(val):
	if val is None:
		return None
	if hasattr(val, "total_seconds"):
		return int(val.total_seconds())
	parts = str(val).split(":")
	return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(float(parts[2]) if len(parts) > 2 else 0)




def _build_row(emp, ad_date, bs_label, weekday, att_map, emp_holidays, leave_map, components, shift_cache, roster=None):
	holiday = emp_holidays.get(ad_date)
	leave_type = leave_map.get((emp.name, ad_date))
	att = att_map.get((emp.name, ad_date))

	in_time_str = ""
	out_time_str = ""
	working_hours = ""
	status = ""
	late_min = 0
	early_exit_min = 0
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
		working_hours = _fmt_hours(att.working_hours)
		if att.in_time:
			in_time_str = _fmt_time(att.in_time)
		if att.out_time:
			out_time_str = _fmt_time(att.out_time)
		if (holiday or work_in_holiday) and status in ("Present", "Half Day"):
			work_in_holiday = 1
		if att.custom_worked_on_holiday and status in ("Present", "Half Day"):
			work_in_holiday = 1
		shift_start, shift_end = _shift_window(att.shift, shift_cache)
		if att.in_time and shift_start is not None:
			diff = _time_of_day_seconds(att.in_time) - shift_start
			if att.late_entry and diff > 0:
				late_min = diff // 60
		if att.out_time and shift_end is not None:
			diff_end = shift_end - _time_of_day_seconds(att.out_time)
			if diff_end > 0:
				early_exit_min = diff_end // 60
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
		"shift": (att.shift if att else None) or (roster or {}).get(emp.name) or emp.default_shift,
		"department": emp.department,
		"in_time": in_time_str,
		"out_time": out_time_str,
		"working_hours": working_hours,
		"status": status,
		"late_minutes": int(late_min),
		"before_office_minutes": int(early_exit_min),
		"leave_count": leave_flag,
		"work_in_holiday": work_in_holiday,
		"remarks": remarks,
		"holidays_col": holidays_col,
	}
	row.update(component_values)
	return row


def _accumulate(totals, row):
	totals["late_min"] += row["late_minutes"]
	status = row["status"]
	if row["work_in_holiday"]:
		totals["holiday"] += 1
	elif status in ("Present", "Half Day"):
		totals["office"] += 1
	if row["leave_count"]:
		totals["leave"] += 1


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


def _time_of_day_seconds(dt):
	if hasattr(dt, "hour"):
		return dt.hour * 3600 + dt.minute * 60 + dt.second
	s = str(dt)
	t = s.split(" ")[-1] if " " in s else s
	parts = t.split(":")
	return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(float(parts[2]) if len(parts) > 2 else 0)


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
		{"label": _("IN"), "fieldname": "in_time", "fieldtype": "Data", "width": 85},
		{"label": _("OUT"), "fieldname": "out_time", "fieldtype": "Data", "width": 85},
		{"label": _("Hours"), "fieldname": "working_hours", "fieldtype": "Data", "width": 65, "align": "right"},
		{"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 95},
		{"label": _("Late (min)"), "fieldname": "late_minutes", "fieldtype": "Int", "width": 80},
		{"label": _("Before ofc. Time"), "fieldname": "before_office_minutes", "fieldtype": "Int", "width": 110},
		{"label": _("Leave"), "fieldname": "leave_count", "fieldtype": "Check", "width": 65},
		{"label": _("Work In Holiday"), "fieldname": "work_in_holiday", "fieldtype": "Check", "width": 110},
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


def _summary(office_days, holiday_days, total_worked, leave_days, late_min, bs_label):
	return [
		{"value": bs_label, "label": _("BS Period"), "datatype": "Data"},
		{"value": total_worked, "label": _("Total Days Worked"), "datatype": "Int"},
		{"value": office_days, "label": _("Worked on Office Day"), "datatype": "Int"},
		{"value": holiday_days, "label": _("Worked on Holiday"), "datatype": "Int"},
		{"value": leave_days, "label": _("Leave Days"), "datatype": "Int"},
		{"value": late_min, "label": _("Late Time (min)"), "datatype": "Int"},
	]


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
