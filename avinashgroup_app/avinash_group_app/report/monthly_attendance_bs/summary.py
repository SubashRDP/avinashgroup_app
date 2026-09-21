"""
Monthly Attendance BS — Summary view
====================================
One row per employee for the selected BS month.

Reached from the Monthly Attendance BS report with View = Summary; the Detail
view of that same report is the per-day grid. They were two reports until they
were merged: one period resolution, one employee fetch, one set of filters, two
shapes of the same month.

Mirrors the Nepal Gas Udhyog physical attendance sheet:
  • Employee Code, Name, Department
  • Meal              = sum(Food qty + Late Food qty)
  • Tea & Conveyance  = sum(Tea qty + Commute qty)
  • Tihar             = sum(Tihar component qty, when component exists)
  • O.T. (hrs)        = hr.shift_day.measure_day, summed: hours outside the day's
                        shift (all hours on a holiday), to the half hour,
                        overtime-eligible staff only — the figure overtime pay uses
  • Late Time (min)   = late arrival + leaving early, against the day's shift,
                        as the sheet's card adds them (Late + Before ofc. Time)
  • Present Days      = count(Present + WFH) + 0.5 × count(Half Day)
  • Worked on Holiday = count(custom_worked_on_holiday=1 AND status in Present/Half Day)
  • Leave Current     = approved Leave Application days within the BS month
  • Leave Previous    = approved Leave Application days within the previous BS month
  • Leave Upto Month  = cumulative approved leave from BS fiscal year start (Shrawan) → end of selected month

Reuses period resolution, employee fetch, and bulk fetches from the per-day report module.
"""

import bisect

import frappe
from frappe import _
from frappe.utils import getdate, flt, add_days

from rdp_common_app.utils.bs_boundaries import (
	ad_to_bs,
	bs_to_ad,
	get_bs_month_range,
	get_bs_month_name,
)
from avinashgroup_app.hr.shift_day import measure_day, overtime_eligibility
from avinashgroup_app.hr.utils import resolve_holiday_lists
from avinashgroup_app.payroll.attendance_allowance import (
	evaluate_rule,
	get_attendance_driven_components,
	get_present_statuses,
)
from avinashgroup_app.avinash_group_app.report.monthly_attendance_bs.monthly_attendance_bs import (  # noqa: E501
	_note_html,
	_resolve_period,
	_get_employees,
	_fetch_attendance,
	_fetch_holidays,
	_fetch_leaves,
)




def _build_column_spec(components):
	"""Group attendance-driven Salary Components by their custom_summary_group field.

	Returns (groups, standalone) where:
	  • groups:     list of (slug, label, [member_sc_names]) in order of first occurrence
	  • standalone: list of components with no summary group (one column each, in
	                 the order returned by get_attendance_driven_components)

	The grouping is driven entirely by Salary Component config — no hardcoding.
	"""
	groups_by_label = {}
	groups_order = []
	standalone = []
	for sc in components:
		label = (sc.custom_summary_group or "").strip()
		if not label:
			standalone.append(sc)
			continue
		if label not in groups_by_label:
			groups_by_label[label] = []
			groups_order.append(label)
		groups_by_label[label].append(sc.name)
	groups = [(_slugify(label), label, groups_by_label[label]) for label in groups_order]
	return groups, standalone


def _slugify(value):
	raw = "".join(c.lower() if c.isalnum() else "_" for c in value)
	# Collapse runs of underscores and trim leading/trailing
	parts = [p for p in raw.split("_") if p]
	return "_".join(parts) or "group"


def _component_slug(component_name):
	return f"sc_{_slugify(component_name)}"


def _group_fieldname(slug):
	return f"grp_{slug}"


