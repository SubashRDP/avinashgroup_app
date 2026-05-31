import frappe
from frappe import _
from frappe.utils import flt
from itertools import groupby
from rdp_common_app.utils.bs_boundaries import get_bs_month_range


def execute(filters):
	filters = frappe._dict(filters or {})

	# Parse filter values
	bs_year = int(filters.bs_year)
	bs_month = _parse_select(filters.bs_month)
	company = filters.company
	docstatus = _parse_select(filters.docstatus)

	# Get AD dates for current month
	start_date, end_date = get_bs_month_range(bs_year, bs_month)

	# Get AD dates for previous month
	if bs_month > 1:
		prev_year, prev_month = bs_year, bs_month - 1
	else:
		prev_year, prev_month = bs_year - 1, 12
	prev_start, prev_end = get_bs_month_range(prev_year, prev_month)

	# Fetch salary slips ordered by designation, employee
	salary_slips = get_salary_slips(company, start_date, end_date, docstatus)

	if not salary_slips:
		columns = build_columns([], [])
		return columns, []

	slip_names = [s.name for s in salary_slips]

	# Get earning and deduction component types
	earning_types, ded_types = get_component_types(slip_names)

	# Pivot earnings and deductions by slip
	earn_map = get_details_map(slip_names, "earnings")
	ded_map = get_details_map(slip_names, "deductions")

	# Get previous month's net pay for each employee
	employees = list({s.employee for s in salary_slips})
	prev_net_map = get_prev_net_pay(employees, prev_start, prev_end, company, docstatus)

	# Get employee numbers
	emp_numbers = _get_employee_numbers(employees)

	# Build columns and data
	columns = build_columns(earning_types, ded_types)
	data = build_data(salary_slips, earning_types, ded_types, earn_map, ded_map, prev_net_map, emp_numbers)

	return columns, data


def _parse_select(value):
	"""Accept '11 - Falgun', '11', or 11 → int."""
	if isinstance(value, int):
		return value
	return int(str(value).strip().split(" ")[0])


def get_salary_slips(company, start_date, end_date, docstatus):
	"""Fetch all salary slips for the period, ordered by designation, employee."""
	ss = frappe.qb.DocType("Salary Slip")
	query = (
		frappe.qb.from_(ss)
		.select(
			ss.name, ss.employee, ss.employee_name,
			ss.designation, ss.start_date, ss.end_date,
			ss.gross_pay, ss.net_pay, ss.docstatus,
		)
		.where(ss.company == company)
		.where(ss.start_date >= start_date)
		.where(ss.end_date <= end_date)
		.where(ss.docstatus == int(docstatus))
		.orderby(ss.designation)
		.orderby(ss.employee)
	)
	return query.run(as_dict=True) or []


def get_component_types(slip_names):
	"""Get sorted lists of earning and deduction component names."""
	if not slip_names:
		return [], []

	sd = frappe.qb.DocType("Salary Detail")
	rows = (
		frappe.qb.from_(sd)
		.select(sd.salary_component, sd.parentfield)
		.distinct()
		.where(sd.parent.isin(slip_names))
		.where(sd.amount != 0)
	).run(as_dict=True)

	earnings = sorted({r.salary_component for r in rows if r.parentfield == "earnings"})
	deductions = sorted({r.salary_component for r in rows if r.parentfield == "deductions"})
	return earnings, deductions


def get_details_map(slip_names, parentfield):
	"""Return {slip_name: {component_name: amount}} for the given parentfield."""
	if not slip_names:
		return {}

	sd = frappe.qb.DocType("Salary Detail")
	rows = (
		frappe.qb.from_(sd)
		.select(sd.parent, sd.salary_component, sd.amount)
		.where(sd.parent.isin(slip_names))
		.where(sd.parentfield == parentfield)
	).run(as_dict=True)

	result = {}
	for r in rows:
		result.setdefault(r.parent, {})
		result[r.parent][r.salary_component] = (
			result[r.parent].get(r.salary_component, 0.0) + flt(r.amount)
		)
	return result


def get_prev_net_pay(employees, prev_start, prev_end, company, docstatus):
	"""Return {employee_name: net_pay} for previous BS month."""
	if not employees:
		return {}

	ss = frappe.qb.DocType("Salary Slip")
	rows = (
		frappe.qb.from_(ss)
		.select(ss.employee, ss.net_pay)
		.where(ss.company == company)
		.where(ss.employee.isin(employees))
		.where(ss.start_date >= prev_start)
		.where(ss.end_date <= prev_end)
		.where(ss.docstatus == int(docstatus))
	).run(as_dict=True)

	result = {}
	for r in rows:
		result[r.employee] = flt(r.net_pay)
	return result


