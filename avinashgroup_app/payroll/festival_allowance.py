"""Dashain (festival) allowance: one button on the Payroll Entry, a draft to review.

Before this, the festival allowance had no way into payroll except a person's
amount worked out on paper and typed onto a Payroll Adjustment (an earlier
"Dashain Bonus" screen was removed on 2026-09-29, by user decision, because it
was a document of its own). This keeps that decision: nothing new to file. The
Payroll Entry of the month it is paid in gets a "Dashain Allowance" button, and
the button writes a DRAFT Payroll Adjustment — the screen HR already uses for
one-off amounts — with one row per person showing the arithmetic. HR reads it,
corrects a line if needed, and submits; submitting writes the Additional Salary
the slip reads (Payroll Adjustment.on_submit), taxed in its own month.

The rule (user, 2026-10-13): one month's BASIC salary — the Salary Structure
Assignment's `base` on the cut-off date, which is what the structures' Basic
row pays (formula `base`); no allowance, overtime or grade added, nothing
deducted — times a factor for service:

    service days = cut-off − joining date        (days elapsed; joining day 0)
    year days    = cut-off − (cut-off one year earlier)   (365, or 366)
    factor       = 1 if joined on or before the cut-off one year earlier,
                   else service days ÷ year days; clamped to 0..1
    amount       = basic × factor   (never more than one month's basic)

So someone who joined exactly one year before the cut-off gets 100 %, someone
who joined on the cut-off or later gets nothing and is not listed. HR picks the
cut-off on the button's dialog (Ghatasthapana, or the payment date); it
defaults to the payroll month's last day.

Every other rule is data on the festival Salary Component
(`custom_is_festival_allowance` and the `custom_festival_*` fields, patch
setup_festival_allowance): minimum service, proration on/off, daily-wage staff
in or out, people leaving before the cut-off in or out, and the pay month. A
second festival (Tihar) would be a second component with the tick.

Re-running is safe. A draft made earlier for this entry is rebuilt in place.
Anyone already paid the component in this payroll period (a submitted
Additional Salary, from an earlier run or typed by hand) is left out and named.
A second draft for the same company, component and year from a different entry
is refused, so two drafts can never both be submitted. Payroll Adjustment
refuses a computed row above its basic (the 100 % cap holds after hand edits).

Boundary: it pays the people on this Payroll Entry. Someone who left in an
earlier month is not on it and has no slip this month; settle them in their
Full and Final.
"""

import frappe
from frappe import _
from frappe.utils import add_years, cint, date_diff, flt, getdate

from avinashgroup_app.payroll.allowance import current_assignment

#: Payroll Adjustment.source for a run of this button; "<SOURCE>: <component>".
SOURCE = "Festival Allowance"


def festival_components() -> list:
	"""Enabled Salary Components ticked as a festival allowance, with their rules."""
	return frappe.get_all(
		"Salary Component",
		filters={"custom_is_festival_allowance": 1, "disabled": 0},
		fields=[
			"name",
			"custom_festival_min_service_days",
			"custom_festival_prorate",
			"custom_festival_include_daily_wage",
			"custom_festival_include_leavers",
			"custom_festival_pay_month",
		],
		order_by="name",
	)


def service_factor(date_of_joining, cutoff) -> tuple:
	"""(service days, year days, factor) at the cut-off.

	Service days are the days elapsed from joining to the cut-off (the joining
	day itself is day 0). Year days are the length of the year ending on the
	cut-off — 365, or 366 across a 29 February. A full year (joined on or before
	the same date a year earlier) is factor 1; the factor never exceeds 1.
	"""
	cutoff = getdate(cutoff)
	year_ago = getdate(add_years(cutoff, -1))
	year_days = date_diff(cutoff, year_ago)
	if not date_of_joining:
		return year_days, year_days, 1.0
	joined = getdate(date_of_joining)
	service = max(0, date_diff(cutoff, joined))
	if joined <= year_ago:
		return service, year_days, 1.0
	return service, year_days, min(1.0, max(0.0, service / year_days))


