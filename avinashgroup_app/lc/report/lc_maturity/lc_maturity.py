"""LC Maturity — usance bills accepted but not yet paid, by how soon they fall due.

What the treasury needs funded, and when: each accepted bill with its maturity
date, days left, the value it was accepted at, and its value at today's rate
(the difference is the exchange loss or gain coming). Overdue rows are bills
the bank should already have debited.
"""

import frappe
from frappe import _
from frappe.utils import date_diff, flt, getdate, nowdate


def execute(filters=None):
	filters = frappe._dict(filters or {})
	as_on = getdate(filters.as_on or nowdate())
	rows = frappe.db.sql(
		f"""select l.name, l.lc_no, l.company, l.supplier_name, l.bank, l.currency,
			c.fc_amount as amount, c.exchange_rate, c.amount as accepted_npr, c.posting_date as acceptance_date,
			c.maturity_date
		from `tabLC Cost` c join `tabLetter of Credit` l on l.name = c.parent
		where l.docstatus = 1 and c.paid_via = 'Acceptance' and c.paid_on is null
			{"and l.company = %(company)s" if filters.company else ""}
		order by c.maturity_date""",
		{"company": filters.company}, as_dict=True,
	)
	from erpnext.setup.utils import get_exchange_rate

	rates = {}
	for r in rows:
		r.days = date_diff(r.maturity_date, as_on)
		r.bucket = _("Overdue") if r.days < 0 else _("0-7 Days") if r.days <= 7 else _("8-30 Days") if r.days <= 30 else _("31+ Days")
		currency = frappe.get_cached_value("Company", r.company, "default_currency")
		key = (r.currency, currency)
		if key not in rates:
			rates[key] = flt(get_exchange_rate(r.currency, currency, as_on))
		r.estimated_npr = flt(r.amount) * rates[key] if rates[key] else None
	return columns(), rows


def columns():
	return [
		{"fieldname": "name", "label": _("LC"), "fieldtype": "Link", "options": "Letter of Credit", "width": 160},
		{"fieldname": "lc_no", "label": _("LC No."), "fieldtype": "Data", "width": 120},
		{"fieldname": "supplier_name", "label": _("Supplier"), "fieldtype": "Data", "width": 170},
		{"fieldname": "bank", "label": _("Bank"), "fieldtype": "Link", "options": "Bank", "width": 130},
		{"fieldname": "currency", "label": _("Cur."), "fieldtype": "Data", "width": 60},
		{"fieldname": "amount", "label": _("Bill Amount"), "fieldtype": "Float", "precision": 2, "width": 120},
		{"fieldname": "acceptance_date", "label": _("Accepted"), "fieldtype": "Date", "width": 100},
		{"fieldname": "exchange_rate", "label": _("Accepted Rate"), "fieldtype": "Float", "precision": 4, "width": 100},
		{"fieldname": "accepted_npr", "label": _("Accepted Value"), "fieldtype": "Currency", "width": 130},
		{"fieldname": "maturity_date", "label": _("Matures"), "fieldtype": "Date", "width": 100},
		{"fieldname": "days", "label": _("Days Left"), "fieldtype": "Int", "width": 80},
		{"fieldname": "bucket", "label": _("Due In"), "fieldtype": "Data", "width": 90},
		{"fieldname": "estimated_npr", "label": _("At Today's Rate"), "fieldtype": "Currency", "width": 140},
	]
