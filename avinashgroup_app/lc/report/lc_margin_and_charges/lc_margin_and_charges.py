"""LC Margin and Charges — money the banks hold or took, per company and bank.

Margin deposited, used in settlements, released and still held; bank charges
booked, how much of them a Landed Cost Voucher has already moved into stock,
and what is still waiting in LC Charges Clearing.
"""

import frappe
from frappe import _
from frappe.utils import flt

from avinashgroup_app.lc.accounting import capitalised_charges


def execute(filters=None):
	filters = frappe._dict(filters or {})
	conditions = {"docstatus": 1}
	if filters.company:
		conditions["company"] = filters.company
	lcs = frappe.get_all("Letter of Credit", filters=conditions,
		fields=["name", "company", "bank", "margin_deposited", "margin_applied", "margin_released",
			"margin_balance", "charges_total"])
	groups = {}
	for lc in lcs:
		key = (lc.company, lc.bank)
		g = groups.setdefault(key, frappe._dict(company=lc.company, bank=lc.bank, lcs=0,
			margin_deposited=0, margin_applied=0, margin_released=0, margin_balance=0,
			charges_total=0, capitalised=0))
		g.lcs += 1
		for f in ("margin_deposited", "margin_applied", "margin_released", "margin_balance", "charges_total"):
			g[f] += flt(lc[f])
		if flt(lc.charges_total):
			g.capitalised += capitalised_charges(lc)
	rows = list(groups.values())
	for g in rows:
		g.pending = g.charges_total - g.capitalised
	return columns(), sorted(rows, key=lambda r: (r.company, r.bank or ""))


def columns():
	cur = lambda f, l, w=130: {"fieldname": f, "label": l, "fieldtype": "Currency", "width": w}
	return [
		{"fieldname": "company", "label": _("Company"), "fieldtype": "Link", "options": "Company", "width": 220},
		{"fieldname": "bank", "label": _("Bank"), "fieldtype": "Link", "options": "Bank", "width": 160},
		{"fieldname": "lcs", "label": _("LCs"), "fieldtype": "Int", "width": 60},
		cur("margin_deposited", _("Margin Deposited")),
		cur("margin_applied", _("Margin Used")),
		cur("margin_released", _("Margin Released")),
		cur("margin_balance", _("Margin Held")),
		cur("charges_total", _("Bank Charges")),
		cur("capitalised", _("In Stock (LCV)")),
		cur("pending", _("Not Yet Capitalised")),
	]
