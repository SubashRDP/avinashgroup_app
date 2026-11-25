"""LC Margin and Charges — money the banks hold or took, and what each LC cost, per company and bank.

Margin deposited, used in goods payments, released and still held; then the
LCs' costs by group (bank charges, insurance, customs duty, clearing, freight),
the landed cost in total, how much of it is already in stock or assets, and
what still sits in LC Goods in Transit.
"""

import frappe
from frappe import _
from frappe.utils import flt

SUM_FIELDS = ("margin_deposited", "margin_applied", "margin_released", "margin_balance", "goods_cost",
	"bank_charges", "insurance_cost", "customs_cost", "clearing_cost", "freight_cost", "other_cost",
	"total_cost", "vat_total", "transferred_cost")


def execute(filters=None):
	filters = frappe._dict(filters or {})
	conditions = {"docstatus": 1}
	if filters.company:
		conditions["company"] = filters.company
	lcs = frappe.get_all("Letter of Credit", filters=conditions, fields=["name", "company", "bank", *SUM_FIELDS])
	groups = {}
	for lc in lcs:
		g = groups.setdefault((lc.company, lc.bank),
			frappe._dict(company=lc.company, bank=lc.bank, lcs=0, **{f: 0 for f in SUM_FIELDS}))
		g.lcs += 1
		for f in SUM_FIELDS:
			g[f] += flt(lc[f])
	rows = list(groups.values())
	for g in rows:
		g.in_transit = g.total_cost - g.transferred_cost
	return columns(), sorted(rows, key=lambda r: (r.company, r.bank or ""))


def columns():
	cur = lambda f, l, w=125: {"fieldname": f, "label": l, "fieldtype": "Currency", "width": w}
	return [
		{"fieldname": "company", "label": _("Company"), "fieldtype": "Link", "options": "Company", "width": 220},
		{"fieldname": "bank", "label": _("Bank"), "fieldtype": "Link", "options": "Bank", "width": 160},
		{"fieldname": "lcs", "label": _("LCs"), "fieldtype": "Int", "width": 60},
		cur("margin_deposited", _("Margin Deposited")),
		cur("margin_applied", _("Margin Used")),
		cur("margin_released", _("Margin Released")),
		cur("margin_balance", _("Margin Held")),
		cur("goods_cost", _("Goods")),
		cur("bank_charges", _("Bank Charges")),
		cur("insurance_cost", _("Insurance")),
		cur("customs_cost", _("Customs Duty")),
		cur("clearing_cost", _("Clearing")),
		cur("freight_cost", _("Freight")),
		cur("other_cost", _("Other")),
		cur("total_cost", _("Landed Cost")),
		cur("vat_total", _("VAT Paid")),
		cur("transferred_cost", _("In Stock / Assets")),
		cur("in_transit", _("Still in Transit")),
	]
