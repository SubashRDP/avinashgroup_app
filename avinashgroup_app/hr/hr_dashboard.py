"""Data behind the HR Dashboard desk page (`/app/hr-dashboard`).

Stock HRMS spreads HR over four workspaces (HR, Leaves, Shift & Attendance,
Payroll) of link cards, with dashboards cut on Gregorian months. A clerk here
thinks in Bikram Sambat months and in "who is missing what", so this module
answers one question per BS month: how many people, did they come, who is off,
what did payroll cost, and what setup data is still blank.

Two entry points, both called from `avinash_group_app/page/hr_dashboard/`:

- `get_dashboard` — every number on the page for one BS month and one company
  (or every company the user may see).
- `get_menu` — the page's left-hand menu, filtered to the doctypes and reports
  the user can actually open, so nobody clicks into a permission error.

Deliberately read-only and aggregate-only: nothing here writes, and no figure
is computed differently from the report that owns it — attendance counts are
plain `tabAttendance` rows, payroll is plain `tabSalary Slip` totals. Month
boundaries come from `rdp_common_app.utils.bs_boundaries`, never frappe.utils.
"""

import datetime

import frappe
from frappe import _
from frappe.utils import flt, getdate, today

from rdp_common_app.utils.bs_boundaries import (
	ad_to_bs,
	get_bs_month_name,
	get_bs_month_range,
)

DASHBOARD_ROLES = ("HR Manager", "HR User", "System Manager")

# How far back the page looks for a month with data when none is asked for.
# The current BS month is empty until the first attendance run, and an empty
# dashboard on day 1 of every month teaches clerks to ignore it.
FALLBACK_MONTHS = 3

# Upcoming birthdays, anniversaries and holidays: the next month or so.
UPCOMING_DAYS = 30


@frappe.whitelist()
def get_dashboard(company=None, bs_year=None, bs_month=None):
	"""Every figure on the dashboard for one BS month.

	Picks the current BS month when none is given, falling back up to
	FALLBACK_MONTHS to the latest month that has attendance or salary slips.
	Raises PermissionError for users outside DASHBOARD_ROLES, or for a company
	the user has no permission on.
	"""
	frappe.only_for(DASHBOARD_ROLES)
	companies = _allowed_companies(company)

	if bs_year and bs_month:
		year, month = int(bs_year), int(bs_month)
	else:
		year, month = _default_month(companies)
	start, end = get_bs_month_range(year, month)

	return {
		"period": _period(year, month, start, end),
		"companies": _allowed_companies(None),
		"company": company or "",
		"headcount": _headcount(companies, start, end),
		"attendance": _attendance(companies, start, end),
		"today": _today(companies),
		# Pay is the one block more sensitive than the page itself: show it only
		# to someone who could open the slips anyway.
		"payroll": _payroll(companies, start) if frappe.has_permission("Salary Slip", "read") else None,
		"pending": _pending(companies),
		"gaps": _setup_gaps(companies),
		"upcoming": _upcoming(companies),
		"devices": _devices(companies),
	}


def _allowed_companies(company):
	allowed = frappe.get_list("Company", pluck="name", order_by="name")
	if not company:
		return allowed
	if company not in allowed:
		frappe.throw(_("Not permitted for company {0}").format(company), frappe.PermissionError)
	return [company]


def _default_month(companies):
	bs = ad_to_bs(getdate(today()))
	year, month = bs.year, bs.month
	for _step in range(FALLBACK_MONTHS + 1):
		start, end = get_bs_month_range(year, month)
		has_data = frappe.db.sql(
			"""select exists(select 1 from tabAttendance where docstatus=1
				and company in %(c)s and attendance_date between %(s)s and %(e)s)
			or exists(select 1 from `tabSalary Slip` where docstatus<2
				and company in %(c)s and start_date=%(s)s)""",
			{"c": companies, "s": start, "e": end},
		)[0][0]
		if has_data:
			return year, month
		year, month = (year - 1, 12) if month == 1 else (year, month - 1)
	return bs.year, bs.month


def _step_month(year, month, delta):
	index = year * 12 + (month - 1) + delta
	return index // 12, index % 12 + 1