def execute_summary(filters):
	filters = frappe._dict(filters or {})

	ad_start, ad_end, bs_label, note = _resolve_period(filters)
	if ad_end < ad_start:
		frappe.throw(_("To Date cannot be before From Date"))

	employees = _get_employees(filters, ad_start, ad_end)
	components = get_attendance_driven_components()
	groups, standalone_components = _build_column_spec(components)

	columns = _columns(groups, standalone_components)

	if not employees:
		return columns, [], _note_html(note), None, _summary([], bs_label)

	company = filters.get("company")
	att_map = _fetch_attendance(employees, ad_start, ad_end, company)
	# Employee.holiday_list is blank for nearly everyone; the list is set on the
	# Company and inherited. Resolve that fallback for the whole roster.
	holiday_list_of = resolve_holiday_lists(employees)
	holiday_map = _fetch_holidays(holiday_list_of, ad_start, ad_end)
	# Bucket each leave map ONCE into {employee: sorted [dates]} so per-employee
	# leave counting is a bounded bisect instead of a full scan of every entry.
	leave_dates = _bucket_leave_dates(_fetch_leaves(employees, ad_start, ad_end, company))

	# Previous-month leave map
	prev_start, prev_end = _previous_bs_month_range(ad_start)
	prev_leave_dates = _bucket_leave_dates(
		_fetch_leaves(employees, prev_start, prev_end, company) if prev_start else {}
	)

	# FY-to-month-end leave map
	fy_start = _bs_fy_start(ad_start)
	upto_leave_dates = _bucket_leave_dates(
		_fetch_leaves(employees, fy_start, ad_end, company) if fy_start else {}
	)

	leave_windows = {
		"current":  (leave_dates,       ad_start, ad_end),
		"previous": (prev_leave_dates,  prev_start, prev_end),
		"upto":     (upto_leave_dates,  fy_start, ad_end),
	}

	ot_eligible = overtime_eligibility(employees)

	data = []
	for idx, emp in enumerate(employees, start=1):
		row = _build_summary_row(
			idx, emp, ad_start, ad_end,
			att_map, holiday_map, holiday_list_of, leave_windows,
			components, groups, standalone_components, ot_eligible.get(emp.name),
		)
		data.append(row)

	return columns, data, _note_html(note), _chart(data), _summary(data, bs_label)


# ---------------------------------------------------------------------------
# Row builder
# ---------------------------------------------------------------------------

def _build_summary_row(
	idx, emp, ad_start, ad_end,
	att_map, holiday_map, holiday_list_of, leave_windows,
	components, groups, standalone_components, ot_eligible=False,
):
	emp_holidays = holiday_map.get(holiday_list_of.get(emp.name), {})

	# Per-component qty totals (only attendance-driven components count)
	component_totals = {sc.name: 0.0 for sc in components}

	late_min_total = 0
	ot_hours_total = 0.0
	present_days = 0.0
	worked_on_holiday = 0

	present_statuses = get_present_statuses()

	day_count = (ad_end - ad_start).days + 1
	for offset in range(day_count):
		ad_date = getdate(add_days(ad_start, offset))
		att = att_map.get((emp.name, ad_date))
		if not att:
			continue
		status = att.status or ""

		# Present-day count (includes WFH; Half Day counts 0.5)
		if status in present_statuses:
			present_days += 1.0
		elif status == "Half Day":
			present_days += 0.5

		# Worked on holiday count
		if att.custom_worked_on_holiday and status in present_statuses + ("Half Day",):
			worked_on_holiday += 1

		# Against the day's shift, by the same measure as the per-day grid and
		# overtime pay. This used to need HRMS's `late_entry` flag, which nothing
		# here sets, and counted every minute anyone stayed late as overtime.
		measured = measure_day(att, is_holiday=ad_date in emp_holidays, ot_eligible=ot_eligible)
		late_min_total += measured.late_minutes + measured.early_exit_minutes
		ot_hours_total += measured.ot_hours

		# Sum each attendance-driven component's per-day qty
		for sc in components:
			try:
				qty = evaluate_rule(att, sc, emp.name)
			except Exception:
				qty = 0
			if qty:
				component_totals[sc.name] += flt(qty)

	# Collapse component totals into group columns (per custom_summary_group field).
	group_values = {}
	for slug, _label, members in groups:
		total = 0.0
		for n in members:
			total += component_totals.get(n, 0.0)
		group_values[_group_fieldname(slug)] = flt(total)

	# Standalone components → one dynamic column each (any component with no summary group).
	standalone_values = {
		_component_slug(sc.name): flt(component_totals.get(sc.name, 0.0))
		for sc in standalone_components
	}

	# Leave counts: count of (employee, date) entries falling inside each window
	leave_current = _leave_days_for(emp.name, *leave_windows["current"])
	leave_previous = _leave_days_for(emp.name, *leave_windows["previous"])
	leave_upto = _leave_days_for(emp.name, *leave_windows["upto"])

	row = {
		"sn": idx,
		"employee": emp.name,
		"employee_number": emp.employee_number or "",
		"employee_name": emp.employee_name,
		"department": emp.department or "",
		"ot_hours": flt(ot_hours_total, 1),
		"late_minutes": int(late_min_total),
		"present_days": flt(present_days, 1),
		"worked_on_holiday": worked_on_holiday,
		"leave_current": leave_current,
		"leave_previous": leave_previous,
		"leave_upto": leave_upto,
	}
	row.update(group_values)
	row.update(standalone_values)
	return row


