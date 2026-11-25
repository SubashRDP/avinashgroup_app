"""LC Cost Sheet — what one import really cost, line by line, and per unit of each item.

Two parts on one sheet. First every cost booked on the LC, grouped the way the
accounts team reads an LC file (goods, bank charges, insurance, customs,
clearing, freight, other), with a subtotal per group and the total landed cost;
VAT paid is shown beside each line but kept out of the cost, because it is
claimed back. Then each goods row with its share of that cost and its landed
rate per unit: after the transfer the figures the Stock Entry / Asset used,
before it what the transfer would use now.
"""

import frappe
from frappe import _
from frappe.utils import flt

from avinashgroup_app.lc import transfer

GROUP_ORDER = ("Goods", "Bank Charges", "Insurance", "Customs", "Clearing", "Freight", "VAT", "Other")


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if not filters.letter_of_credit:
		return columns(), []
	lc = frappe.get_doc("Letter of Credit", filters.letter_of_credit)
	lc.check_permission("read")
	return columns(), cost_rows(lc) + [{}] + item_rows(lc)


def cost_rows(lc):
	rows = []
	total = vat = 0
	for group in GROUP_ORDER:
		lines = [c for c in lc.costs if c.cost_group == group]
		if not lines:
			continue
		g_cost = sum(flt(c.amount) for c in lines)
		g_vat = sum(flt(c.vat_amount) for c in lines)
		rows.append({"particulars": _(group), "indent": 0, "amount": g_cost, "vat": g_vat, "bold": 1})
		for c in lines:
			rows.append({
				"particulars": c.cost_type or c.description, "indent": 1, "date": c.posting_date,
				"detail": c.description if c.cost_type else (c.bill_no or ""),
				"party": c.party, "qty": c.fc_amount or None, "rate": c.exchange_rate or None,
				"amount": flt(c.amount), "vat": flt(c.vat_amount), "voucher": c.journal_entry,
			})
		total += g_cost
		vat += g_vat
	rows.append({"particulars": _("Total Landed Cost"), "indent": 0, "amount": total, "vat": vat, "bold": 1})
	if flt(lc.exchange_difference):
		rows.append({"particulars": _("Exchange Loss / (Gain) at Maturity (to profit and loss, not in cost)"),
			"indent": 0, "amount": flt(lc.exchange_difference)})
	return rows


def item_rows(lc):
	if not lc.items:
		return []
	transferred = bool(lc.transferred_on)
	if transferred:
		shares = [flt(i.allocated_cost) for i in lc.items]
	else:
		shares = transfer.allocate(lc, flt(lc.total_cost)) if flt(lc.total_cost) > 0 else [0] * len(lc.items)
	head = _("Landed Cost per Item") + (
		_(" (transferred {0})").format(frappe.format(lc.transferred_on, "Date")) if transferred else _(" (estimate, not transferred yet)"))
	rows = [{"particulars": head, "indent": 0, "bold": 1}]
	for i, share in zip(lc.items, shares):
		rows.append({
			"particulars": i.item_code or i.item_group or "", "indent": 1,
			"detail": i.description, "party": i.transfer_to, "qty": flt(i.qty),
			"rate": flt(i.rate), "fc_value": flt(i.amount), "amount": share,
			"landed_rate": flt(share / flt(i.qty), 4) if flt(i.qty) else None,
			"voucher": i.stock_entry or i.asset or "",
		})
	rows.append({"particulars": _("Total"), "indent": 0, "qty": sum(flt(i.qty) for i in lc.items),
		"fc_value": sum(flt(i.amount) for i in lc.items), "amount": sum(shares), "bold": 1})
	return rows


def columns():
	return [
		{"fieldname": "particulars", "label": _("Particulars"), "fieldtype": "Data", "width": 230},
		{"fieldname": "date", "label": _("Date"), "fieldtype": "Date", "width": 95},
		{"fieldname": "detail", "label": _("Detail"), "fieldtype": "Data", "width": 200},
		{"fieldname": "party", "label": _("Party / To"), "fieldtype": "Data", "width": 140},
		{"fieldname": "qty", "label": _("Qty / LC Cur. Amount"), "fieldtype": "Float", "precision": 2, "width": 120},
		{"fieldname": "rate", "label": _("Rate"), "fieldtype": "Float", "precision": 4, "width": 90},
		{"fieldname": "fc_value", "label": _("Value (LC Cur.)"), "fieldtype": "Float", "precision": 2, "width": 110},
		{"fieldname": "amount", "label": _("Cost"), "fieldtype": "Currency", "width": 130},
		{"fieldname": "vat", "label": _("VAT (Claimable)"), "fieldtype": "Currency", "width": 110},
		{"fieldname": "landed_rate", "label": _("Landed per Unit"), "fieldtype": "Float", "precision": 4, "width": 110},
		{"fieldname": "voucher", "label": _("Voucher"), "fieldtype": "Data", "width": 150},
	]
