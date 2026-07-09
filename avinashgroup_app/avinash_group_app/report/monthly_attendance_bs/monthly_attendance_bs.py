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
from frappe.utils import getdate, flt, strip_html_tags

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

	ad_start, ad_end, bs_label = _resolve_period(filters)
	if ad_end < ad_start:
		frappe.throw(_("To Date cannot be before From Date"))

	employees = _get_employees(filters, ad_start, ad_end)
	components = get_attendance_driven_components()

	if not employees:
		return _columns(components), [], None, None, _summary(0, 0, 0, 0, 0, bs_label)

	company = filters.get("company")
	att_map = _fetch_attendance(employees, ad_start, ad_end, company)
	holiday_map = _fetch_holidays(employees, ad_start, ad_end)
	leave_map = _fetch_leaves(employees, ad_start, ad_end, company)
	shift_cache = {}

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
		bs_label = f"{bs.day:02d} {get_bs_month_name(bs.month)}"
		weekday = DAY_NAMES[ad_date.weekday()]
		date_info[ad_date] = (bs_label, weekday)

	for emp in employees:
		emp_holidays = holiday_map.get(emp.holiday_list, {})
		for ad_date in dates:
			bs_label, weekday = date_info[ad_date]
			row = _build_row(
				emp, ad_date, bs_label, weekday, att_map, emp_holidays, leave_map,
				components, shift_cache,
			)
			data.append(row)
			_accumulate(totals, row)

	return (
		_columns(components),
		data,
		None,
		None,
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
	"""Return (ad_start, ad_end, bs_label_for_header).

	Priority: Fiscal Year + BS Month wins when both are set. Only fall back to
	From Date + To Date when those filters are blank — otherwise Frappe's
	Date-type widgets (which can retain values across runs) would silently
	override a freshly-picked BS month.
	"""
	if filters.get("fiscal_year") and filters.get("bs_month"):
		bs_month = _parse_bs_month(filters.bs_month)
		fy = frappe.get_cached_doc("Fiscal Year", filters.fiscal_year)
		# FY starts on Shrawan 1 of some BS year. Months 4-12 belong to that BS
		# year; months 1-3 (Baisakh–Ashadh) roll into the next BS year.
		fy_start_bs_year = ad_to_bs(getdate(fy.year_start_date)).year
		bs_year = fy_start_bs_year if bs_month >= 4 else fy_start_bs_year + 1
		company = filters.get("company")

		raw_start, raw_end = get_bs_month_range(bs_year, bs_month)
		if company:
			custom = get_user_defined_period(raw_start, company)
			if custom and custom.bs_year == bs_year and custom.bs_month == bs_month:
				return custom.start_date, custom.end_date, f"{get_bs_month_name(bs_month)} {bs_year}"

		return raw_start, raw_end, f"{get_bs_month_name(bs_month)} {bs_year}"

	if filters.get("from_date") and filters.get("to_date"):
		ad_start = getdate(filters.from_date)
		ad_end = getdate(filters.to_date)
		bs_s = ad_to_bs(ad_start)
		bs_e = ad_to_bs(ad_end)
		if bs_s.year == bs_e.year and bs_s.month == bs_e.month:
			label = f"{get_bs_month_name(bs_s.month)} {bs_s.year}"
		else:
			label = (
				f"{bs_s.day} {get_bs_month_name(bs_s.month)} → "
				f"{bs_e.day} {get_bs_month_name(bs_e.month)} {bs_e.year}"
			)
		return ad_start, ad_end, label

	frappe.throw(_("Select Fiscal Year + BS Month or From Date + To Date to run the report."))


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
# Employee fetch (honors User Permissions via frappe.get_all)
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

	emp_filters.append(["Employee", "date_of_joining", "<=", ad_end])

	# Either still employed (no relieving date) or relieved after the period start.
	emp_or_filters = [
		["Employee", "relieving_date", "is", "not set"],
		["Employee", "relieving_date", ">", ad_start],
	]

	return frappe.get_all(
		"Employee",
		filters=emp_filters,
		or_filters=emp_or_filters,
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


def _fetch_holidays(employees, ad_start, ad_end):
	"""Return {holiday_list_name: {date: {description, weekly_off}}}."""
	lists = list({e.holiday_list for e in employees if e.holiday_list})
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




def _build_row(emp, ad_date, bs_label, weekday, att_map, emp_holidays, leave_map, components, shift_cache):
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
	base = [
		{"label": _("BS Date"), "fieldname": "bs_date", "fieldtype": "Data", "width": 110},
		{"label": _("AD Date"), "fieldname": "ad_date", "fieldtype": "Date", "width": 100},
		{"label": _("Day"), "fieldname": "day", "fieldtype": "Data", "width": 60},
		{"label": _("Employee"), "fieldname": "employee", "fieldtype": "Link", "options": "Employee", "width": 130},
		{"label": _("Name"), "fieldname": "employee_name", "fieldtype": "Data", "width": 150},
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
