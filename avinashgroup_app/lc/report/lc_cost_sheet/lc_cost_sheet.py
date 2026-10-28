"""LC Cost Sheet — what each import under an LC really cost in company currency.

Per shipment: the bank's debit for the goods (at its rate), the exchange
difference against the invoice rate, and the shipment's share of the LC's bank
charges (by amount); then the Landed Cost Vouchers linked to the LC (customs
duty, freight, clearing and the capitalised charges) for the whole LC. The
landed rate per unit of LC currency is the figure to compare across suppliers.
"""

import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if not filters.letter_of_credit:
		return columns(), []
	lc = frappe.get_doc("Letter of Credit", filters.letter_of_credit)
	lc.check_permission("read")
	shipped = sum(flt(s.amount) for s in lc.shipments) or 1
	lcv_total = flt(frappe.db.sql(
		"select sum(total_taxes_and_charges) from `tabLanded Cost Voucher` where docstatus = 1 and letter_of_credit = %s",
		lc.name)[0][0])
	clearing = frappe.db.sql(
		"""select sum(t.base_amount) from `tabLanded Cost Taxes and Charges` t
		join `tabLanded Cost Voucher` v on v.name = t.parent
		join `tabLC Company Account` a on a.charges_account = t.expense_account
		where v.docstatus = 1 and v.letter_of_credit = %s""", lc.name)[0][0]
	# LCV totals include the LC charges they capitalise; count those once.
	other_landed = lcv_total - flt(clearing)

	rows = []
	for s in lc.shipments:
		share = flt(s.amount) / shipped
		r = frappe._dict(
			shipment_no=s.shipment_no, transport_doc_no=s.transport_doc_no, status=s.status,
			amount=s.amount, exchange_rate=s.exchange_rate, goods=flt(s.amount_npr),
			exchange_difference=flt(s.exchange_difference),
			charges=flt(lc.charges_total) * share, other_landed=other_landed * share,
		)
		r.total = r.goods + r.charges + r.other_landed
		r.landed_rate = r.total / flt(s.amount) if flt(s.amount) and r.goods else None
		rows.append(r)
	return columns(), rows


def columns():
	cur = lambda f, l, w=130: {"fieldname": f, "label": l, "fieldtype": "Currency", "width": w}
	return [
		{"fieldname": "shipment_no", "label": _("Shipment"), "fieldtype": "Int", "width": 80},
		{"fieldname": "transport_doc_no", "label": _("B/L No."), "fieldtype": "Data", "width": 120},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 100},
		{"fieldname": "amount", "label": _("Amount (LC Cur.)"), "fieldtype": "Float", "precision": 2, "width": 120},
		{"fieldname": "exchange_rate", "label": _("Bank Rate"), "fieldtype": "Float", "precision": 4, "width": 90},
		cur("goods", _("Goods (Bank Debit)")),
		cur("exchange_difference", _("of which Exch. Loss/(Gain)")),
		cur("charges", _("LC Bank Charges")),
		cur("other_landed", _("Duty, Freight, Clearing")),
		cur("total", _("Landed Cost")),
		{"fieldname": "landed_rate", "label": _("Landed per Unit"), "fieldtype": "Float", "precision": 4, "width": 110},
	]
