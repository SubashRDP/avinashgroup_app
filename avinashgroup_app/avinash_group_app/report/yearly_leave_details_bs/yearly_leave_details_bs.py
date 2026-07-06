"""Yearly Leave Details (BS)

One row per Employee for a BS fiscal year (Shrawan -> Ashad). Columns:

  S.No. | Name | Code | Department |
  Shrawan | Bhadra | Aswin | Kartik | Mansir | Poush |
  Magh | Falgun | Chaitra | Baisakh | Jestha | Ashad |
  Total Leave Days | Total Yearly Leave |
  Total Worked on Holiday | Leave Remaining | Remarks

Mirrors the Excel template "Yearly Leave Details F/Y 2082/083".

- Monthly cells: approved Leave Application days falling in that BS month
- Total Yearly Leave: sum of `new_leaves_allocated` from submitted Leave
  Allocations active in the FY window
- Worked on Holiday: count of Attendance rows with custom_worked_on_holiday=1
- Leave Remaining: Total Yearly Leave - Total Leave Days
"""

from datetime import timedelta

import frappe
from frappe import _
from frappe.utils import getdate, flt, add_days

from rdp_common_app.utils.bs_boundaries import (
	ad_to_bs,
	BS_MONTH_NAMES,
)


# Fiscal-year order of BS months: Shrawan (4) -> Ashad (3)
FY_MONTH_ORDER = [4, 5, 6, 7, 8, 9, 10, 11, 12, 1, 2, 3]


def execute(filters=None):
	filters = frappe._dict(filters or {})
	ad_start, ad_end, fy_label = _fy_window(filters)
	employees = _get_employees(filters)
	if not employees:
		return _columns(), [], None, None

	emp_names = [e.name for e in employees]
	leave_taken_map = _aggregate_leave_taken(emp_names, ad_start, ad_end)
	allocation_map = _aggregate_allocation(emp_names, ad_start, ad_end)
	holiday_work_map = _count_worked_on_holiday(emp_names, ad_start, ad_end, filters.get("company"))

	data = []
	for idx, emp in enumerate(employees, start=1):
		row = {
			"sno": idx,
			"employee": emp.name,
			"employee_name": emp.employee_name,
			"code": emp.employee_number or "",
			"department": emp.department or "",
		}
		month_days = leave_taken_map.get(emp.name, {})
		total_taken = 0.0
		for bs_month in FY_MONTH_ORDER:
			days = flt(month_days.get(bs_month, 0))
			row[_month_field(bs_month)] = days
			total_taken += days
		yearly_alloc = flt(allocation_map.get(emp.name, 0))
		worked_holiday = holiday_work_map.get(emp.name, 0)
		row["total_leave_days"] = flt(total_taken, 2)
		row["total_yearly_leave"] = flt(yearly_alloc, 2)
		row["total_worked_on_holiday"] = worked_holiday
		row["leave_remaining"] = flt(yearly_alloc - total_taken, 2)
		row["remarks"] = ""
		data.append(row)

	chart = None
	report_summary = [
		{"label": _("Fiscal Year"), "value": fy_label, "indicator": "Blue"},
		{"label": _("Employees"), "value": len(employees), "indicator": "Grey"},
		{
			"label": _("Total Leave Days"),
			"value": flt(sum(r["total_leave_days"] for r in data), 2),
			"indicator": "Orange",
		},
		{
			"label": _("Total Holiday Work Days"),
			"value": sum(r["total_worked_on_holiday"] for r in data),
			"indicator": "Green",
		},
	]
	return _columns(), data, None, chart, report_summary


# ---------------------------------------------------------------------------
# Filter helpers
# ---------------------------------------------------------------------------

def _fy_window(filters):
	"""Return (ad_start, ad_end, label) from the selected Fiscal Year record."""
	fy_name = filters.get("fiscal_year")
	if not fy_name:
		frappe.throw(_("Fiscal Year is required."))
	fy = frappe.get_cached_doc("Fiscal Year", fy_name)
	return getdate(fy.year_start_date), getdate(fy.year_end_date), fy.name


# ---------------------------------------------------------------------------
# Employee fetch
# ---------------------------------------------------------------------------

def _get_employees(filters):
	emp_filters = {"status": filters.get("status") or "Active"}
	if filters.get("company"):
		emp_filters["company"] = filters.company
	if filters.get("department"):
		emp_filters["department"] = filters.department
	if filters.get("branch"):
		emp_filters["branch"] = filters.branch
	if filters.get("employee"):
		emp_filters["name"] = filters.employee
	return frappe.get_all(
		"Employee",
		filters=emp_filters,
		fields=["name", "employee_name", "employee_number", "department", "company"],
		order_by="employee_name asc",
	)


# ---------------------------------------------------------------------------
# Leave taken aggregation (split LA across BS months)
# ---------------------------------------------------------------------------

