"""The Shift Roster page: who is on which rotational shift, month by month.

One row per employee, one column per BS month of a fiscal year. Each cell holds
the shift(s) that person works in that month, with the day spans, so a month
with a mid-month change can be drawn split. Read-only: every change goes
through `hr.shift_rotation`, which owns the rules (rotational shifts only, one
company, paid months locked, lived days re-marked).

Per-day resolution is `hr.shift_day.ShiftRoster` — the same answer attendance,
late time and overtime use — so the roster can never disagree with them.
"""

from datetime import timedelta

import frappe
from frappe import _
from frappe.utils import getdate, today
from rdp_common_app.utils.bs_boundaries import ad_to_bs, get_bs_month_name, get_bs_month_range

from avinashgroup_app.hr.shift_day import ShiftRoster
from avinashgroup_app.hr.shift_rotation import rotational_shifts

#: Chip colours by position among the company's rotational shifts (earliest
#: start first), so 6-2 and 12-8 never share one. Shift Type.color is "Blue" for
#: both on this site, so it can't be used.
PALETTE = ("#2f80ed", "#f2994a", "#27ae60", "#9b51e0")


@frappe.whitelist()
def roster(company, fiscal_year=None):
	"""Months, rotational shifts and per-employee month cells for one company and year."""
	frappe.has_permission("Shift Assignment", "read", throw=True)
	if not company:
		frappe.throw(_("Choose a company."))

	fy = _fiscal_year(fiscal_year)
	months = _bs_months(fy.year_start_date, fy.year_end_date)
	shift_names = rotational_shifts(company)
	shifts = []
	for i, name in enumerate(shift_names):
		start, end = frappe.db.get_value("Shift Type", name, ["start_time", "end_time"])
		shifts.append(
			{"name": name, "label": _short_label(start, end), "color": PALETTE[i % len(PALETTE)]}
		)

	employees = frappe.get_all(
		"Employee",
		filters={"company": company, "status": "Active"},
		fields=["name", "employee_name", "department"],
		order_by="employee_name",
	)
	start, end = months[0]["start"], months[-1]["end"]
	day_roster = ShiftRoster(employees, start, end)
	rotational = set(shift_names)

	rows = []
	for emp in employees:
		cells, touches_rotation = [], False
		for month in months:
			spans = _spans(day_roster, emp.name, month["start"], month["end"])
			touches_rotation |= any(s["shift"] in rotational for s in spans)
			cells.append(spans)
		if touches_rotation:
			rows.append(
				{
					"employee": emp.name,
					"employee_name": emp.employee_name,
					"department": emp.department,
					"cells": cells,
				}
			)

	return {
		"fiscal_year": fy.name,
		"today": str(getdate(today())),
		"months": [{**m, "start": str(m["start"]), "end": str(m["end"])} for m in months],
		"shifts": shifts,
		"rows": rows,
	}


def _fiscal_year(name):
	if name:
		return frappe.get_cached_doc("Fiscal Year", name)
	name = frappe.db.get_value(
		"Fiscal Year",
		{"year_start_date": ("<=", today()), "year_end_date": (">=", today())},
		"name",
	)
	if not name:
		frappe.throw(_("No Fiscal Year covers today. Choose one."))
	return frappe.get_cached_doc("Fiscal Year", name)


def _bs_months(ad_start, ad_end):
	"""The BS months that start inside [ad_start, ad_end], in order."""
	months, day = [], getdate(ad_start)
	end = getdate(ad_end)
	while day <= end:
		bs = ad_to_bs(day)
		m_start, m_end = get_bs_month_range(bs.year, bs.month)
		months.append(
			{
				"key": f"{bs.year}-{bs.month:02d}",
				"label": get_bs_month_name(bs.month),
				"bs_year": bs.year,
				"start": getdate(m_start),
				"end": getdate(m_end),
			}
		)
		day = getdate(m_end) + timedelta(days=1)
	return months


def _spans(day_roster, employee, start, end):
	"""[{shift, from, to}] for one month: runs of consecutive days on one shift."""
	spans, day = [], start
	while day <= end:
		shift = day_roster.shift_on(employee, day)
		if spans and spans[-1]["shift"] == shift:
			spans[-1]["to"] = str(day)
		else:
			spans.append({"shift": shift, "from": str(day), "to": str(day)})
		day += timedelta(days=1)
	return spans


def _short_label(start, end):
	"""'6–2' for 06:00–14:00, '12–8' for 12:00–20:00: what the staff call them."""

	def hour(t):
		h = int(str(t).split(":")[0]) % 12
		return str(h or 12)

	return f"{hour(start)}–{hour(end)}"