def festival_amount(basic: float, factor: float, prorate: int = 1) -> float:
	"""basic × factor, never above the basic. With proration off, any service pays the full basic."""
	factor = min(1.0, max(0.0, flt(factor)))
	if not cint(prorate) and factor > 0:
		factor = 1.0
	return flt(min(flt(basic), flt(basic) * factor), 2)


def monthly_basic(employee: str, on_date) -> tuple:
	"""(one month's basic, is_daily_wage) on `on_date`, from the salary assignment.

	The assignment's `base` is what the Basic row pays. A Daily Wage structure's
	base is one day's pay, so its month is that × the BS month's days.
	"""
	assignment = current_assignment(employee, on_date)
	if not assignment:
		return 0.0, False
	basic = flt(assignment.get("base"))
	daily = cint(frappe.db.get_value("Salary Structure", assignment.get("salary_structure"), "custom_daily_wage"))
	if daily:
		from rdp_common_app.utils.bs_boundaries import ad_to_bs, get_bs_month_days

		bs = ad_to_bs(getdate(on_date))
		basic *= get_bs_month_days(bs.year, bs.month)
	return flt(basic, 2), bool(daily)


def compute_rows(company: str, employees: list, component, cutoff, payroll_period=None) -> dict:
	"""Work out each person's festival allowance at the cut-off.

	Returns {"rows": [...], "left_out": [{employee, employee_name, reason}]}.
	Pure computation: writes nothing. `employees` is a list of Employee names.
	"""
	cutoff = getdate(cutoff)
	rows, left_out = [], []
	min_days = cint(component.custom_festival_min_service_days)
	already = paid_already(employees, component.name, payroll_period) if employees else set()

	for emp in frappe.get_all(
		"Employee",
		filters={"name": ("in", employees or [""])},
		fields=["name", "employee_name", "date_of_joining", "relieving_date", "company"],
		order_by="employee_name",
	):

		def skip(reason):
			left_out.append({"employee": emp.name, "employee_name": emp.employee_name, "reason": reason})

		if emp.company != company:
			skip(_("belongs to {0}").format(emp.company))
			continue
		if emp.name in already:
			skip(_("already paid {0} this year").format(component.name))
			continue
		if emp.date_of_joining and getdate(emp.date_of_joining) >= cutoff:
			skip(_("joined on or after the cut-off"))
			continue
		if emp.relieving_date and getdate(emp.relieving_date) < cutoff and not cint(
			component.custom_festival_include_leavers
		):
			skip(_("left on {0}, before the cut-off").format(emp.relieving_date))
			continue

		# A leaver who is included is counted to the relieving date.
		counted_to = min(cutoff, getdate(emp.relieving_date)) if emp.relieving_date else cutoff
		service, year_days, factor = service_factor(emp.date_of_joining, counted_to)
		if min_days and service < min_days:
			skip(_("under {0} days of service").format(min_days))
			continue

		basic, daily = monthly_basic(emp.name, cutoff)
		if daily and not cint(component.custom_festival_include_daily_wage):
			skip(_("daily-wage staff are not included"))
			continue
		if not basic:
			skip(_("no salary structure assignment on {0}").format(cutoff))
			continue

		amount = festival_amount(basic, factor, component.custom_festival_prorate)
		if amount <= 0:
			skip(_("nothing due"))
			continue
		rows.append(
			{
				"employee": emp.name,
				"employee_name": emp.employee_name,
				"salary_component": component.name,
				"date_of_joining": emp.date_of_joining,
				"base_amount": basic,
				"service_days": service,
				"year_days": year_days,
				"prorate_factor": round(factor, 6),
				"amount": amount,
				"note": _("Full year") if factor >= 1 or not cint(component.custom_festival_prorate)
				else _("{0} of {1} days").format(service, year_days),
			}
		)
	return {"rows": rows, "left_out": left_out}


def paid_already(employees: list, component: str, payroll_period) -> set:
	"""Employees with a submitted Additional Salary for the component in the payroll period."""
	if not payroll_period:
		return set()
	return set(
		frappe.get_all(
			"Additional Salary",
			filters={
				"employee": ("in", employees),
				"salary_component": component,
				"docstatus": 1,
				"payroll_date": ("between", [payroll_period.start_date, payroll_period.end_date]),
			},
			pluck="employee",
		)
	)


