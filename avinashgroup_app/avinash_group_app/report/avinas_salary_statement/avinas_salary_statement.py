"""The salary sheet, from the submitted slips: what the client's Excel showed.

Each company used to run payroll on its own Excel sheet (the Falgun 2082
sheets, docs/allowances.md): one row per person, the columns from attendance
through Basic, allowances, tea, OT, meal, gross, SSF, tax, late fine, advances
to Net Payable, and people grouped O/O, S/D, F/P with a subtotal each, because
that is how the books charge salary. This report prints the same sheet from the
slips, so HR and accounts can lay it beside the old one and see the same
figures.

It reproduces the payroll, it never recomputes it:

  * every amount is the slip's own (Salary Detail), and Gross, Total Deduction
    and Net Payable are the slip's totals; a component the layout does not
    name still gets its own column, so the columns always add up to them;
  * Basic Salary is the full month (the row's default amount), Deduction what
    unpaid days took off it, Net Basic what was paid, as the sheet splits it;
  * OT hours, meals and late hours are the quantities Prepare Payroll Inputs
    priced (Additional Salary → Quantity / Rate);
  * the section is the employee's Department → Payroll Section, the same one
    the payroll journal posts by (payroll/payroll_entry.py);
  * the summary checks the totals against the payroll journal: gross against
    its expense debits, net against its credit to the payroll payable account.

The month is chosen as on the Payroll Entry: Fiscal Year + BS Month, dates
from hr/bs_calendar.py (Nepal BS Period first).
"""

import frappe
from frappe import _
from frappe.utils import add_days, flt, fmt_money

from avinashgroup_app.hr.bs_calendar import bs_year_of, get_default_month, month_of_date, month_period
from avinashgroup_app.payroll.allowance import get_section

#: Payroll Section (Department) → the sheet's own label, in the sheet's order.
SECTION_LABELS = {"Admin & Accounts": "O/O", "Marketing": "S/D", "Plant": "F/P"}
NO_SECTION = "No Section"

#: The sheet's columns, in its order (Falgun 2082 sheets). Any other component
#: on the slips is added after its group, so nothing is left out of a total.
FIXED_ALLOWANCES = (
	("House Rent Allowance", "HRA"),
	("Dearness Allowance", "Dearness Allowance"),
	("Other Allowance", "Other Allowance"),
	("Fixed Allowance", "Fixed Allowance"),
	("Fuel Allowance", "Fuel Allowance"),
	("Maintenance Allowance", "Maintenance Allowance"),
	("Gas Allowance", "Gas"),
	("Education Allowance", "Edu"),
)
ATTENDANCE_EARNINGS = (("Tea & Conveyance", "Tea Conveyance"), ("Overtime", "OT"), ("Meal", "Meal"))
DEDUCTIONS = (
	("SSF", "SSF"),
	("Income Tax", "Tax"),
	("Late Fine", "Late Fine"),
	("Salary Advance", "Regular Advance"),
	("Dashain Advance", "Dashain Advance"),
)
BASIC, SSF_ADDITION = "Basic", "SSF Addition"
#: Quantity columns: the component whose Additional Salary holds the count.
QUANTITIES = (("ot_hours", "OT Hr.", "Overtime"), ("meal_qty", "Meal Qty.", "Meal"), ("late_hours", "Late Hr.", "Late Fine"))


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if not (filters.fiscal_year and filters.bs_month):
		default = get_default_month(filters.company)
		filters.fiscal_year, filters.bs_month = default["fiscal_year"], default["bs_month"]
	period = month_period(filters.company, bs_year_of(filters.fiscal_year, filters.bs_month), filters.bs_month)
	docstatus = 0 if str(filters.docstatus or "").startswith("0") else 1

	slips = get_slips(filters, period, docstatus)
	if not slips:
		return base_columns(), [], _("No salary slips for {0}.").format(period.label)

	names = [s.name for s in slips]
	amounts, defaults, components = get_details(names)
	layout = column_layout(components)
	quantities = get_quantities(names)
	present = get_present_days(slips)
	initial_basic = get_initial_basic(slips)
	prev_net = get_prev_net(filters.company, period, [s.employee for s in slips], docstatus)

	rows = []
	for s in slips:
		row = sheet_row(s, layout, amounts.get(s.name, {}), defaults.get(s.name, {}))
		row.update(quantities.get(s.name, {}))
		row["attendance"] = present.get(s.name, 0)
		row["initial_basic"] = initial_basic.get(s.name, 0)
		row["prev_net_pay"] = prev_net.get(s.employee, 0)
		rows.append(row)

	columns = base_columns() + layout_columns(layout)
	data = grouped(rows, numeric_fields(columns))
	summary = report_summary(rows, slips, docstatus)
	message = _("{0}: {1} to {2} ({3}).").format(period.label, period.start_date, period.end_date, period.source)
	return columns, data, message, None, summary