def _period(year, month, start, end):
	prev_y, prev_m = _step_month(year, month, -1)
	next_y, next_m = _step_month(year, month, 1)
	bs_today = ad_to_bs(getdate(today()))
	return {
		"bs_year": year,
		"bs_month": month,
		"label": f"{get_bs_month_name(month)} {year}",
		"start": str(start),
		"end": str(end),
		"days": (end - start).days + 1,
		"is_current": (year, month) == (bs_today.year, bs_today.month),
		"prev": {"bs_year": prev_y, "bs_month": prev_m, "label": f"{get_bs_month_name(prev_m)} {prev_y}"},
		"next": {"bs_year": next_y, "bs_month": next_m, "label": f"{get_bs_month_name(next_m)} {next_y}"},
		"can_go_next": (next_y, next_m) <= (bs_today.year, bs_today.month),
	}


def _headcount(companies, start, end):
	rows = frappe.db.sql(
		"""select company, count(*) n, sum(gender='Female') women
		from tabEmployee where status='Active' and company in %(c)s
		group by company order by n desc""",
		{"c": companies},
		as_dict=True,
	)
	moves = frappe.db.sql(
		"""select
			sum(date_of_joining between %(s)s and %(e)s) joined,
			sum(relieving_date between %(s)s and %(e)s) left_
		from tabEmployee where company in %(c)s""",
		{"c": companies, "s": start, "e": end},
		as_dict=True,
	)[0]
	abbr = dict(frappe.get_all("Company", fields=["name", "abbr"], as_list=True))
	return {
		"active": sum(r.n for r in rows),
		"women": int(sum(flt(r.women) for r in rows)),
		"joined": int(flt(moves.joined)),
		"left": int(flt(moves.left_)),
		"by_company": [
			{"company": r.company, "abbr": abbr.get(r.company, r.company), "count": r.n} for r in rows
		],
	}


def _attendance(companies, start, end):
	"""Submitted Attendance rows in the month, per status and per day."""
	rows = frappe.db.sql(
		"""select attendance_date d, status, count(*) n, sum(late_entry) late
		from tabAttendance where docstatus=1 and company in %(c)s
			and attendance_date between %(s)s and %(e)s
		group by attendance_date, status""",
		{"c": companies, "s": start, "e": end},
		as_dict=True,
	)
	totals = {"Present": 0, "Half Day": 0, "Absent": 0, "On Leave": 0, "Work From Home": 0}
	late = 0
	by_day = {}
	for r in rows:
		totals[r.status] = totals.get(r.status, 0) + r.n
		late += int(flt(r.late))
		by_day.setdefault(str(r.d), {}).update({r.status: r.n})

	days = []
	current = start
	while current <= end:
		counts = by_day.get(str(current), {})
		days.append(
			{
				"date": str(current),
				"bs_day": ad_to_bs(current).day,
				"weekday": current.strftime("%a"),
				"present": counts.get("Present", 0) + counts.get("Work From Home", 0),
				"half_day": counts.get("Half Day", 0),
				"absent": counts.get("Absent", 0),
				"on_leave": counts.get("On Leave", 0),
			}
		)
		current += datetime.timedelta(days=1)

	marked = sum(totals.values())
	attended = totals["Present"] + totals["Work From Home"] + 0.5 * totals["Half Day"]
	return {
		"totals": totals,
		"marked": marked,
		"late": late,
		"rate": round(100.0 * attended / marked, 1) if marked else None,
		"days": days,
	}


def _today(companies):
	date = getdate(today())
	punched = frappe.db.sql(
		"""select count(distinct c.employee) from `tabEmployee Checkin` c
		join tabEmployee e on e.name=c.employee
		where e.company in %(c)s and c.time >= %(d)s and c.time < %(d)s + interval 1 day""",
		{"c": companies, "d": date},
	)[0][0]
	on_leave = frappe.db.sql(
		"""select count(distinct employee) from `tabLeave Application`
		where docstatus=1 and status='Approved' and company in %(c)s
			and %(d)s between from_date and to_date""",
		{"c": companies, "d": date},
	)[0][0]
	bs = ad_to_bs(date)
	return {
		"date": str(date),
		"bs_label": f"{bs.day} {get_bs_month_name(bs.month)} {bs.year}",
		"punched": punched,
		"on_leave": on_leave,
	}


