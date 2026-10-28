"""PDC Maturity — open cheques bucketed by how soon they fall due.

Open = received and still In Hand / Deposited, or issued and not yet cleared.
"Overdue" is a cheque whose date has passed but is still in the drawer (received)
or not yet presented (issued): the first column to chase. Grouped per cheque or
per party.
"""

import frappe
from frappe import _
from frappe.utils import date_diff, flt, getdate, nowdate

# (column, label, days-to-due from, days-to-due to inclusive); None = open-ended.
BUCKETS = (
	("overdue", "Overdue", None, -1),
	("d0_7", "0-7 Days", 0, 7),
	("d8_30", "8-30 Days", 8, 30),
	("d31_60", "31-60 Days", 31, 60),
	("d61", "61+ Days", 61, None),
)

OPEN = {"Received": ("In Hand", "Deposited"), "Issued": ("Issued",)}


def execute(filters=None):
	filters = frappe._dict(filters or {})
	as_on = getdate(filters.as_on or nowdate())
	cheque_type = filters.cheque_type or "Received"
	group_by_party = filters.group_by == "Party"

	conditions = {"docstatus": 1, "cheque_type": cheque_type, "status": ["in", OPEN[cheque_type]]}
	if filters.company:
		conditions["company"] = filters.company
	if filters.party:
		conditions["party"] = filters.party
	cheques = frappe.get_all(
		"PDC Cheque",
		filters=conditions,
		fields=["name", "party_type", "party", "party_name", "cheque_no", "cheque_date", "amount", "status", "bank_name"],
		order_by="cheque_date asc",
	)

	rows = {}
	for c in cheques:
		days = date_diff(c.cheque_date, as_on)
		key = c.party if group_by_party else c.name
		row = rows.setdefault(key, frappe._dict(
			name=None if group_by_party else c.name,
			party_type=c.party_type, party=c.party, party_name=c.party_name,
			cheque_no=None if group_by_party else c.cheque_no,
			cheque_date=None if group_by_party else c.cheque_date,
			status=None if group_by_party else c.status,
			days_to_due=None if group_by_party else days,
			count=0, total=0, **{b[0]: 0 for b in BUCKETS},
		))
		row.count += 1
		row.total += flt(c.amount)
		for field, _label, low, high in BUCKETS:
			if (low is None or days >= low) and (high is None or days <= high):
				row[field] += flt(c.amount)
				break

	return columns(group_by_party), list(rows.values()), None, chart(rows.values())


def columns(group_by_party):
	cols = []
	if not group_by_party:
		cols += [
			{"fieldname": "name", "label": _("Cheque"), "fieldtype": "Link", "options": "PDC Cheque", "width": 170},
			{"fieldname": "cheque_no", "label": _("Cheque No"), "fieldtype": "Data", "width": 100},
			{"fieldname": "cheque_date", "label": _("Cheque Date"), "fieldtype": "Date", "width": 100},
			{"fieldname": "days_to_due", "label": _("Days to Due"), "fieldtype": "Int", "width": 90},
			{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 90},
		]
	cols += [
		{"fieldname": "party_type", "label": _("Party Type"), "fieldtype": "Data", "hidden": 1},
		{"fieldname": "party", "label": _("Party"), "fieldtype": "Dynamic Link", "options": "party_type", "width": 130},
		{"fieldname": "party_name", "label": _("Party Name"), "fieldtype": "Data", "width": 180},
		{"fieldname": "count", "label": _("Cheques"), "fieldtype": "Int", "width": 70},
		{"fieldname": "total", "label": _("Total"), "fieldtype": "Currency", "width": 120},
	]
	cols += [{"fieldname": f, "label": _(label), "fieldtype": "Currency", "width": 110} for f, label, _l, _h in BUCKETS]
	return cols


def chart(rows):
	rows = list(rows)
	return {
		"data": {
			"labels": [_(label) for _f, label, _l, _h in BUCKETS],
			"datasets": [{"name": _("Amount"), "values": [sum(flt(r[f]) for r in rows) for f, *_rest in BUCKETS]}],
		},
		"type": "bar",
		"fieldtype": "Currency",
	}