# ── data ────────────────────────────────────────────────────────────────────


def get_slips(filters, period, docstatus):
	conditions = {
		"company": filters.company,
		"docstatus": docstatus,
		"start_date": (">=", period.start_date),
		"end_date": ("<=", period.end_date),
	}
	if filters.payroll_entry:
		conditions["payroll_entry"] = filters.payroll_entry
	slips = frappe.get_all(
		"Salary Slip",
		filters=conditions,
		fields=[
			"name", "company", "employee", "employee_name", "department", "designation", "payroll_entry",
			"start_date", "end_date", "total_working_days", "payment_days",
			"gross_pay", "total_deduction", "net_pay",
		],
		order_by="employee",
	)
	# Today's department, not the one copied onto the slip when it was made: the
	# section (and the journal) follow the employee's department too.
	departments = dict(
		frappe.get_all("Employee", filters={"name": ("in", [s.employee for s in slips])}, fields=["name", "department"], as_list=True)
	)
	for s in slips:
		s.department = departments.get(s.employee) or s.department
		s.section = SECTION_LABELS.get(get_section(s.employee), NO_SECTION)
	return slips


def get_details(slip_names):
	"""({slip: {component: amount}}, {slip: {component: full-month amount}},
	{component: (type, row)}) for components with an amount on any slip."""
	amounts, defaults, components = {}, {}, {}
	for d in frappe.get_all(
		"Salary Detail",
		filters={"parent": ("in", slip_names), "parenttype": "Salary Slip"},
		fields=["parent", "parentfield", "salary_component", "amount", "default_amount", "do_not_include_in_total", "statistical_component"],
	):
		if d.statistical_component or d.do_not_include_in_total:
			continue
		slip = amounts.setdefault(d.parent, {})
		slip[d.salary_component] = slip.get(d.salary_component, 0) + flt(d.amount)
		full = defaults.setdefault(d.parent, {})
		full[d.salary_component] = full.get(d.salary_component, 0) + flt(d.default_amount)
		if flt(d.amount):
			components[d.salary_component] = d.parentfield
	return amounts, defaults, components


def get_quantities(slip_names):
	"""{slip: {ot_hours, meal_qty, late_hours, ot_rate, late_rate}} from the
	Additional Salary each line came from."""
	rows = frappe.db.sql(
		"""
		select d.parent, d.salary_component, a.custom_quantity qty, a.custom_rate rate
		from `tabSalary Detail` d
		join `tabAdditional Salary` a on a.name = d.additional_salary
		where d.parent in %(slips)s and d.parenttype = 'Salary Slip'
		""",
		{"slips": slip_names},
		as_dict=True,
	)
	out = {}
	for r in rows:
		q = out.setdefault(r.parent, {})
		for field, _label, component in QUANTITIES:
			if r.salary_component == component:
				q[field] = q.get(field, 0) + flt(r.qty)
		if r.salary_component == "Overtime":
			q["ot_rate"] = flt(r.rate)
		elif r.salary_component == "Late Fine":
			q["late_rate"] = flt(r.rate)
	return out


