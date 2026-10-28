"""PDC notifications — the daily digest to accounts, and SMS to the party.

Two audiences, two channels:

* Accounts staff get one email a day (PDC Settings → Daily Email Digest) listing
  received cheques due for deposit, issued cheques about to be presented, and
  cheques that bounced yesterday. Nothing in ERPNext tells anyone a cheque in the
  drawer has reached its date; without this the cheque goes stale unnoticed.
* The customer / supplier gets an SMS on receipt, before the cheque date, on
  clearance and on bounce — each one its own tick in PDC Settings, under a master
  "Send SMS to Party" switch. Off by default.

SMS goes through `sparrow_sms` — the same post-commit send, Sparrow SMS Log row
and queue fallback every other SMS in the app uses — so it also obeys Sparrow SMS
Settings → Enabled. This module only decides *whether* and *what*.

Never blocks a cheque step: a failed render or a missing phone number is logged
(Error Log / Sparrow SMS Log) and the step carries on.

Not done here: SMS Notification Rule records also work on PDC Cheque (its
submit / cancel events), and are independent of these switches. Use one or the
other for a given message, not both, or the party gets it twice.
"""

import frappe
from frappe import _
from frappe.utils import add_days, cint, getdate, nowdate

# PDC Settings field pairs: (switch, template) per event.
SMS_EVENTS = {
	"receipt": ("sms_on_receipt", "receipt_template"),
	"reminder": ("sms_due_reminder", "reminder_template"),
	"clearance": ("sms_on_clearance", "clearance_template"),
	"bounce": ("sms_on_bounce", "bounce_template"),
}


def _sms_switched_on(settings, event):
	switch, _template = SMS_EVENTS[event]
	return bool(
		cint(settings.send_sms)
		and cint(settings.get(switch))
		and frappe.db.get_single_value("Sparrow SMS Settings", "enabled")
	)


def party_mobile(party_type, party):
	"""The party's mobile: own field, then primary contact, then any linked contact."""
	if party_type not in ("Customer", "Supplier"):
		return None
	meta = frappe.get_meta(party_type)
	for field in ("custom_mobile_number", "mobile_no"):
		if meta.has_field(field):
			value = frappe.db.get_value(party_type, party, field)
			if value:
				return value
	contact = frappe.db.sql(
		"""select c.mobile_no, c.phone from `tabContact` c
		join `tabDynamic Link` dl on dl.parent = c.name and dl.parenttype = 'Contact'
		where dl.link_doctype = %s and dl.link_name = %s
		order by c.is_primary_contact desc, c.modified desc limit 1""",
		(party_type, party),
		as_dict=True,
	)
	if contact:
		return contact[0].mobile_no or contact[0].phone
	return None


def send_party_sms(cheque, event):
	"""Queue one SMS for `event` if PDC Settings says so. Never raises."""
	try:
		settings = frappe.get_cached_doc("PDC Settings")
		if not _sms_switched_on(settings, event):
			return False
		if frappe.flags.in_import or frappe.flags.in_migrate or frappe.flags.in_patch:
			return False

		from avinashgroup_app.sparrow_sms.sms_dispatch import _process_after_commit, normalize_mobile

		message = frappe.render_template(settings.get(SMS_EVENTS[event][1]) or "", {"doc": cheque})
		if not message.strip():
			return False

		receiver = cheque.mobile_no or party_mobile(cheque.party_type, cheque.party)
		context = {
			"sent_via": "Automatic",
			"reference_doctype": "PDC Cheque",
			"reference_name": cheque.name,
			"company": cheque.company,
			"party_type": cheque.party_type,
			"party": cheque.party,
			"party_name": cheque.party_name,
			"recipient_field": "pdc." + event,
			"raw_mobile_no": str(receiver or "")[:140],
			"mobile_no": normalize_mobile(receiver),
			"message": message,
		}
		if not receiver:
			context["error"] = _("No mobile number on PDC Cheque {0} or {1} {2}.").format(
				cheque.name, cheque.party_type, cheque.party
			)
		reference = f"{cheque.name} (PDC {event})"
		frappe.db.after_commit.add(
			lambda c=context, m=message, ref=reference: _process_after_commit(c, m, ref)
		)
		return True
	except Exception:
		frappe.log_error(title=f"PDC SMS ({event}) failed for {cheque.name}", message=frappe.get_traceback())
		return False