def _bucket_leave_dates(leave_map):
	"""Pre-bucket a (employee, date) -> leave_type map into {employee: sorted [dates]}.

	`_fetch_leaves` returns one entry per unrolled day of each overlapping Leave
	Application, keyed by (employee, date). Bucketing once (single pass) lets each
	per-employee, per-window count be a bounded bisect instead of a full scan of
	every entry across all employees.
	"""
	buckets = {}
	for (emp, d) in (leave_map or {}):
		buckets.setdefault(emp, []).append(d)
	for dates in buckets.values():
		dates.sort()
	return buckets


def _leave_days_for(employee, leave_dates, range_start, range_end):
	"""Count this employee's leave dates falling within [range_start, range_end].

	`leave_dates` is the bucketed {employee: sorted [dates]} map produced by
	`_bucket_leave_dates`. The underlying dates can lie outside the intended window
	(applications are unrolled fully), so we bound here to stop previous/upto counts
	bleeding across windows. Equivalent to counting (employee, date) entries where
	range_start <= date <= range_end, but via bisect on the sorted per-employee list.
	"""
	if not leave_dates or range_start is None or range_end is None:
		return 0
	dates = leave_dates.get(employee)
	if not dates:
		return 0
	lo = bisect.bisect_left(dates, range_start)
	hi = bisect.bisect_right(dates, range_end)
	return hi - lo


# ---------------------------------------------------------------------------
# BS period helpers (previous month, fiscal-year start)
# ---------------------------------------------------------------------------

def _previous_bs_month_range(ad_date):
	"""AD range covering the BS month immediately before the one containing ad_date."""
	bs = ad_to_bs(ad_date)
	if bs.month == 1:
		prev_year, prev_month = bs.year - 1, 12
	else:
		prev_year, prev_month = bs.year, bs.month - 1
	return get_bs_month_range(prev_year, prev_month)


def _bs_fy_start(ad_date):
	"""AD date of Shrawan 1 of the BS fiscal year containing ad_date.

	Fiscal year runs Shrawan (4) → Ashadh (3 of next year).
	"""
	bs = ad_to_bs(ad_date)
	fy_year = bs.year if bs.month >= 4 else bs.year - 1
	return bs_to_ad(fy_year, 4, 1)


# ---------------------------------------------------------------------------
# Columns + summary card
# ---------------------------------------------------------------------------