def _payroll(companies, start):
	"""Salary Slips whose period starts on this BS month's first day."""
	rows = frappe.db.sql(
		"""select s.docstatus, count(*) n, sum(s.gross_pay) gross,
			sum(s.total_deduction) deduction, sum(s.net_pay) net,
			ifnull(e.payroll_cost_center, '') cost_center
		from `tabSalary Slip` s join tabEmployee e on e.name=s.employee
		where s.docstatus<2 and s.company in %(c)s and s.start_date=%(s)s
		group by s.docstatus, e.payroll_cost_center""",
		{"c": companies, "s": start},
		as_dict=True,
	)
	submitted = [r for r in rows if r.docstatus == 1]
	by_cc = {}
	for r in submitted:
		by_cc[r.cost_center or _("No cost centre")] = by_cc.get(r.cost_center or _("No cost centre"), 0) + flt(r.gross)
	return {
		"slips": sum(r.n for r in submitted),
		"draft_slips": sum(r.n for r in rows if r.docstatus == 0),
		"gross": sum(flt(r.gross) for r in submitted),
		"deduction": sum(flt(r.deduction) for r in submitted),
		"net": sum(flt(r.net) for r in submitted),
		"by_cost_center": sorted(
			({"label": k, "amount": v} for k, v in by_cc.items()), key=lambda x: -x["amount"]
		),
	}


def _pending(companies):
	"""Documents waiting on someone, each with the route that lists them."""
	checks = [
		("Leave Application", _("Leave requests"), {"status": "Open", "docstatus": 0}),
		("Attendance Request", _("Attendance requests"), {"docstatus": 0}),
		("Shift Request", _("Shift requests"), {"status": "Draft", "docstatus": 0}),
		("Employee Advance", _("Advances"), {"docstatus": 0}),
		("Overtime Sheet", _("Overtime sheets"), {"docstatus": 0}),
		("Payroll Entry", _("Payroll runs"), {"docstatus": 0}),
	]
	out = []
	for doctype, label, filters in checks:
		if not frappe.has_permission(doctype, "read"):
			continue
		filters = dict(filters, company=["in", companies])
		count = frappe.db.count(doctype, filters)
		if count:
			out.append({"doctype": doctype, "label": label, "count": count, "filters": filters})

	recent = []
	if frappe.has_permission("Leave Application", "read"):
		recent = frappe.get_list(
			"Leave Application",
			filters={"company": ["in", companies], "docstatus": ["<", 2]},
			fields=["name", "employee_name", "leave_type", "from_date", "to_date", "total_leave_days", "status"],
			order_by="modified desc",
			limit=5,
		)
		for r in recent:
			r["bs_from"] = _bs_short(r.from_date)
			r["bs_to"] = _bs_short(r.to_date)
	return {"queues": out, "recent_leave": recent}


# (label, SQL condition on tabEmployee e, what happens while it stays blank)
# The list mirrors docs/payroll-handover.md §8 — keep the two in step.
SETUP_GAPS = [
	("attendance_device_id", _("Attendance Device ID"), "ifnull(e.attendance_device_id,'')=''",
		_("No punch reaches this person")),
	("default_shift", _("Default Shift"), "ifnull(e.default_shift,'')=''",
		_("Lateness cannot be measured")),
	("custom_employee_category", _("Employee Category"), "ifnull(e.custom_employee_category,'')=''",
		_("Never paid overtime")),
	("payroll_cost_center", _("Payroll Cost Center"), "ifnull(e.payroll_cost_center,'')=''",
		_("Journal cannot split by cost centre")),
	# 71 on avinas1 (2026-09-24): an import copied the birth date into both fields.
	("date_of_joining", _("Joining date = birth date"), "e.date_of_joining = e.date_of_birth",
		_("Service years and bonus come out wrong")),
]