# ── Daily job ────────────────────────────────────────────────────────────────


def daily_run():
	"""Scheduler entry point: reminders first (they are per cheque), then the digest."""
	for job in (send_due_reminders, send_daily_digest):
		try:
			job()
		except Exception:
			frappe.log_error(title=f"PDC daily job {job.__name__} failed", message=frappe.get_traceback())


def send_due_reminders(today=None):
	"""SMS each customer whose received cheque falls due in `reminder_days_before` days."""
	settings = frappe.get_cached_doc("PDC Settings")
	if not _sms_switched_on(settings, "reminder"):
		return []
	today = getdate(today or nowdate())
	due = add_days(today, cint(settings.reminder_days_before))
	sent = []
	for name in frappe.get_all(
		"PDC Cheque",
		filters={
			"docstatus": 1, "cheque_type": "Received", "status": "In Hand",
			"cheque_date": ["between", [today, due]],
		},
		or_filters=[["last_reminder_on", "is", "not set"], ["last_reminder_on", "<", today]],
		pluck="name",
	):
		cheque = frappe.get_doc("PDC Cheque", name)
		if send_party_sms(cheque, "reminder"):
			# One reminder per cheque: the date window above would otherwise
			# send it every day until the cheque date.
			cheque.db_set("last_reminder_on", today, update_modified=False)
			sent.append(name)
	frappe.db.commit()
	return sent


def digest_rows(today=None, days_ahead=7):
	today = getdate(today or nowdate())
	fields = ["name", "company", "cheque_type", "status", "party_name", "party", "cheque_no",
		"cheque_date", "amount", "bank_name", "bounce_reason"]
	upto = add_days(today, cint(days_ahead))
	return {
		"to_deposit": frappe.get_all(
			"PDC Cheque",
			filters={"docstatus": 1, "cheque_type": "Received", "status": "In Hand", "cheque_date": ["<=", upto]},
			fields=fields, order_by="cheque_date asc",
		),
		"issued_due": frappe.get_all(
			"PDC Cheque",
			filters={"docstatus": 1, "cheque_type": "Issued", "status": "Issued", "cheque_date": ["<=", upto]},
			fields=fields, order_by="cheque_date asc",
		),
		"bounced": frappe.get_all(
			"PDC Cheque",
			filters={"docstatus": 1, "status": "Bounced", "bounce_date": [">=", add_days(today, -1)]},
			fields=fields, order_by="bounce_date desc",
		),
	}


def send_daily_digest(today=None):
	settings = frappe.get_cached_doc("PDC Settings")
	if not cint(settings.send_daily_digest):
		return None
	rows = digest_rows(today, settings.digest_days_ahead or 7)
	if not any(rows.values()):
		return None

	role = settings.digest_role or "Accounts Manager"
	with_role = frappe.get_all("Has Role", filters={"role": role, "parenttype": "User"}, pluck="parent")
	recipients = frappe.get_all(
		"User",
		filters={
			"enabled": 1, "user_type": "System User",
			"name": ["in", with_role or [""]],
		},
		pluck="name",
	)
	recipients = [u for u in recipients if u not in ("Administrator", "Guest")]
	if not recipients:
		return None

	message = frappe.render_template(
		"avinashgroup_app/pdc/templates/pdc_digest.html",
		{"rows": rows, "today": getdate(today or nowdate()), "days": settings.digest_days_ahead or 7},
	)
	frappe.sendmail(
		recipients=recipients,
		subject=_("Post-dated cheques: {0} to deposit, {1} issued due, {2} bounced").format(
			len(rows["to_deposit"]), len(rows["issued_due"]), len(rows["bounced"])
		),
		message=message,
	)
	return recipients
