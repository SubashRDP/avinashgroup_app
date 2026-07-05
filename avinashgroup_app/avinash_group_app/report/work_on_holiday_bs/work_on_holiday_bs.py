

import frappe
from frappe import _
from frappe.utils import getdate

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
	holiday_work_map = _count_worked_on_holiday(
		emp_names, ad_start, ad_end, filters.get("company")
	)

	data = []
	for idx, emp in enumerate(employees, start=1):
		row = {
			"sno": idx,
			"employee_name": emp.employee_name,
			"ot_eligibility": "Yes" if emp.custom_ot_eligibility else "No",
		}
		month_counts = holiday_work_map.get(emp.name, {})
		total = 0
		for bs_month in FY_MONTH_ORDER:
			n = int(month_counts.get(bs_month, 0))
			row[_month_field(bs_month)] = n
			total += n
		row["total"] = total
		data.append(row)

	report_summary = [
		{"label": _("Fiscal Year"), "value": fy_label, "indicator": "Blue"},
		{"label": _("Employees"), "value": len(employees), "indicator": "Grey"},
		{
			"label": _("Total Holiday Work Days"),
			"value": sum(r["total"] for r in data),
			"indicator": "Green",
		},
	]
	return _columns(), data, None, None, report_summary


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

	ot_choice = (filters.get("ot_eligibility") or "All").strip()
	if ot_choice == "No":
		emp_filters["custom_ot_eligibility"] = 0
	elif ot_choice == "Yes":
		emp_filters["custom_ot_eligibility"] = 1
	# "All" → no filter added (matches the Excel "Work On Holiday" sheet, which lists every staff member)

	return frappe.get_all(
		"Employee",
		filters=emp_filters,
		fields=[
			"name",
			"employee_name",
			"department",
			"company",
			"custom_ot_eligibility",
		],
		order_by="employee_name asc",
	)


# ---------------------------------------------------------------------------
# Worked-on-holiday count, bucketed by BS month
# ---------------------------------------------------------------------------

def _count_worked_on_holiday(emp_names, ad_start, ad_end, company=None):
	"""Return {employee: {bs_month: count}} from Attendance rows where
	custom_worked_on_holiday = 1 in the FY window.
	"""
	if not emp_names:
		return {}
	att_filters = {
		"employee": ["in", emp_names],
		"attendance_date": ["between", [ad_start, ad_end]],
		"custom_worked_on_holiday": 1,
		"docstatus": ["!=", 2],
	}
	if company:
		att_filters["company"] = company
	rows = frappe.get_all(
		"Attendance",
		filters=att_filters,
		fields=["employee", "attendance_date"],
	)
	by_emp = {}
	# Attendance dates repeat heavily across rows; convert each distinct date once.
	bs_month_cache = {}
	for r in rows:
		d = getdate(r.attendance_date)
		bs_month = bs_month_cache.get(d)
		if bs_month is None:
			bs_month = ad_to_bs(d).month
			bs_month_cache[d] = bs_month
		bucket = by_emp.setdefault(r.employee, {})
		bucket[bs_month] = bucket.get(bs_month, 0) + 1
	return by_emp


# ---------------------------------------------------------------------------
# Columns
# ---------------------------------------------------------------------------

def _month_field(bs_month):
	return f"bs_{bs_month:02d}"


def _columns():
	cols = [
		{"label": _("S.N."), "fieldname": "sno", "fieldtype": "Int", "width": 60},
		{"label": _("Name Of Staff"), "fieldname": "employee_name",
		 "fieldtype": "Data", "width": 220},
		{"label": _("OT Eligibility"), "fieldname": "ot_eligibility",
		 "fieldtype": "Data", "width": 110},
	]
	for bs_month in FY_MONTH_ORDER:
		cols.append({
			"label": BS_MONTH_NAMES[bs_month],
			"fieldname": _month_field(bs_month),
			"fieldtype": "Int",
			"width": 85,
		})
	cols.append({
		"label": _("Total"),
		"fieldname": "total",
		"fieldtype": "Int",
		"width": 100,
	})
	return cols
