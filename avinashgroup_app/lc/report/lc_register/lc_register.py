"""LC Register — every Letter of Credit with its position: drawn, settled, available,
margin held and charges, plus the two dates that matter (latest shipment, expiry)."""

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
		conditions["status"] = ["not in", ["Closed", "Expired", "Cancelled"]]

	rows = frappe.get_all(
		"Letter of Credit", filters=conditions, order_by="posting_date desc",
		fields=["name", "company", "supplier", "supplier_name", "bank", "lc_no", "issue_date", "drafts_at",
			"usance_days", "currency", "lc_amount", "shipped_amount", "settled_amount", "available_amount",
			"latest_shipment_date", "expiry_date", "margin_balance", "charges_total", "settled_npr",
			"exchange_difference", "status"],
	)
	for r in rows:
		r.terms = _("Sight") if r.drafts_at == "Sight" else _("Usance {0} days").format(r.usance_days)
	return columns(), rows


def columns():
	return [
		{"fieldname": "name", "label": _("LC"), "fieldtype": "Link", "options": "Letter of Credit", "width": 160},
		{"fieldname": "lc_no", "label": _("Bank LC No."), "fieldtype": "Data", "width": 130},
		{"fieldname": "supplier_name", "label": _("Beneficiary"), "fieldtype": "Data", "width": 170},
		{"fieldname": "bank", "label": _("Bank"), "fieldtype": "Link", "options": "Bank", "width": 140},
		{"fieldname": "terms", "label": _("Terms"), "fieldtype": "Data", "width": 110},
		{"fieldname": "currency", "label": _("Cur."), "fieldtype": "Link", "options": "Currency", "width": 60},
		{"fieldname": "lc_amount", "label": _("LC Amount"), "fieldtype": "Float", "precision": 2, "width": 120},
		{"fieldname": "shipped_amount", "label": _("Shipped"), "fieldtype": "Float", "precision": 2, "width": 110},
		{"fieldname": "settled_amount", "label": _("Settled"), "fieldtype": "Float", "precision": 2, "width": 110},
		{"fieldname": "available_amount", "label": _("Available"), "fieldtype": "Float", "precision": 2, "width": 110},
		{"fieldname": "latest_shipment_date", "label": _("Ship By"), "fieldtype": "Date", "width": 100},
		{"fieldname": "expiry_date", "label": _("Expiry"), "fieldtype": "Date", "width": 100},
		{"fieldname": "margin_balance", "label": _("Margin Held"), "fieldtype": "Currency", "width": 120},
		{"fieldname": "charges_total", "label": _("Charges"), "fieldtype": "Currency", "width": 110},
		{"fieldname": "settled_npr", "label": _("Paid (NPR)"), "fieldtype": "Currency", "width": 130},
		{"fieldname": "exchange_difference", "label": _("Exch. Loss/(Gain)"), "fieldtype": "Currency", "width": 120},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 110},
	]