def _setup_gaps(companies):
	active = frappe.db.count("Employee", {"status": "Active", "company": ["in", companies]})
	gaps = []
	for field, label, condition, consequence in SETUP_GAPS:
		count = frappe.db.sql(
			f"select count(*) from tabEmployee e where e.status='Active' and e.company in %(c)s and {condition}",
			{"c": companies},
		)[0][0]
		if count:
			gaps.append({"field": field, "label": label, "count": count, "consequence": consequence})

	no_assignment = frappe.db.sql(
		"""select count(*) from tabEmployee e where e.status='Active' and e.company in %(c)s
		and not exists (select 1 from `tabSalary Structure Assignment` a
			where a.employee=e.name and a.docstatus=1 and a.from_date<=%(d)s)""",
		{"c": companies, "d": today()},
	)[0][0]
	if no_assignment:
		gaps.append(
			{
				"field": "salary_structure_assignment",
				"label": _("Salary Structure Assignment"),
				"count": no_assignment,
				"consequence": _("Left out of every payroll run"),
			}
		)
	return {"active": active, "items": gaps}


def _upcoming(companies):
	"""Birthdays, work anniversaries and festival holidays in the next UPCOMING_DAYS."""
	start = getdate(today())
	horizon = start + datetime.timedelta(days=UPCOMING_DAYS)
	people = frappe.get_all(
		"Employee",
		filters={"status": "Active", "company": ["in", companies]},
		fields=["name", "employee_name", "date_of_birth", "date_of_joining", "image"],
	)
	events = []
	for p in people:
		for field, kind in (("date_of_birth", "birthday"), ("date_of_joining", "anniversary")):
			when = _next_occurrence(p.get(field), start)
			if not when or when > horizon:
				continue
			years = when.year - p.get(field).year
			# Imported records sometimes carry the birth date as the joining
			# date; that is not a 31-year anniversary, so leave it out.
			if kind == "anniversary" and (years < 1 or p.date_of_joining == p.date_of_birth):
				continue
			events.append(
				{
					"kind": kind,
					"employee": p.name,
					"employee_name": p.employee_name,
					"date": str(when),
					"bs": _bs_short(when),
					"in_days": (when - start).days,
					"years": years,
				}
			)
	events.sort(key=lambda e: (e["in_days"], e["employee_name"]))

	holiday_lists = [
		h for h in frappe.get_all("Company", filters={"name": ["in", companies]}, pluck="default_holiday_list") if h
	]
	holidays = []
	if holiday_lists:
		holidays = frappe.db.sql(
			"""select holiday_date d, description from tabHoliday
			where parent in %(h)s and weekly_off=0 and holiday_date between %(s)s and %(e)s
			group by holiday_date, description order by holiday_date""",
			{"h": holiday_lists, "s": start, "e": horizon},
			as_dict=True,
		)
	return {
		"people": events[:8],
		"people_total": len(events),
		"holidays": [
			{"date": str(h.d), "bs": _bs_short(h.d), "name": frappe.utils.strip_html(h.description or ""),
				"in_days": (h.d - start).days}
			for h in holidays
		],
	}


def _next_occurrence(date, start):
	if not date:
		return None
	for year in (start.year, start.year + 1):
		try:
			when = date.replace(year=year)
		except ValueError:  # 29 Feb in a non-leap year
			when = datetime.date(year, 3, 1)
		if when >= start:
			return when
	return None


def _devices(companies):
	if not frappe.has_permission("Biometric Device", "read"):
		return []
	return frappe.get_list(
		"Biometric Device",
		filters={"company": ["in", companies]},
		fields=["name", "device_name", "enabled", "connection_status", "last_contact_time", "alert_threshold_minutes"],
		order_by="device_name",
	)


def _bs_short(date):
	if not date:
		return ""
	bs = ad_to_bs(getdate(date))
	return f"{bs.day} {get_bs_month_name(bs.month)}"


# ---------------------------------------------------------------------------
# Menu
# ---------------------------------------------------------------------------