def get_present_days(slips):
	"""Days at work in the slip's period, as the sheet's Attendance column
	counts them: a half day is half."""
	from avinashgroup_app.payroll.attendance_allowance import get_present_statuses

	present_statuses = get_present_statuses()
	out = {}
	for s in slips:
		days = 0.0
		for a in frappe.get_all(
			"Attendance",
			filters={"employee": s.employee, "docstatus": 1, "attendance_date": ("between", [s.start_date, s.end_date])},
			fields=["status"],
		):
			if a.status == "Half Day":
				days += 0.5
			elif a.status in present_statuses:
				days += 1
		out[s.name] = days
	return out


def get_initial_basic(slips):
	out = {}
	for s in slips:
		out[s.name] = flt(
			frappe.db.get_value(
				"Salary Structure Assignment",
				{"employee": s.employee, "docstatus": 1, "from_date": ("<=", s.end_date)},
				"custom_initial_basic",
				order_by="from_date desc",
			)
		)
	return out


def get_prev_net(company, period, employees, docstatus):
	prev = month_of_date(company, add_days(period.start_date, -1))
	return {
		r.employee: flt(r.net_pay)
		for r in frappe.get_all(
			"Salary Slip",
			filters={
				"company": company,
				"docstatus": docstatus,
				"employee": ("in", employees),
				"start_date": (">=", prev.start_date),
				"end_date": ("<=", prev.end_date),
			},
			fields=["employee", "net_pay"],
		)
	}


# ── layout ──────────────────────────────────────────────────────────────────


def column_layout(components):
	"""The component columns in sheet order, each group followed by any
	component on the slips the sheet did not name."""
	earnings = {c for c, field in components.items() if field == "earnings"}
	deductions = {c for c, field in components.items() if field == "deductions"}
	named = {c for c, _l in FIXED_ALLOWANCES + ATTENDANCE_EARNINGS + DEDUCTIONS} | {BASIC, SSF_ADDITION}

	def present(group):
		return [(c, label) for c, label in group if c in components]

	extra_earnings = sorted(earnings - named)
	allowance_extras = [c for c in extra_earnings if frappe.get_cached_value("Salary Component", c, "custom_is_allowance")]
	other_earnings = [c for c in extra_earnings if c not in allowance_extras]
	return frappe._dict(
		allowances=present(FIXED_ALLOWANCES) + [(c, c) for c in allowance_extras],
		attendance=present(ATTENDANCE_EARNINGS),
		other_earnings=[(c, c) for c in other_earnings],
		deductions=present(DEDUCTIONS) + [(c, c) for c in sorted(deductions - named)],
	)


def field(component):
	return "c_" + frappe.scrub(component)


def sheet_row(s, layout, amounts, defaults):
	row = frappe._dict(
		employee=s.employee,
		employee_name=s.employee_name,
		department=s.department,
		designation=s.designation,
		section=s.section,
		unpaid_days=flt(s.total_working_days) - flt(s.payment_days),
	)
	row.basic_salary = flt(defaults.get(BASIC))
	row.net_basic = flt(amounts.get(BASIC))
	row.basic_deduction = row.basic_salary - row.net_basic
	row.ssf_addition = flt(amounts.get(SSF_ADDITION))

	for group in ("allowances", "attendance", "other_earnings", "deductions"):
		for component, _label in layout[group]:
			row[field(component)] = flt(amounts.get(component))
	row.total_allowance = sum(row[field(c)] for c, _l in layout.allowances)
	row.regular_salary = row.net_basic + row.ssf_addition + row.total_allowance
	row.gross_pay = flt(s.gross_pay)
	row.total_deduction = flt(s.total_deduction)
	row.net_pay = flt(s.net_pay)
	return row


def currency(label, fieldname, width=110):
	return {"label": label, "fieldname": fieldname, "fieldtype": "Currency", "width": width}