def _get_employee_numbers(employee_names):
	"""Return {employee_name: employee_number} in one query."""
	if not employee_names:
		return {}

	emp = frappe.qb.DocType("Employee")
	rows = (
		frappe.qb.from_(emp)
		.select(emp.name, emp.employee_number)
		.where(emp.name.isin(employee_names))
	).run(as_dict=True)
	return {r.name: r.employee_number or "" for r in rows}


def build_columns(earning_types, ded_types):
	"""Build column specifications."""
	cols = [
		{"label": _("S.N."), "fieldname": "sn", "fieldtype": "Int", "width": 50},
		{"label": _("Employee Code"), "fieldname": "employee_number", "fieldtype": "Data", "width": 110},
		{"label": _("Employee"), "fieldname": "employee", "fieldtype": "Link", "options": "Employee", "width": 120},
		{"label": _("Employee Name"), "fieldname": "employee_name", "fieldtype": "Data", "width": 160},
		{"label": _("Designation"), "fieldname": "designation", "fieldtype": "Link", "options": "Designation", "width": 130},
	]

	# Dynamic earning columns
	for e in earning_types:
		cols.append({
			"label": e,
			"fieldname": frappe.scrub(e),
			"fieldtype": "Currency",
			"width": 120,
		})

	# Gross Salary
	cols.append({
		"label": _("Gross Salary"),
		"fieldname": "gross_pay",
		"fieldtype": "Currency",
		"width": 130,
	})

	# Dynamic deduction columns
	for d in ded_types:
		cols.append({
			"label": d,
			"fieldname": frappe.scrub(d),
			"fieldtype": "Currency",
			"width": 120,
		})

	# Net Payable and Previous Month Net Pay
	cols.extend([
		{"label": _("Net Payable"), "fieldname": "net_pay", "fieldtype": "Currency", "width": 130},
		{"label": _("Prev Month Net Pay"), "fieldname": "prev_month_net_pay", "fieldtype": "Currency", "width": 140},
	])

	return cols


def build_data(salary_slips, earning_types, ded_types, earn_map, ded_map, prev_net_map, emp_numbers):
	"""Build data rows with sub-totals by designation."""
	data = []

	# List of numeric field names for totaling
	numeric_fields = (
		[frappe.scrub(e) for e in earning_types] +
		["gross_pay"] +
		[frappe.scrub(d) for d in ded_types] +
		["net_pay", "prev_month_net_pay"]
	)

	grand_totals = {f: 0.0 for f in numeric_fields}
	sn = 0

	# Group by designation
	for designation, group_slips in groupby(salary_slips, key=lambda s: s.designation or ""):
		group_list = list(group_slips)
		group_totals = {f: 0.0 for f in numeric_fields}

		for ss in group_list:
			sn += 1
			row = {
				"sn": sn,
				"employee_number": emp_numbers.get(ss.employee, ""),
				"employee": ss.employee,
				"employee_name": ss.employee_name,
				"designation": ss.designation,
			}

			# Earning components
			for e in earning_types:
				val = flt(earn_map.get(ss.name, {}).get(e, 0))
				row[frappe.scrub(e)] = val
				group_totals[frappe.scrub(e)] += val

			# Gross pay
			row["gross_pay"] = flt(ss.gross_pay)
			group_totals["gross_pay"] += flt(ss.gross_pay)

			# Deduction components
			for d in ded_types:
				val = flt(ded_map.get(ss.name, {}).get(d, 0))
				row[frappe.scrub(d)] = val
				group_totals[frappe.scrub(d)] += val

			# Net pay
			row["net_pay"] = flt(ss.net_pay)
			group_totals["net_pay"] += flt(ss.net_pay)

			# Previous month net pay
			prev = flt(prev_net_map.get(ss.employee, 0))
			row["prev_month_net_pay"] = prev
			group_totals["prev_month_net_pay"] += prev

			data.append(row)

		# Sub-total row for this designation
		sub_row = {
			"sn": "",
			"employee_number": "",
			"employee": "",
			"employee_name": _("Sub-Total: {0}").format(designation or _("No Designation")),
			"designation": "",
			"bold": 1,
		}
		sub_row.update(group_totals)
		data.append(sub_row)

		# Accumulate into grand totals
		for f in numeric_fields:
			grand_totals[f] += group_totals[f]

	# Grand total row
	grand_row = {
		"sn": "",
		"employee_number": "",
		"employee": "",
		"employee_name": _("Grand Total"),
		"designation": "",
		"bold": 1,
	}
	grand_row.update(grand_totals)
	data.append(grand_row)

	return data
