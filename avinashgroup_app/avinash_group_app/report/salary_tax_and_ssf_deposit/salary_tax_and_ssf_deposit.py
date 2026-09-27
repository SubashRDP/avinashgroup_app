"""Salary Tax and SSF Deposit: what one BS month's payroll owes the government.

Every month accounts deposits three amounts withheld from salary, each on its own
voucher and deadline:

  SSF contribution    31% of basic (20% employer + 11% employee), to the Social
                      Security Fund by the 15th of the next BS month
  SST                 the 1% social security tax band, paid only by staff outside
                      SSF, to IRD by the 25th
  Remuneration tax    the rest of the income tax, to IRD by the 25th

Until now the only way to get those figures was to add up the salary sheet by
hand; the HR dashboard shows one combined TDS total, which is not what either
voucher asks for. This report gives one row per employee and the three totals.

How the tax is split: the slip holds a single Income Tax row (payroll/
income_tax.py puts SST on the slab as its first band, waived for SSF members).
Each month's deduction is the year's tax spread over the remaining months, so
the month's SST share is the deduction × (first-band tax ÷ total annual tax),
worked out from the slip's own annual taxable amount and the company's slab.
Over a year the shares add up to exactly the SST charged.

Which slips: submitted ones (or drafts, to preview) whose pay period ENDS in the
chosen BS month, so a company on a Nepal BS Period override still lands in the
month it pays.

Deliberately read-only: it deposits nothing and posts nothing. Deadlines come
from the same table the HR dashboard uses (hr/hr_dashboard.STATUTORY_DEPOSITS);
both are pending the accountant's confirmation.
"""

import frappe
from frappe import _
from frappe.utils import flt

from hrms.payroll.doctype.salary_slip.salary_slip import calculate_tax_by_tax_slab
from rdp_common_app.utils.bs_boundaries import bs_to_ad, get_bs_month_name, get_bs_month_range

from avinashgroup_app.hr.hr_dashboard import STATUTORY_DEPOSITS
from avinashgroup_app.payroll.income_tax import TAX_COMPONENT
from avinashgroup_app.payroll.year_rollover import tax_slab_for

SSF_DEDUCTION = "SSF"  # the full 31%, deducted
SSF_EMPLOYER = "SSF Addition"  # the employer's 20%, added to gross first
CIT_COMPONENT = "CIT"  # patches/setup_tax_exemptions.py


def execute(filters=None):
	filters = frappe._dict(filters or {})
	year, month = int(filters.bs_year), _month(filters.bs_month)
	start, end = get_bs_month_range(year, month)

	slips = _slips(filters.company, start, end, 0 if str(filters.docstatus).startswith("0") else 1)
	amounts = _amounts([s.name for s in slips])
	sst_share = _sst_share_calculator(filters.company, start)
	id_fields = _employee_id_fields()

	data = []
	for slip in slips:
		a = amounts.get(slip.name, {})
		# Slips store amounts at 5 decimals (currency precision 5); deposits are
		# made in paisa, so round first and split the rounded figure.
		tax = flt(a.get(TAX_COMPONENT), 2)
		ssf = flt(a.get(SSF_DEDUCTION))
		employer = flt(a.get(SSF_EMPLOYER))
		sst = sst_share(slip, tax)
		data.append(
			{
				"employee": slip.employee,
				"employee_name": slip.employee_name,
				"pan": slip.get(id_fields.get("pan")) if id_fields.get("pan") else None,
				"ssf_id": slip.get(id_fields.get("ssf")) if id_fields.get("ssf") else None,
				"salary_slip": slip.name,
				"gross_pay": flt(slip.gross_pay),
				"ssf_employer": employer,
				"ssf_employee": max(ssf - employer, 0),
				"ssf_total": ssf,
				"cit": flt(a.get(CIT_COMPONENT)),
				"sst": sst,
				"remuneration_tax": flt(tax - sst, 2),
				"income_tax": tax,
			}
		)

	return _columns(id_fields), data, _message(year, month), None, _summary(data, year, month)


def _month(value):
	"""'05 - Bhadra', '5' or 5 → 5."""
	return int(str(value).strip().split(" ")[0])


def _slips(company, start, end, docstatus):
	fields = ["name", "employee", "employee_name", "gross_pay", "annual_taxable_amount"]
	slips = frappe.get_list(
		"Salary Slip",
		filters={"company": company, "docstatus": docstatus, "end_date": ("between", [start, end])},
		fields=fields,
		order_by="employee asc",
	)
	ids = _employee_id_fields()
	wanted = [f for f in ids.values() if f] + ["custom_ssf_applicable"]
	if slips:
		employees = {
			e.name: e
			for e in frappe.get_all(
				"Employee",
				filters={"name": ("in", [s.employee for s in slips])},
				fields=["name"] + [f for f in wanted if frappe.get_meta("Employee").has_field(f)],
			)
		}
		for s in slips:
			s.update({k: v for k, v in employees.get(s.employee, {}).items() if k != "name"})
	return slips