def base_columns():
	return [
		{"label": _("S. No."), "fieldname": "sn", "fieldtype": "Data", "width": 55},
		{"label": _("Employee"), "fieldname": "employee", "fieldtype": "Link", "options": "Employee", "width": 125},
		{"label": _("Employee Name"), "fieldname": "employee_name", "fieldtype": "Data", "width": 170},
		{"label": _("Section"), "fieldname": "section", "fieldtype": "Data", "width": 70},
		{"label": _("Department"), "fieldname": "department", "fieldtype": "Link", "options": "Department", "width": 140},
		{"label": _("Designation"), "fieldname": "designation", "fieldtype": "Link", "options": "Designation", "width": 120},
		{"label": _("Attendance"), "fieldname": "attendance", "fieldtype": "Float", "precision": 1, "width": 90},
		{"label": _("OT Hr."), "fieldname": "ot_hours", "fieldtype": "Float", "precision": 2, "width": 70},
		{"label": _("Meal Qty."), "fieldname": "meal_qty", "fieldtype": "Float", "precision": 0, "width": 75},
		{"label": _("Late Hr."), "fieldname": "late_hours", "fieldtype": "Float", "precision": 2, "width": 70},
		currency(_("Initial Basic"), "initial_basic"),
		currency(_("Basic Salary"), "basic_salary"),
		currency(_("OT Rate/ Hr."), "ot_rate", 95),
		currency(_("Late Deduction Rate"), "late_rate", 95),
		{"label": _("Unpaid Leave"), "fieldname": "unpaid_days", "fieldtype": "Float", "precision": 1, "width": 80},
		currency(_("Deduction"), "basic_deduction", 100),
		currency(_("Net Basic"), "net_basic"),
		currency(_("SSF Addition"), "ssf_addition"),
	]


def layout_columns(layout):
	cols = [currency(_(label), field(c)) for c, label in layout.allowances]
	cols += [currency(_("Total Allowance"), "total_allowance"), currency(_("Regular Salary"), "regular_salary", 120)]
	cols += [currency(_(label), field(c), 100) for c, label in layout.attendance]
	cols += [currency(_(label), field(c)) for c, label in layout.other_earnings]
	cols.append(currency(_("Gross Salary"), "gross_pay", 120))
	cols += [currency(_(label), field(c), 100) for c, label in layout.deductions]
	cols += [
		currency(_("Total Deduction"), "total_deduction", 115),
		currency(_("Net Payable"), "net_pay", 120),
		currency(_("Last Month Net"), "prev_net_pay", 115),
	]
	return cols


NON_NUMERIC = {"Data", "Link"}
#: Rates are per person; a subtotal of rates means nothing.
NOT_TOTALLED = {"ot_rate", "late_rate", "sn"}


def numeric_fields(columns):
	return [c["fieldname"] for c in columns if c["fieldtype"] not in NON_NUMERIC and c["fieldname"] not in NOT_TOTALLED]


def grouped(rows, numeric):
	"""The sheet: each section's people, its subtotal; then the sections'
	summary and the grand total."""
	order = list(SECTION_LABELS.values()) + [NO_SECTION]
	data, subtotals, sn = [], [], 0
	for section in order:
		people = [r for r in rows if r.section == section]
		if not people:
			continue
		for r in people:
			sn += 1
			r.sn = str(sn)
			data.append(r)
		total = total_row(people, numeric, _("Sub Total {0}").format(section))
		total.section = section
		data.append(total)
		subtotals.append(total)
	if len(subtotals) > 1:
		data.append({})
		for t in subtotals:
			data.append(frappe._dict(t, employee_name=_("Sub Total {0}").format(t.section)))
	data.append(total_row(rows, numeric, _("Grand Total")))
	return data


def total_row(rows, numeric, label):
	total = frappe._dict(employee_name=label, bold=1)
	for f in numeric:
		total[f] = sum(flt(r.get(f)) for r in rows)
	return total


# ── the check against the payroll journal ───────────────────────────────────


def report_summary(rows, slips, docstatus):
	gross = sum(r.gross_pay for r in rows)
	deductions = sum(r.total_deduction for r in rows)
	net = sum(r.net_pay for r in rows)
	cards = [
		{"label": _("Employees"), "value": len(rows), "datatype": "Int"},
		{"label": _("Gross Salary"), "value": gross, "datatype": "Currency"},
		{"label": _("Total Deduction"), "value": deductions, "datatype": "Currency"},
		{"label": _("Net Payable"), "value": net, "datatype": "Currency", "indicator": "Blue"},
	]
	if docstatus == 1:
		cards += journal_check(rows, slips, net)
	return cards