def _payroll_period(company, on_date):
	return frappe.db.get_value(
		"Payroll Period",
		{"company": company, "start_date": ("<=", on_date), "end_date": (">=", on_date)},
		["name", "start_date", "end_date"],
		as_dict=True,
	)


@frappe.whitelist()
def get_defaults(payroll_entry: str) -> dict:
	"""What the dialog opens with: the festival components and the default cut-off."""
	pe = frappe.get_doc("Payroll Entry", payroll_entry)
	pe.check_permission("read")
	return {
		"components": [{"name": c.name, "pay_month": c.custom_festival_pay_month} for c in festival_components()],
		"cutoff": pe.end_date,
		"bs_month": pe.get("custom_bs_month"),
	}


@frappe.whitelist()
def make_festival_adjustment(payroll_entry: str, component: str, cutoff=None) -> dict:
	"""Build (or rebuild) the draft Payroll Adjustment for this entry's festival allowance.

	Explicit action, pressed by HR; writes only a draft. Throws for a cancelled
	entry, a component that is not a festival allowance, a payroll month that is
	not the component's pay month, or another draft for the same year.
	"""
	pe = frappe.get_doc("Payroll Entry", payroll_entry)
	pe.check_permission("read")
	frappe.has_permission("Payroll Adjustment", "create", throw=True)
	if pe.docstatus == 2:
		frappe.throw(_("This Payroll Entry is cancelled."))

	rules = next((c for c in festival_components() if c.name == component), None)
	if not rules:
		frappe.throw(
			_("{0} is not a festival allowance (tick Festival Allowance on the Salary Component)").format(component)
		)
	if rules.custom_festival_pay_month and pe.get("custom_bs_month") and rules.custom_festival_pay_month != pe.custom_bs_month:
		frappe.throw(
			_("{0} is paid in {1} (Salary Component → Festival Allowance → Pay Month); this entry is for {2}.").format(
				component, rules.custom_festival_pay_month, pe.custom_bs_month
			)
		)

	cutoff = getdate(cutoff or pe.end_date)
	period = _payroll_period(pe.company, pe.end_date)
	source = f"{SOURCE}: {component}"
	drafts = frappe.get_all(
		"Payroll Adjustment",
		filters={"company": pe.company, "source": source, "docstatus": 0},
		fields=["name", "payroll_entry", "payroll_date"],
	)
	mine = [d for d in drafts if d.payroll_entry == pe.name]
	others = [
		d
		for d in drafts
		if d.payroll_entry != pe.name
		and (not period or period.start_date <= getdate(d.payroll_date) <= period.end_date)
	]
	if others:
		frappe.throw(
			_("Draft {0} already holds {1} for this year. Delete it, or submit it, before making another.").format(
				", ".join(d.name for d in others), component
			)
		)

	employees = [r.employee for r in pe.employees]
	if not employees:
		frappe.throw(_("The Payroll Entry has no employees yet: press Get Employees first."))

	result = compute_rows(pe.company, employees, rules, cutoff, period)

	doc = frappe.get_doc("Payroll Adjustment", mine[0].name) if mine else frappe.new_doc("Payroll Adjustment")
	doc.update(
		{
			"company": pe.company,
			"payroll_date": pe.end_date,
			"payroll_entry": pe.name,
			"source": source,
			"cutoff_date": cutoff,
			"reason": _("{0} {1}, service counted to {2}").format(component, pe.get("custom_fiscal_year") or "", cutoff),
		}
	)
	doc.set("adjustments", [])
	for row in result["rows"]:
		doc.append("adjustments", row)
	doc.flags.ignore_permissions = True
	if doc.adjustments:
		doc.save()
	else:
		if not doc.is_new():
			# Nothing is due any more: an old draft must not stay to be submitted.
			frappe.delete_doc("Payroll Adjustment", doc.name, ignore_permissions=True)
		doc = None

	return {
		"payroll_adjustment": doc.name if doc else None,
		"count": len(result["rows"]),
		"total": flt(sum(r["amount"] for r in result["rows"]), 2),
		"left_out": result["left_out"],
	}
