"""LC daily digest — the dates an importer must not miss, emailed to accounts.

An LC fails quietly: goods shipped after the latest shipment date, documents
after expiry, a usance bill not funded on its maturity date, or customs proof
not given to the bank in time all turn into discrepancies, penalty interest or
an NRB reporting problem, and nothing in ERPNext warns about any of them. Each
morning this collects what falls due within LC Settings → "Warn This Many Days
Ahead" (and anything already overdue) and mails it to the digest role.

Boundary: it only reads and emails. Nothing changes status by date; an LC is
closed by a person (lifecycle.close).
"""

import frappe
from frappe import _
from frappe.utils import add_days, cint, getdate, nowdate

NOT_ARRIVED = ("Open", "In Transit")
ACTIVE = ("Open", "In Transit", "Arrived", "Transferred")


def daily_run():
	"""Scheduler entry point (hooks.py scheduler_events, cron 35 8 * * *)."""
	try:
		send_daily_digest()
	except Exception:
		frappe.log_error(title="LC daily digest failed", message=frappe.get_traceback())


def digest_rows(today=None, days_ahead=15):
	today = getdate(today or nowdate())
	upto = add_days(today, cint(days_ahead))
	lc_fields = ["name", "company", "supplier_name", "lc_no", "currency", "lc_amount",
		"latest_shipment_date", "expiry_date", "status"]
	proof_days = cint(frappe.db.get_single_value("LC Settings", "customs_proof_days"))
	customs = []
	if proof_days:
		customs = frappe.db.sql(
			"""select l.name, l.company, l.supplier_name, l.lc_no, l.currency, l.lc_amount,
				date_add(min(c.posting_date), interval %(days)s day) as due
			from `tabLetter of Credit` l join `tabLC Cost` c on c.parent = l.name and c.cost_group = 'Goods'
			where l.docstatus = 1 and l.has_customs = 1 and l.customs_proof_submitted_on is null
				and l.status in %(active)s
			group by l.name having due <= %(upto)s order by due""",
			{"days": proof_days, "upto": upto, "active": ACTIVE}, as_dict=True)
	return {
		"shipping": frappe.get_all("Letter of Credit", fields=lc_fields, order_by="latest_shipment_date asc",
			filters={"docstatus": 1, "status": "Open", "latest_shipment_date": ["between", [today, upto]]}),
		"expiring": frappe.get_all("Letter of Credit", fields=lc_fields, order_by="expiry_date asc",
			filters={"docstatus": 1, "status": ["in", NOT_ARRIVED], "expiry_date": ["<=", upto]}),
		"maturing": frappe.db.sql(
			"""select l.name, l.company, l.supplier_name, l.lc_no, l.currency, c.fc_amount as amount, c.maturity_date as due
			from `tabLC Cost` c join `tabLetter of Credit` l on l.name = c.parent
			where l.docstatus = 1 and c.paid_via = 'Acceptance' and c.paid_on is null and c.maturity_date <= %(upto)s
			order by c.maturity_date""", {"upto": upto}, as_dict=True),
		"customs": customs,
	}


def send_daily_digest(today=None):
	settings = frappe.get_cached_doc("LC Settings")
	if not cint(settings.send_daily_digest):
		return None
	days = cint(settings.alert_days_ahead) or 15
	rows = digest_rows(today, days)
	if not any(rows.values()):
		return None

	role = settings.digest_role or "Accounts Manager"
	with_role = frappe.get_all("Has Role", filters={"role": role, "parenttype": "User"}, pluck="parent")
	recipients = frappe.get_all(
		"User", filters={"enabled": 1, "user_type": "System User", "name": ["in", with_role or [""]]}, pluck="name"
	)
	recipients = [u for u in recipients if u not in ("Administrator", "Guest")]
	if not recipients:
		return None

	message = frappe.render_template(
		"avinashgroup_app/lc/templates/lc_digest.html",
		{"rows": rows, "today": getdate(today or nowdate()), "days": days},
	)
	frappe.sendmail(
		recipients=recipients,
		subject=_("Letters of credit: {0} expiring, {1} maturing, {2} customs proofs due").format(
			len(rows["expiring"]), len(rows["maturing"]), len(rows["customs"])),
		message=message,
	)
	return recipients