def journal_check(rows, slips, net):
	"""Does the payroll journal say the same? Each section's gross against the
	journal's debits to that section's expense accounts, and net pay against
	its credit to the payroll payable account.

	HRMS tags only the payable lines with the Payroll Entry, so the journal is
	found through them and read whole.
	"""
	entries = sorted({s.payroll_entry for s in slips if s.payroll_entry})
	if not entries:
		return [{"label": _("Payroll Journal"), "value": _("No payroll entry"), "datatype": "Data", "indicator": "Orange"}]
	payable = set(
		frappe.get_all("Payroll Entry", filters={"name": ("in", entries)}, pluck="payroll_payable_account")
	)
	vouchers = frappe.db.sql_list(
		"""
		select distinct a.parent from `tabJournal Entry Account` a
		join `tabJournal Entry` je on je.name = a.parent
		where a.reference_type = 'Payroll Entry' and a.reference_name in %(entries)s
			and je.docstatus = 1 and je.voucher_type = 'Journal Entry'
		""",
		{"entries": entries},
	)
	if not vouchers:
		return [{"label": _("Payroll Journal"), "value": _("Not posted"), "datatype": "Data", "indicator": "Orange"}]
	lines = frappe.db.sql(
		"""
		select a.account, a.debit_in_account_currency dr, a.credit_in_account_currency cr, acc.root_type
		from `tabJournal Entry Account` a join `tabAccount` acc on acc.name = a.account
		where a.parent in %(vouchers)s
		""",
		{"vouchers": vouchers},
		as_dict=True,
	)
	company = slips[0].company
	account_section = section_of_accounts(company)
	journal = {}
	for l in lines:
		if l.root_type == "Expense":
			section = account_section.get(l.account, "?")
			# Debits only: a deduction booked back to an expense account (the
			# late fine) is a credit line of its own, and the sheet keeps it
			# under deductions, not in gross.
			journal[section] = journal.get(section, 0) + flt(l.dr)
	journal_net = sum(flt(l.cr) - flt(l.dr) for l in lines if l.account in payable)

	sheet = {}
	for r in rows:
		sheet[r.section] = sheet.get(r.section, 0) + r.gross_pay
	# (what, journal, sheet) for each figure that disagrees.
	differences = [
		(_("{0} expense").format(sec), journal.get(sec, 0), sheet.get(sec, 0))
		for sec in sorted(set(journal) | set(sheet))
		if abs(journal.get(sec, 0) - sheet.get(sec, 0)) >= 0.5
	]
	if abs(journal_net - net) >= 0.5:
		differences.append((_("Net payable"), journal_net, net))
	names = ", ".join(sorted(vouchers))
	if not differences:
		return [{"label": _("Matches Journal"), "value": names, "datatype": "Data", "indicator": "Green"}]
	return [
		{
			"label": _("{0}: journal {1}").format(what, fmt_money(in_journal)),
			"value": _("{0} vs sheet").format(fmt_money(in_journal - in_sheet)),
			"datatype": "Data",
			"indicator": "Red",
		}
		for what, in_journal, in_sheet in differences
	] + [{"label": _("Journal"), "value": names, "datatype": "Data", "indicator": "Red"}]


def section_of_accounts(company):
	"""{expense account: section label} from the salary components' account rows
	(the row's own account is O/O, then the S/D and F/P columns)."""
	out = {}
	for row in frappe.get_all(
		"Salary Component Account",
		filters={"company": company, "parenttype": "Salary Component"},
		fields=["account", "custom_account_marketing", "custom_account_plant"],
	):
		for fieldname, section in (("custom_account_plant", "F/P"), ("custom_account_marketing", "S/D"), ("account", "O/O")):
			if row.get(fieldname):
				out.setdefault(row.get(fieldname), section)
	return out