def _columns(groups, standalone_components):
	cols = [
		# S.N. + Employee are FROZEN by the report JS — see FROZEN_FIELDS in
		# monthly_attendance_bs.js. They must stay contiguous and leading.
		# Employee renders name over ID as one clickable cell; see the note on
		# the matching column in monthly_attendance_bs.py.
		{"label": _("S.N."), "fieldname": "sn", "fieldtype": "Int", "width": 60},
		{"label": _("Employee"), "fieldname": "employee", "fieldtype": "Data", "width": 190},
		{"label": _("Department"), "fieldname": "department", "fieldtype": "Link", "options": "Department", "width": 130},
	]
	# Grouped columns — one per Salary Component custom_summary_group value.
	for slug, label, _members in groups:
		cols.append({
			"label": label,
			"fieldname": _group_fieldname(slug),
			"fieldtype": "Float",
			"width": 110,
			"precision": 2,
		})
	# Standalone columns — one per attendance-driven Salary Component without a summary group.
	for sc in standalone_components:
		cols.append({
			"label": sc.name,
			"fieldname": _component_slug(sc.name),
			"fieldtype": "Float",
			"width": 90,
			"precision": 2,
		})
	cols.extend([
		{"label": _("O.T. (hrs)"), "fieldname": "ot_hours", "fieldtype": "Float", "width": 90, "precision": 2},
		{"label": _("Late Time (min)"), "fieldname": "late_minutes", "fieldtype": "Int", "width": 110},
		{"label": _("Present Days"), "fieldname": "present_days", "fieldtype": "Float", "width": 100, "precision": 1},
		{"label": _("Worked on Holiday"), "fieldname": "worked_on_holiday", "fieldtype": "Int", "width": 130},
		{"label": _("Leave (Current)"), "fieldname": "leave_current", "fieldtype": "Float", "width": 110, "precision": 1},
		{"label": _("Leave (Prev Month)"), "fieldname": "leave_previous", "fieldtype": "Float", "width": 130, "precision": 1},
		{"label": _("Leave (Upto Month)"), "fieldname": "leave_upto", "fieldtype": "Float", "width": 130, "precision": 1},
	])
	return cols


def _summary(data, bs_label):
	if not data:
		return [
			{"value": bs_label, "label": _("BS Period"), "datatype": "Data"},
			{"value": 0, "label": _("Employees"), "datatype": "Int"},
		]
	return [
		{"value": bs_label, "label": _("BS Period"), "datatype": "Data"},
		{"value": len(data), "label": _("Employees"), "datatype": "Int"},
		{"value": sum(r["present_days"] for r in data), "label": _("Total Present Days"), "datatype": "Float"},
		{"value": sum(r["worked_on_holiday"] for r in data), "label": _("Total Worked on Holiday"), "datatype": "Int"},
		{"value": sum(r["ot_hours"] for r in data), "label": _("Total O.T. (hrs)"), "datatype": "Float"},
		{"value": sum(r["late_minutes"] for r in data), "label": _("Total Late (min)"), "datatype": "Int"},
	]


def _chart(data):
	"""How the whole roster attended, as a distribution — not a ranking.

	This used to chart the twelve people with the most late minutes, worst
	first, by name. Three things were wrong with that. It answered a question
	nobody had asked of a monthly summary; it showed twelve of a hundred and
	seven with no way to reach the rest; and a named league table of lateness
	is a document that gets forwarded, which is not what an attendance report
	is for.

	A histogram answers what the summary is actually for — "how did the month
	go" — and answers it for every employee at once. Most of the roster stacks
	up on the right at a full month; anyone worth following up shows as height
	on the left, as a count rather than a name. The grid directly below is
	where names belong, sortable on any column.
	"""
	if not data:
		return None

	days = [round(flt(r.get("present_days"))) for r in data]
	if not any(days):
		return None

	# One bar per whole day-count somebody actually reached, ascending. Bucketing
	# into ranges would hide the detail most worth seeing: the gap between a full
	# month and one day short of it.
	counts = {}
	for d in days:
		counts[d] = counts.get(d, 0) + 1
	order = sorted(counts)

	return {
		"data": {
			"labels": [str(d) for d in order],
			"datasets": [{"name": _("Employees"), "values": [counts[d] for d in order]}],
		},
		"type": "bar",
		"colors": ["#2b8a5e"],
		"axisOptions": {"shortenYAxisNumbers": 1},
		"height": 260,
	}
