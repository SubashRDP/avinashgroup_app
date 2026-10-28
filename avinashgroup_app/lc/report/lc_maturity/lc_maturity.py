"""LC Maturity — usance bills accepted but not yet paid, by how soon they fall due.

What the treasury needs funded, and when: each accepted shipment with its
maturity date, days left, and its value at today's rate. Overdue rows are bills
the bank should already have debited.
"""

import frappe
from frappe import _
from frappe.utils import date_diff, flt, getdate, nowdate


def execute(filters=None):
	filters = frappe._dict(filters or {})
	as_on = getdate(filters.as_on or nowdate())
	values = {"company": filters.company}
	rows = frappe.db.sql(
		f"""select l.name, l.lc_no, l.company, l.supplier_name, l.bank, l.currency,
			s.shipment_no, s.transport_doc_no, s.amount, s.acceptance_date, s.maturity_date, s.purchase_invoice
		from `tabLC Shipment` s join `tabLetter of Credit` l on l.name = s.parent
		where l.docstatus = 1 and s.status = 'Accepted' {"and l.company = %(company)s" if filters.company else ""}
		order by s.maturity_date""",
		values, as_dict=True,
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
		r.estimated_npr = flt(r.amount) * rates[key]
	return columns(), rows


def columns():
	return [
		{"fieldname": "name", "label": _("LC"), "fieldtype": "Link", "options": "Letter of Credit", "width": 160},
		{"fieldname": "lc_no", "label": _("Bank LC No."), "fieldtype": "Data", "width": 120},
		{"fieldname": "supplier_name", "label": _("Beneficiary"), "fieldtype": "Data", "width": 170},
		{"fieldname": "bank", "label": _("Bank"), "fieldtype": "Link", "options": "Bank", "width": 130},
		{"fieldname": "shipment_no", "label": _("Shipment"), "fieldtype": "Int", "width": 80},
		{"fieldname": "transport_doc_no", "label": _("B/L No."), "fieldtype": "Data", "width": 110},
		{"fieldname": "currency", "label": _("Cur."), "fieldtype": "Data", "width": 60},
		{"fieldname": "amount", "label": _("Bill Amount"), "fieldtype": "Float", "precision": 2, "width": 120},
		{"fieldname": "acceptance_date", "label": _("Accepted"), "fieldtype": "Date", "width": 100},
		{"fieldname": "maturity_date", "label": _("Matures"), "fieldtype": "Date", "width": 100},
		{"fieldname": "days", "label": _("Days Left"), "fieldtype": "Int", "width": 80},
		{"fieldname": "bucket", "label": _("Due In"), "fieldtype": "Data", "width": 90},
		{"fieldname": "estimated_npr", "label": _("At Today's Rate"), "fieldtype": "Currency", "width": 140},
		{"fieldname": "purchase_invoice", "label": _("Purchase Invoice"), "fieldtype": "Link", "options": "Purchase Invoice", "width": 150},
	]