# Grouped the way HR works through a month, not the way HRMS files its
# doctypes. (label, icon, [(type, name, label)]) — type is doctype, report,
# new (open a blank form) or page.
MENU = [
	("Employees", "people", [
		("doctype", "Employee", "Employees"),
		("new", "Employee", "New Employee"),
		("doctype", "Employee Category", "Employee Categories"),
		("doctype", "Allowance Category", "Allowance Categories"),
		("doctype", "Department", "Departments"),
		("doctype", "Designation", "Designations"),
		("doctype", "Employee Promotion", "Promotions"),
		("doctype", "Employee Transfer", "Transfers"),
		("doctype", "Employee Separation", "Separations"),
	]),
	("Attendance", "clock", [
		("report", "Monthly Attendance BS", "Monthly Attendance (BS)"),
		("doctype", "Attendance", "Attendance"),
		("doctype", "Employee Checkin", "Punches (Checkins)"),
		("doctype", "Attendance Request", "Attendance Requests"),
		("doctype", "Attendance Fix", "Attendance Fix"),
		("report", "Work On Holiday BS", "Work on Holiday (BS)"),
		("doctype", "Biometric Device", "Biometric Devices"),
	]),
	("Shifts & Overtime", "shift", [
		("doctype", "Shift Type", "Shift Types"),
		("doctype", "Shift Assignment", "Shift Assignments"),
		("doctype", "Shift Request", "Shift Requests"),
		("doctype", "Overtime Sheet", "Overtime Sheets"),
	]),
	("Leave", "calendar", [
		("new", "Leave Application", "Apply Leave"),
		("doctype", "Leave Application", "Leave Applications"),
		("report", "Yearly Leave Details BS", "Yearly Leave (BS)"),
		("doctype", "Leave Allocation", "Leave Allocations"),
		("doctype", "Leave Policy Assignment", "Policy Assignments"),
		("doctype", "Compensatory Leave Request", "Compensatory Leave"),
		("doctype", "Leave Encashment", "Leave Encashment"),
		("doctype", "Holiday List", "Holiday Lists"),
		("doctype", "Holiday Bulk Update", "Holiday Bulk Update"),
	]),
	("Payroll", "wallet", [
		("new", "Payroll Entry", "Run Payroll"),
		("doctype", "Payroll Entry", "Payroll Entries"),
		("doctype", "Salary Slip", "Salary Slips"),
		("report", "Avinas Salary Statement", "Salary Statement"),
		("doctype", "Payroll Adjustment", "Payroll Adjustments"),
		("doctype", "Additional Salary", "Additional Salary"),
		("doctype", "Employee Advance", "Employee Advances"),
		("doctype", "Dashain Bonus", "Dashain Bonus"),
		("doctype", "Salary Revision", "Salary Revisions"),
		("doctype", "Salary Structure Assignment", "Structure Assignments"),
	]),
	("Setup", "gear", [
		("doctype", "Salary Structure", "Salary Structures"),
		("doctype", "Salary Component", "Salary Components"),
		("doctype", "Income Tax Slab", "Income Tax Slabs"),
		("doctype", "Payroll Period", "Payroll Periods"),
		("doctype", "Leave Type", "Leave Types"),
		("doctype", "Leave Policy", "Leave Policies"),
		("doctype", "Leave Period", "Leave Periods"),
		("doctype", "HR Settings", "HR Settings"),
		("doctype", "Payroll Settings", "Payroll Settings"),
	]),
]


@frappe.whitelist()
def get_menu():
	"""The left-hand menu, minus anything the user cannot open or that is not installed."""
	frappe.only_for(DASHBOARD_ROLES)
	groups = []
	for label, icon, items in MENU:
		visible = []
		for kind, name, item_label in items:
			if kind == "report":
				if not frappe.db.exists("Report", name):
					continue
				report = frappe.get_cached_doc("Report", name)
				if report.disabled or not report.is_permitted():
					continue
			else:
				if not frappe.db.exists("DocType", name):
					continue
				if not frappe.has_permission(name, "create" if kind == "new" else "read"):
					continue
			visible.append({"type": kind, "name": name, "label": _(item_label)})
		if visible:
			groups.append({"label": _(label), "icon": icon, "items": visible})
	return groups
