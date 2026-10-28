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
    priced (Additional Salary → Quantity / Rate). OT is exact to the second,
    so OT Hr. and its rate show four decimals and OT Time the h:mm:ss behind
    them: hours × rate gives the OT column to the paisa;
  * tea, OT, meal and the late fine are found by the Condition Type that
    prices them, not by name: each site names them its own way ("Tea &
    Convience", "late comers deduction"), and a name the layout did not know
    put tea among the fixed allowances, inside Regular Salary, and left the
    late fine without its hours or rate;
  * the section is the employee's Department → Payroll Section, the same one
    the payroll journal posts by (payroll/payroll_entry.py);
  * the summary checks the totals against the payroll journal: gross against
    its expense debits, net against its credit to the payroll payable account.

The month is chosen as on the Payroll Entry: Fiscal Year + BS Month, dates
from hr/bs_calendar.py (Nepal BS Period first).

Payout picks which slips of the month: the month's salary (the default), or a
Dashain / leave encashment payout, each paid on slips of its own
(payroll/special_payout.py). One kind at a time, so a person never shows twice
and the journal check compares the sheet with that payout's own journal.
Previous Net Pay is always last month's salary slip.
"""

import frappe
from frappe import _
from frappe.utils import add_days, flt, fmt_money

from avinashgroup_app.hr.bs_calendar import bs_year_of, get_default_month, month_of_date, month_period
from avinashgroup_app.payroll.allowance import get_section
from avinashgroup_app.payroll.special_payout import PAYOUT_TYPES, REGULAR_SLIPS, slip_kind_filter

#: Payroll Section (Department) → the sheet's own label, in the sheet's order.
SECTION_LABELS = {"Admin & Accounts": "O/O", "Marketing": "S/D", "Plant": "F/P"}
NO_SECTION = "No Section"

#: The sheet's columns, in its order (Falgun 2082 sheets). Any other component
#: on the slips is added after its group, so nothing is left out of a total.
#: Fixed allowances are matched by name, ignoring case.
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
#: Attendance pay by the Condition Type that prices it (payroll/attendance_allowance.py),
#: in the sheet's order, with the sheet's label. Tea is the per-day-present one.
TEA, OT, MEAL, LATE = "Status = Present", "Authorised Overtime", "Meal Entitlement", "Late Time"
ATTENDANCE_LABELS = {TEA: "Tea Conveyance", OT: "OT", MEAL: "Meal"}
DEDUCTIONS_BEFORE_LATE = (("SSF", "SSF"), ("Income Tax", "Tax"))
DEDUCTIONS_AFTER_LATE = (("Salary Advance", "Regular Advance"), ("Dashain Advance", "Dashain Advance"))
BASIC, SSF_ADDITION = "Basic", "SSF Addition"
#: Quantity columns: (field, rate field, condition whose Additional Salary holds the count).
QUANTITIES = (("ot_hours", "ot_rate", OT), ("meal_qty", None, MEAL), ("late_hours", "late_rate", LATE))


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if not (filters.fiscal_year and filters.bs_month):
		default = get_default_month(filters.company)
		filters.fiscal_year, filters.bs_month = default["fiscal_year"], default["bs_month"]
	period = month_period(filters.company, bs_year_of(filters.fiscal_year, filters.bs_month), filters.bs_month)
	docstatus = 0 if str(filters.docstatus or "").startswith("0") else 1

	slips = get_slips(filters, period, docstatus)
	if not slips:
		return base_columns(), [], _("No {0} slips for {1}.").format(payout_of(filters) or _("salary"), period.label)

	names = [s.name for s in slips]
	amounts, defaults, components = get_details(names)
	roles = component_roles(components)
	layout = column_layout(components, roles)
	quantities = get_quantities(names, roles)
	present = get_present_days(slips)
	initial_basic = get_initial_basic(slips)
	prev_net = get_prev_net(filters.company, period, [s.employee for s in slips])

	rows = []
	for s in slips:
		row = sheet_row(s, layout, amounts.get(s.name, {}), defaults.get(s.name, {}))
		row.slip = s.name
		row.update(quantities.get(s.name, {}))
		row["attendance"] = present.get(s.name, 0)
		row["initial_basic"] = initial_basic.get(s.name, 0)
		row["prev_net_pay"] = prev_net.get(s.employee, 0)
		rows.append(row)

	columns = base_columns() + layout_columns(layout)
	data = grouped(rows, numeric_fields(columns))
	summary = report_summary(rows, slips, docstatus, amounts)
	message = _("{0}: {1} to {2} ({3}).").format(period.label, period.start_date, period.end_date, period.source)
	if payout_of(filters):
		message = _("{0} payout. ").format(payout_of(filters)) + message
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
	conditions.update(slip_kind_filter(payout_of(filters)))
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


def component_roles(components):
	"""{component: Condition Type} for the attendance-driven ones on the slips."""
	return {
		c.name: c.custom_condition_type
		for c in frappe.get_all(
			"Salary Component",
			filters={"name": ("in", list(components) or [""]), "custom_is_attendance_driven": 1},
			fields=["name", "custom_condition_type"],
		)
	}


def get_quantities(slip_names, roles):
	"""{slip: {ot_hours, ot_time, meal_qty, late_hours, ot_rate, late_rate}}
	from the Additional Salary each line came from."""
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
		for qty_field, rate_field, condition in QUANTITIES:
			if roles.get(r.salary_component) == condition:
				q[qty_field] = q.get(qty_field, 0) + flt(r.qty)
				if rate_field:
					q[rate_field] = flt(r.rate)
	for q in out.values():
		if q.get("ot_hours"):
			q["ot_time"] = clock(q["ot_hours"])
	return out


def clock(hours):
	"""Hours as h:mm:ss, to the second the overtime was measured to."""
	seconds = round(flt(hours) * 3600)
	return "{0}:{1:02d}:{2:02d}".format(seconds // 3600, seconds % 3600 // 60, seconds % 60)


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


def payout_of(filters):
	"""The Payout the sheet shows: a payout type, or None for the month's salary."""
	return filters.get("payout_type") if filters.get("payout_type") in PAYOUT_TYPES else None


def get_prev_net(company, period, employees):
	"""Last month's net pay as paid: submitted slips, whichever slips this
	month's sheet shows (a draft month compared with draft last month showed 0)."""
	prev = month_of_date(company, add_days(period.start_date, -1))
	return {
		r.employee: flt(r.net_pay)
		for r in frappe.get_all(
			"Salary Slip",
			filters={
				"company": company,
				"docstatus": 1,
				"employee": ("in", employees),
				"start_date": (">=", prev.start_date),
				"end_date": ("<=", prev.end_date),
				**REGULAR_SLIPS,
			},
			fields=["employee", "net_pay"],
		)
	}


# ── layout ──────────────────────────────────────────────────────────────────


def column_layout(components, roles):
	"""The component columns in sheet order, each group followed by any
	component on the slips the sheet did not name.

	Attendance pay (tea, OT, meal) is never a fixed allowance, whatever its
	Is Allowance tick: it is paid by the days and hours, after Regular Salary.
	"""
	earnings = {c for c, field in components.items() if field == "earnings"}
	deductions = {c for c, field in components.items() if field == "deductions"}
	by_name = {c.lower(): c for c in components}

	def present(group):
		return [(by_name[name.lower()], label) for name, label in group if name.lower() in by_name]

	attendance = sorted(
		(c for c in earnings if c in roles),
		key=lambda c: (list(ATTENDANCE_LABELS).index(roles[c]) if roles[c] in ATTENDANCE_LABELS else len(ATTENDANCE_LABELS), c),
	)
	late = [(c, "Late Fine") for c in sorted(deductions) if roles.get(c) == LATE]
	fixed = present(FIXED_ALLOWANCES)
	named_deductions = present(DEDUCTIONS_BEFORE_LATE) + late + present(DEDUCTIONS_AFTER_LATE)
	named = {c for c, _l in fixed + named_deductions} | set(attendance) | {BASIC, SSF_ADDITION}

	extra_earnings = sorted(earnings - named)
	allowance_extras = [c for c in extra_earnings if frappe.get_cached_value("Salary Component", c, "custom_is_allowance")]
	other_earnings = [c for c in extra_earnings if c not in allowance_extras]
	return frappe._dict(
		allowances=fixed + [(c, c) for c in allowance_extras],
		attendance=[(c, ATTENDANCE_LABELS.get(roles[c], c)) for c in attendance],
		other_earnings=[(c, c) for c in other_earnings],
		deductions=named_deductions + [(c, c) for c in sorted(deductions - named)],
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
		{"label": _("OT Hr."), "fieldname": "ot_hours", "fieldtype": "Float", "precision": 4, "width": 85},
		{"label": _("OT Time"), "fieldname": "ot_time", "fieldtype": "Data", "width": 80},
		{"label": _("Meal Qty."), "fieldname": "meal_qty", "fieldtype": "Float", "precision": 0, "width": 75},
		{"label": _("Late Hr."), "fieldname": "late_hours", "fieldtype": "Float", "precision": 4, "width": 80},
		currency(_("Initial Basic"), "initial_basic"),
		currency(_("Basic Salary"), "basic_salary"),
		dict(currency(_("OT Rate/ Hr."), "ot_rate", 100), precision=4),
		dict(currency(_("Late Deduction Rate"), "late_rate", 100), precision=4),
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
	if total.get("ot_hours"):
		total.ot_time = clock(total.ot_hours)
	return total


# ── the check against the payroll journal ───────────────────────────────────


def report_summary(rows, slips, docstatus, amounts):
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
		cards += journal_check(rows, slips, net, amounts)
	return cards


def journal_check(rows, slips, net, amounts):
	"""Does the payroll journal say the same? Each section's gross against the
	journal's debits to that section's expense accounts, and net pay against
	its credit to the payroll payable account.

	An earning whose account is not an expense (SSF Addition booked to SSF
	Payable on NGI) never reaches an expense debit, so it is left out of the
	sheet's side too and named on a card: the gap is the set-up, not the sheet.

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
	account_section, clashes = section_of_accounts(company)
	off_expense = earnings_not_expensed(company)
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
		booked = r.gross_pay - sum(flt(amounts.get(r.slip, {}).get(c)) for c in off_expense)
		sheet[r.section] = sheet.get(r.section, 0) + booked
	# (what, journal, sheet) for each figure that disagrees.
	differences = [
		(_("{0} expense").format(sec), journal.get(sec, 0), sheet.get(sec, 0))
		for sec in sorted(set(journal) | set(sheet))
		if abs(journal.get(sec, 0) - sheet.get(sec, 0)) >= 0.5
	]
	if abs(journal_net - net) >= 0.5:
		differences.append((_("Net payable"), journal_net, net))
	names = ", ".join(sorted(vouchers))
	setup = [
		{
			"label": _("{0}: {1} column").format(component, section),
			"value": _("holds the {0} account {1}").format(first, account.split(" - ")[0]),
			"datatype": "Data",
			"indicator": "Red",
		}
		for component, account, first, section in clashes
	] + [
		{
			"label": _("{0}: not an expense").format(component),
			"value": _("posts to {0}; left out of the gross check").format(account.split(" - ")[0]),
			"datatype": "Data",
			"indicator": "Orange",
		}
		for component, account in sorted(off_expense.items())
		if any(flt(amounts.get(r.slip, {}).get(component)) for r in rows)
	]
	if not differences:
		return [{"label": _("Matches Journal"), "value": names, "datatype": "Data", "indicator": "Green"}] + setup
	# A slip cancelled after its entry was posted is still in the journal (NGI
	# Shrawan: NGI-SAL-83/84-00021, 43,080.51 net); name it, it is the usual gap.
	setup += [
		{
			"label": _("Cancelled after posting: {0}").format(c.name),
			"value": _("{0}, net {1}, still in the journal").format(c.employee_name, fmt_money(c.net_pay)),
			"datatype": "Data",
			"indicator": "Red",
		}
		for c in frappe.get_all(
			"Salary Slip",
			filters={"payroll_entry": ("in", entries), "docstatus": 2},
			fields=["name", "employee_name", "net_pay"],
			order_by="name",
		)
	]
	return setup + [
		{
			"label": _("{0}: journal {1}").format(what, fmt_money(in_journal)),
			"value": _("{0} vs sheet").format(fmt_money(in_journal - in_sheet)),
			"datatype": "Data",
			"indicator": "Red",
		}
		for what, in_journal, in_sheet in differences
	] + [{"label": _("Journal"), "value": names, "datatype": "Data", "indicator": "Red"}]


def section_of_accounts(company):
	"""({expense account: section label}, [accounts set for two sections]).

	Each column of a component's account row names a section: the row's own
	account O/O, then S/D and F/P. A row with one account in every column is
	not split by section and is skipped. Read column by column, O/O first, so the
	answer never depends on which row comes first; an account a row puts under
	another section too is a set-up mistake and is returned, not guessed (NGN
	Education Allowance's S/D column held the O/O ledger, October 2026).
	"""
	rows = [
		row
		for row in frappe.get_all(
			"Salary Component Account",
			filters={"company": company, "parenttype": "Salary Component"},
			fields=["parent", "account", "custom_account_marketing", "custom_account_plant"],
		)
		# One account for every section is a component not split by section
		# (SSF, tax, the late fine): nothing to clash.
		if len({row.account, row.custom_account_marketing or row.account, row.custom_account_plant or row.account}) > 1
	]
	out, clashes = {}, []
	for fieldname, section in (("account", "O/O"), ("custom_account_marketing", "S/D"), ("custom_account_plant", "F/P")):
		for row in rows:
			account = row.get(fieldname)
			if not account:
				continue
			if account in out and out[account] != section:
				clashes.append((row.parent, account, out[account], section))
				continue
			out[account] = section
	return out, clashes


def earnings_not_expensed(company):
	"""{earning: its account} for earnings booked to an account that is not an
	expense, so the journal's expense debits never include them."""
	rows = frappe.db.sql(
		"""
		select sca.parent, sca.account
		from `tabSalary Component Account` sca
		join `tabSalary Component` sc on sc.name = sca.parent
		join `tabAccount` acc on acc.name = sca.account
		where sca.company = %(company)s and sca.parenttype = 'Salary Component'
			and sc.type = 'Earning' and acc.root_type != 'Expense'
		""",
		{"company": company},
		as_dict=True,
	)
	return {r.parent: r.account for r in rows}