def _amounts(slip_names):
	"""{slip: {component: amount}} for the components this report reads."""
	if not slip_names:
		return {}
	rows = frappe.db.sql(
		"""select parent, salary_component, sum(amount) amount from `tabSalary Detail`
		where parent in %(slips)s and salary_component in %(components)s
		group by parent, salary_component""",
		{"slips": slip_names, "components": (TAX_COMPONENT, SSF_DEDUCTION, SSF_EMPLOYER, CIT_COMPONENT)},
		as_dict=True,
	)
	out = {}
	for r in rows:
		out.setdefault(r.parent, {})[r.salary_component] = flt(r.amount)
	return out


def _sst_share_calculator(company, on_date):
	"""A function (slip, month's tax) → the SST part of that tax."""
	slab_name = tax_slab_for(company, on_date)
	slab = frappe.get_cached_doc("Income Tax Slab", slab_name) if slab_name else None
	first = sorted(slab.slabs, key=lambda r: flt(r.from_amount))[0] if slab and slab.slabs else None

	def share(slip, tax):
		if not tax or not first or slip.get("custom_ssf_applicable"):
			return 0.0  # SSF members are waived the 1% band; all their tax is remuneration tax
		annual = flt(slip.annual_taxable_amount)
		if annual <= 0:
			return 0.0
		band_top = flt(first.to_amount) or annual
		# Same arithmetic as HRMS's calculate_tax_by_tax_slab: a band is charged
		# on (amount - from + 1), so the ratio is exactly 1 inside the band.
		band_tax = (min(annual, band_top) - flt(first.from_amount) + 1) * flt(first.percent_deduction) / 100
		total_tax, __ = calculate_tax_by_tax_slab(
			annual, slab, {}, frappe._dict(slip, custom_ssf_applicable=0, annual_taxable_earning=annual)
		)
		if total_tax <= 0:
			return 0.0
		return flt(tax * min(band_tax / total_tax, 1), 2)

	return share


def _employee_id_fields():
	"""PAN and SSF number field names, whichever this site has."""
	meta = frappe.get_meta("Employee")
	pick = lambda *names: next((n for n in names if meta.has_field(n)), None)  # noqa: E731
	return {"pan": pick("custom_pan", "pan_number"), "ssf": pick("custom_ssf_id_no")}


def _columns(id_fields):
	cols = [
		{"fieldname": "employee", "label": _("Employee"), "fieldtype": "Link", "options": "Employee", "width": 130},
		{"fieldname": "employee_name", "label": _("Name"), "fieldtype": "Data", "width": 180},
	]
	if id_fields.get("pan"):
		cols.append({"fieldname": "pan", "label": _("PAN"), "fieldtype": "Data", "width": 110})
	if id_fields.get("ssf"):
		cols.append({"fieldname": "ssf_id", "label": _("SSF No."), "fieldtype": "Data", "width": 110})
	money = lambda f, l, w=120: {"fieldname": f, "label": l, "fieldtype": "Currency", "width": w}  # noqa: E731
	cols += [
		money("gross_pay", _("Gross Pay")),
		money("ssf_employer", _("SSF Employer 20%")),
		money("ssf_employee", _("SSF Employee 11%")),
		money("ssf_total", _("SSF Deposit 31%")),
		money("cit", _("CIT")),
		money("sst", _("SST (1%)")),
		money("remuneration_tax", _("Remuneration Tax")),
		money("income_tax", _("Total Tax Withheld")),
		{"fieldname": "salary_slip", "label": _("Salary Slip"), "fieldtype": "Link", "options": "Salary Slip", "width": 150},
	]
	return cols


def _due(year, month, component):
	"""(AD date, 'DD Month') a deposit on this month's salary is due."""
	bs_day = next(d for _l, c, d in STATUTORY_DEPOSITS if c == component)
	next_year, next_month = (year + 1, 1) if month == 12 else (year, month + 1)
	return bs_to_ad(next_year, next_month, bs_day), f"{bs_day} {get_bs_month_name(next_month)} {next_year}"


def _summary(data, year, month):
	total = lambda f: sum(flt(r[f]) for r in data)  # noqa: E731
	__, ssf_due = _due(year, month, SSF_DEDUCTION)
	__, tds_due = _due(year, month, TAX_COMPONENT)
	return [
		{"label": _("SSF to deposit · by {0}").format(ssf_due), "value": total("ssf_total"), "datatype": "Currency", "indicator": "Blue"},
		{"label": _("SST to IRD · by {0}").format(tds_due), "value": total("sst"), "datatype": "Currency", "indicator": "Orange"},
		{"label": _("Remuneration tax to IRD · by {0}").format(tds_due), "value": total("remuneration_tax"), "datatype": "Currency", "indicator": "Orange"},
		{"label": _("CIT"), "value": total("cit"), "datatype": "Currency", "indicator": "Grey"},
	]


def _message(year, month):
	return _(
		"Salary for {0} {1}. SST is the 1% band paid by staff outside SSF; it is deposited to IRD "
		"separately from remuneration tax. Deadlines await the accountant's confirmation."
	).format(get_bs_month_name(month), year)
