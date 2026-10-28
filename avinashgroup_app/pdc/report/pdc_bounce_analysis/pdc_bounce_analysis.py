"""PDC Bounce Analysis — per party: how many cheques were presented, how many bounced.

Counts bounce *events* from each cheque's History, not current status: a cheque
that bounced, was re-deposited and then cleared still counts as one bounce, and
that is exactly the customer-credit signal this report exists for.
"""

import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
	filters = frappe._dict(filters or {})
	params = {"from_date": filters.from_date, "to_date": filters.to_date,
		"company": filters.company, "cheque_type": filters.cheque_type or "Received"}

	company_cond = "and c.company = %(company)s" if filters.company else ""
	presented = frappe.db.sql(
		f"""select c.party_type, c.party, max(c.party_name) party_name,
			count(distinct c.name) cheques, sum(c.amount) amount,
			sum(c.presentation_count) presentations
		from `tabPDC Cheque` c
		where c.docstatus = 1 and c.cheque_type = %(cheque_type)s {company_cond}
			and c.cheque_date between %(from_date)s and %(to_date)s
		group by c.party_type, c.party""",
		params, as_dict=True,
	)
	bounces = frappe.db.sql(
		f"""select c.party, count(*) bounces, sum(c.amount) bounced_amount,
			sum(c.bounce_charges) charges
		from `tabPDC Cheque Event` e
		join `tabPDC Cheque` c on c.name = e.parent and e.parenttype = 'PDC Cheque'
		where e.event = 'Bounced' and c.docstatus = 1 and c.cheque_type = %(cheque_type)s {company_cond}
			and e.event_date between %(from_date)s and %(to_date)s
		group by c.party""",
		params, as_dict=True,
	)
	reasons = frappe.db.sql(
		f"""select c.party, e.remarks reason, count(*) n
		from `tabPDC Cheque Event` e
		join `tabPDC Cheque` c on c.name = e.parent and e.parenttype = 'PDC Cheque'
		where e.event = 'Bounced' and c.docstatus = 1 and c.cheque_type = %(cheque_type)s {company_cond}
			and e.event_date between %(from_date)s and %(to_date)s
		group by c.party, e.remarks order by n desc""",
		params, as_dict=True,
	)

	by_party = {b.party: b for b in bounces}
	top_reason = {}
	for r in reasons:
		top_reason.setdefault(r.party, r.reason)

	data = []
	for p in presented:
		b = by_party.get(p.party) or frappe._dict(bounces=0, bounced_amount=0, charges=0)
		presentations = max(int(p.presentations or 0), int(p.cheques or 0))
		data.append({
			**p,
			"bounces": b.bounces,
			"bounced_amount": b.bounced_amount,
			"charges": b.charges,
			"bounce_rate": (100.0 * b.bounces / presentations) if presentations else 0,
			"top_reason": top_reason.get(p.party),
		})
	if not filters.show_all:
		data = [d for d in data if d["bounces"]]
	data.sort(key=lambda d: (-flt(d["bounce_rate"]), -flt(d["bounced_amount"])))
	return columns(), data


def columns():
	return [
		{"fieldname": "party_type", "label": _("Party Type"), "fieldtype": "Data", "hidden": 1},
		{"fieldname": "party", "label": _("Party"), "fieldtype": "Dynamic Link", "options": "party_type", "width": 130},
		{"fieldname": "party_name", "label": _("Party Name"), "fieldtype": "Data", "width": 200},
		{"fieldname": "cheques", "label": _("Cheques"), "fieldtype": "Int", "width": 80},
		{"fieldname": "amount", "label": _("Cheque Amount"), "fieldtype": "Currency", "width": 130},
		{"fieldname": "presentations", "label": _("Times Presented"), "fieldtype": "Int", "width": 90},
		{"fieldname": "bounces", "label": _("Bounces"), "fieldtype": "Int", "width": 80},
		{"fieldname": "bounce_rate", "label": _("Bounce %"), "fieldtype": "Percent", "width": 90},
		{"fieldname": "bounced_amount", "label": _("Bounced Amount"), "fieldtype": "Currency", "width": 130},
		{"fieldname": "charges", "label": _("Bounce Charges"), "fieldtype": "Currency", "width": 110},
		{"fieldname": "top_reason", "label": _("Most Common Reason"), "fieldtype": "Data", "width": 180},
	]
