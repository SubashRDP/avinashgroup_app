"""LC Register — every Letter of Credit with where it stands: goods paid, landed
cost so far, margin held, and the dates that matter (expiry, maturity, depart, reach)."""

import frappe
from frappe import _


def execute(filters=None):
	filters = frappe._dict(filters or {})
	conditions = {"docstatus": 1}
	for field in ("company", "supplier", "bank", "status"):
		if filters.get(field):
			conditions[field] = filters[field]
	if filters.from_date and filters.to_date:
		conditions["posting_date"] = ["between", [filters.from_date, filters.to_date]]
	if not filters.status and not filters.show_closed:
		conditions["status"] = ["not in", ["Closed", "Cancelled"]]

	rows = frappe.get_all(
		"Letter of Credit", filters=conditions, order_by="posting_date desc",
		fields=["name", "company", "supplier", "supplier_name", "bank", "lc_no", "posting_date", "drafts_at",
			"usance_days", "currency", "lc_amount", "goods_booked_fc", "goods_pending_fc", "expiry_date",
			"maturity_date", "departure_date", "arrival_date", "incoterm", "total_cost", "vat_total",
			"margin_balance", "status"],
	)
	for r in rows:
		r.terms = _("Sight") if r.drafts_at == "Sight" else _("Usance {0} days").format(r.usance_days)
	return columns(), rows


def columns():
	return [
		{"fieldname": "name", "label": _("LC"), "fieldtype": "Link", "options": "Letter of Credit", "width": 160},
		{"fieldname": "lc_no", "label": _("LC No."), "fieldtype": "Data", "width": 130},
		{"fieldname": "supplier_name", "label": _("Supplier"), "fieldtype": "Data", "width": 170},
		{"fieldname": "bank", "label": _("Bank"), "fieldtype": "Link", "options": "Bank", "width": 140},
		{"fieldname": "posting_date", "label": _("Opened"), "fieldtype": "Date", "width": 95},
		{"fieldname": "terms", "label": _("Terms"), "fieldtype": "Data", "width": 110},
		{"fieldname": "incoterm", "label": _("Incoterm"), "fieldtype": "Data", "width": 80},
		{"fieldname": "currency", "label": _("Cur."), "fieldtype": "Link", "options": "Currency", "width": 60},
		{"fieldname": "lc_amount", "label": _("LC Amount"), "fieldtype": "Float", "precision": 2, "width": 120},
		{"fieldname": "goods_booked_fc", "label": _("Paid / Accepted"), "fieldtype": "Float", "precision": 2, "width": 120},
		{"fieldname": "goods_pending_fc", "label": _("Still to Pay"), "fieldtype": "Float", "precision": 2, "width": 110},
		{"fieldname": "expiry_date", "label": _("Expiry"), "fieldtype": "Date", "width": 95},
		{"fieldname": "maturity_date", "label": _("Maturity"), "fieldtype": "Date", "width": 95},
		{"fieldname": "departure_date", "label": _("Departed"), "fieldtype": "Date", "width": 95},
		{"fieldname": "arrival_date", "label": _("Reached"), "fieldtype": "Date", "width": 95},
		{"fieldname": "total_cost", "label": _("Landed Cost"), "fieldtype": "Currency", "width": 130},
		{"fieldname": "vat_total", "label": _("VAT Paid"), "fieldtype": "Currency", "width": 110},
		{"fieldname": "margin_balance", "label": _("Margin Held"), "fieldtype": "Currency", "width": 120},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 100},
	]