def _aggregate_leave_taken(emp_names, ad_start, ad_end):
	"""Return {employee: {bs_month: days}} from approved Leave Applications.

	Handles LA ranges that cross BS month boundaries by walking day-by-day.
	Half-day applications contribute 0.5 to whichever BS month the half_day_date
	(or from_date if not set) falls in.
	"""
	if not emp_names:
		return {}

	apps = frappe.get_all(
		"Leave Application",
		filters={
			"employee": ["in", emp_names],
			"status": "Approved",
			"docstatus": 1,
			"from_date": ["<=", ad_end],
			"to_date": [">=", ad_start],
		},
		fields=[
			"name", "employee", "from_date", "to_date",
			"total_leave_days", "half_day", "half_day_date",
		],
	)

	by_emp = {}
	# Overlapping leaves revisit the same calendar days; convert each date once.
	bs_cache = {}
	for la in apps:
		fd = getdate(la.from_date)
		td = getdate(la.to_date)
		span_days = (td - fd).days + 1
		if span_days <= 0:
			continue
		# Per-day weight: half_day=1 -> half-day on half_day_date, 1 elsewhere.
		# When half_day_date is missing or outside the span, distribute evenly
		# using total_leave_days / span_days (fallback for legacy data).
		hd_date = getdate(la.half_day_date) if la.half_day_date else None
		if la.half_day and hd_date and fd <= hd_date <= td:
			day_weights = {}
			for offset in range(span_days):
				d = fd + timedelta(days=offset)
				day_weights[d] = 0.5 if d == hd_date else 1.0
		else:
			per_day = flt(la.total_leave_days) / span_days if span_days else 0
			day_weights = {fd + timedelta(days=o): per_day for o in range(span_days)}

		emp_bucket = by_emp.setdefault(la.employee, {})
		for d, w in day_weights.items():
			if d < ad_start or d > ad_end:
				continue
			bs = bs_cache.get(d)
			if bs is None:
				bs = ad_to_bs(d)
				bs_cache[d] = bs
			emp_bucket[bs.month] = emp_bucket.get(bs.month, 0) + w

	return by_emp


# ---------------------------------------------------------------------------
# Yearly allocation aggregation
# ---------------------------------------------------------------------------

def _aggregate_allocation(emp_names, ad_start, ad_end):
	"""Return {employee: total_new_leaves_allocated} summed across leave types.

	An allocation counts toward the FY if its window overlaps the FY at all.
	Uses `new_leaves_allocated` (the fresh-allocated amount), not
	`total_leaves_allocated` which includes carry-forward.
	"""
	if not emp_names:
		return {}
	rows = frappe.get_all(
		"Leave Allocation",
		filters={
			"employee": ["in", emp_names],
			"docstatus": 1,
			"from_date": ["<=", ad_end],
			"to_date": [">=", ad_start],
		},
		fields=["employee", "new_leaves_allocated"],
	)
	by_emp = {}
	for r in rows:
		by_emp[r.employee] = by_emp.get(r.employee, 0) + flt(r.new_leaves_allocated)
	return by_emp


# ---------------------------------------------------------------------------
# Worked-on-holiday count
# ---------------------------------------------------------------------------

def _count_worked_on_holiday(emp_names, ad_start, ad_end, company=None):
	if not emp_names:
		return {}
	filters = {
		"employee": ["in", emp_names],
		"attendance_date": ["between", [ad_start, ad_end]],
		"custom_worked_on_holiday": 1,
		"docstatus": ["!=", 2],
	}
	if company:
		filters["company"] = company
	rows = frappe.get_all(
		"Attendance",
		filters=filters,
		fields=["employee"],
	)
	by_emp = {}
	for r in rows:
		by_emp[r.employee] = by_emp.get(r.employee, 0) + 1
	return by_emp


# ---------------------------------------------------------------------------
# Columns
# ---------------------------------------------------------------------------

def _month_field(bs_month):
	return f"bs_{bs_month:02d}"


def _columns():
	cols = [
		{"label": _("S.No."), "fieldname": "sno", "fieldtype": "Int", "width": 60},
		{"label": _("Employee"), "fieldname": "employee", "fieldtype": "Link",
		 "options": "Employee", "width": 130},
		{"label": _("Name Of Staff"), "fieldname": "employee_name",
		 "fieldtype": "Data", "width": 200},
		{"label": _("Code"), "fieldname": "code", "fieldtype": "Data", "width": 80},
		{"label": _("Department"), "fieldname": "department", "fieldtype": "Link",
		 "options": "Department", "width": 140},
	]
	for bs_month in FY_MONTH_ORDER:
		cols.append({
			"label": BS_MONTH_NAMES[bs_month],
			"fieldname": _month_field(bs_month),
			"fieldtype": "Float",
			"precision": 2,
			"width": 85,
		})
	cols.extend([
		{"label": _("Total Leave Days"), "fieldname": "total_leave_days",
		 "fieldtype": "Float", "precision": 2, "width": 120},
		{"label": _("Total Yearly Leave"), "fieldname": "total_yearly_leave",
		 "fieldtype": "Float", "precision": 2, "width": 130},
		{"label": _("Total Worked on Holiday"), "fieldname": "total_worked_on_holiday",
		 "fieldtype": "Int", "width": 150},
		{"label": _("Leave Remaining"), "fieldname": "leave_remaining",
		 "fieldtype": "Float", "precision": 2, "width": 120},
		{"label": _("Remarks"), "fieldname": "remarks", "fieldtype": "Data", "width": 180},
	])
	return cols
