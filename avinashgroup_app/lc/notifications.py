"""LC daily digest — the dates an importer must not miss, emailed to accounts.

An LC fails quietly: a shipment after the latest shipment date, documents after
expiry, a usance bill not funded on its maturity date, or customs proof not
given to the bank in time all turn into discrepancies, penalty interest or an
NRB reporting problem — and nothing in ERPNext warns about any of them. Each
morning this collects what falls due within LC Settings → "Warn This Many Days
Ahead" (and anything already overdue) and mails it to the digest role.

Boundary: it only reads and emails. Statuses do not change by date; an expired
LC is closed by a person (lifecycle.close), because the bank may still honour
documents under a waiver.
"""

import frappe
from frappe import _
from frappe.utils import add_days, cint, getdate, nowdate

ACTIVE = ("Opened", "Partly Settled", "Settled")


def daily_run():
	"""Scheduler entry point (hooks.py scheduler_events, cron 35 8 * * *)."""
	try:
		send_daily_digest()
	except Exception:
		frappe.log_error(title="LC daily digest failed", message=frappe.get_traceback())


def digest_rows(today=None, days_ahead=15):
	today = getdate(today or nowdate())
	upto = add_days(today, cint(days_ahead))
	lc_fields = ["name", "company", "supplier_name", "lc_no", "currency", "lc_amount", "available_amount",
		"latest_shipment_date", "expiry_date", "status"]
	shipment_sql = """select l.name, l.company, l.supplier_name, l.lc_no, l.currency, s.shipment_no,
		s.amount, s.{date} as due, s.status
		from `tabLC Shipment` s join `tabLetter of Credit` l on l.name = s.parent
		where l.docstatus = 1 and {cond} and s.{date} <= %(upto)s order by s.{date}"""
	return {
		"shipping": frappe.get_all("Letter of Credit", fields=lc_fields, order_by="latest_shipment_date asc",
			filters={"docstatus": 1, "status": ["in", ("Opened", "Partly Settled")],
				"available_amount": [">", 0], "latest_shipment_date": ["between", [today, upto]]}),
		"expiring": frappe.get_all("Letter of Credit", fields=lc_fields, order_by="expiry_date asc",
			filters={"docstatus": 1, "status": ["in", ACTIVE], "expiry_date": ["<=", upto]}),
		"maturing": frappe.db.sql(shipment_sql.format(date="maturity_date", cond="s.status = 'Accepted'"),
			{"upto": upto}, as_dict=True),
		"customs": frappe.db.sql(shipment_sql.format(date="customs_proof_due",
			cond="s.status = 'Settled' and s.customs_proof_submitted_on is null"), {"upto": upto}, as_dict=True),
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
