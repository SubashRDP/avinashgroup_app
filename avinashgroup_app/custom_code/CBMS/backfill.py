"""Operator-initiated backfill for CBMS Bills / CBMS Bill Returns.

Purpose: create and send the CBMS record for every *submitted* Sales Invoice that
is IN CBMS SCOPE but has no CBMS Bill / CBMS Bill Return — the gap the submit hook
leaves behind when a data import bypasses hooks, or on_submit crashed before the
CBMS doc was written (see sales_invoice_hooks.py).

Why this is a hand-run tool and not a cron: see scheduler.py. Reporting a bill to
IRD cannot be undone, so *creating* bills must be an explicit action a human runs
and reviews — never something a schedule does on its own. This module therefore:

  * acts ONLY on invoices with posting_date >= the company's enable_from_date
    (the exact scope guard whose earlier absence swept nine months of
    out-of-scope invoices into IRD);
  * is DRY-RUN by default — you must pass commit=True to write/send anything;
  * reuses create_cbms_bill / create_cbms_bill_return (idempotent: they no-op if a
    CBMS record already exists) and the same send functions the cron uses;
  * sends with triggered_from="Retry", so these late sends are reported to IRD as
    isrealtime=false — they are not realtime submits.

Typical use (bench console):

    from avinashgroup_app.custom_code.CBMS import backfill
    backfill.preview()                       # read-only: what's missing, per company
    backfill.run(commit=False)               # dry run: the exact list that would send
    backfill.run(commit=True, limit=50)      # actually create + enqueue, 50 at a time
    backfill.run(company="Nepal Gas Udhyog Pvt. Ltd.", commit=True)
"""

import frappe

from avinashgroup_app.custom_code.CBMS.activity_log import log_cbms_activity
from avinashgroup_app.custom_code.CBMS.sales_invoice_hooks import (
	create_cbms_bill,
	create_cbms_bill_return,
	get_cbms_config,
	in_cbms_scope,
)

_SEND = {
	False: (
		"avinashgroup_app.custom_code.CBMS.api_client.send_bill_to_cbms",
		"cbms_bill_name",
	),
	True: (
		"avinashgroup_app.custom_code.CBMS.api_client.send_return_to_cbms",
		"cbms_bill_return_name",
	),
}


def _target_configs(company=None):
	"""Enabled CBMS Configs with a go-live date, optionally one company."""
	filters = {"enable_cbms": 1, "enable_from_date": ["is", "set"]}
	if company:
		filters["company"] = company
	return frappe.get_all(
		"CBMS Config",
		filters=filters,
		fields=["name", "company", "enable_from_date"],
	)


def find_missing(company=None):
	"""Submitted Sales Invoices in CBMS scope that have NO CBMS Bill / Bill Return.

	Read-only. Returns a list of frappe._dicts with name, company, posting_date,
	is_return, return_against — oldest first, so a limited run backfills in
	chronological (IRD-numbering) order. Standalone credit notes with no
	return_against are excluded: a return with no original cannot be reported.
	"""
	missing = []
	for cfg in _target_configs(company):
		invoices = frappe.get_all(
			"Sales Invoice",
			filters={
				"docstatus": 1,
				"company": cfg.company,
				"posting_date": [">=", cfg.enable_from_date],
			},
			fields=["name", "company", "posting_date", "is_return", "return_against"],
			order_by="posting_date asc, name asc",
		)
		for inv in invoices:
			cbms_doctype = "CBMS Bill Return" if inv.is_return else "CBMS Bill"
			if frappe.db.exists(cbms_doctype, {"sales_invoice": inv.name}):
				continue
			if inv.is_return and not inv.return_against:
				# No original invoice to reference — cannot be sent as a return.
				continue
			missing.append(inv)
	return missing


def preview(company=None):
	"""Read-only summary of the gap: counts and date span per company. Creates
	and sends nothing — run this first."""
	rows = find_missing(company)
	by_company = {}
	for r in rows:
		c = by_company.setdefault(
			r.company, {"bills": 0, "returns": 0, "from": r.posting_date, "to": r.posting_date}
		)
		c["returns" if r.is_return else "bills"] += 1
		c["from"] = min(c["from"], r.posting_date)
		c["to"] = max(c["to"], r.posting_date)
	return {
		"total": len(rows),
		"bills": sum(1 for r in rows if not r.is_return),
		"returns": sum(1 for r in rows if r.is_return),
		"by_company": by_company,
	}


def run(company=None, limit=None, commit=False, triggered_from="Retry"):
	"""Create the missing CBMS records and enqueue their send.

	DRY RUN unless commit=True: with commit=False it returns exactly which
	invoices *would* be processed and writes/sends nothing. `limit` caps how many
	are handled this call (oldest first) so you can backfill in reviewable
	batches. Each record is committed and enqueued individually, so a failure on
	one invoice never rolls back the others — it is logged to Error Log and
	skipped. Idempotent: re-running only picks up what is still missing.
	"""
	missing = find_missing(company)
	if limit:
		missing = missing[: int(limit)]

	if not commit:
		return {
			"dry_run": True,
			"would_process": len(missing),
			"bills": sum(1 for m in missing if not m.is_return),
			"returns": sum(1 for m in missing if m.is_return),
			"invoices": [m.name for m in missing],
		}

	done = {"bills": 0, "returns": 0, "skipped": 0}
	for m in missing:
		_create_and_enqueue(frappe.get_doc("Sales Invoice", m.name), triggered_from, done)

	done["remaining"] = len(find_missing(company))
	return done


def run_for(invoice_names, commit=False, triggered_from="Retry"):
	"""Create + send CBMS records for an EXPLICIT list of Sales Invoice names.

	Use when you want to report exactly the invoices you name, rather than every
	in-scope invoice find_missing() turns up. Each name is validated the same way
	the submit hook would: it must exist, be submitted (docstatus 1), have an
	enabled CBMS Config, and be in scope (posting_date >= enable_from_date). A
	name failing any check — or already having a CBMS record — is reported under
	'skipped' with the reason and never sent. DRY RUN unless commit=True.
	"""
	if isinstance(invoice_names, str):
		invoice_names = [n.strip() for n in invoice_names.splitlines() if n.strip()]

	checked, skipped = [], []
	for name in invoice_names:
		if not frappe.db.exists("Sales Invoice", name):
			skipped.append({"invoice": name, "reason": "does not exist"})
			continue
		inv = frappe.get_doc("Sales Invoice", name)
		if inv.docstatus != 1:
			skipped.append({"invoice": name, "reason": f"not submitted (docstatus {inv.docstatus})"})
			continue
		config = get_cbms_config(inv.company)
		if not config or not in_cbms_scope(config, inv.posting_date):
			skipped.append({"invoice": name, "reason": "out of CBMS scope / no enabled config"})
			continue
		cbms_doctype = "CBMS Bill Return" if inv.is_return else "CBMS Bill"
		if frappe.db.exists(cbms_doctype, {"sales_invoice": name}):
			skipped.append({"invoice": name, "reason": "CBMS record already exists"})
			continue
		if inv.is_return and not inv.return_against:
			skipped.append({"invoice": name, "reason": "return with no original invoice"})
			continue
		checked.append(inv)

	if not commit:
		return {
			"dry_run": True,
			"would_process": [i.name for i in checked],
			"bills": sum(1 for i in checked if not i.is_return),
			"returns": sum(1 for i in checked if i.is_return),
			"skipped": skipped,
		}

	done = {"bills": 0, "returns": 0, "skipped": len(skipped), "skipped_detail": skipped}
	# Bills before returns, so an original's CBMS Bill exists before its return is
	# sent (send_return_to_cbms otherwise holds the return until the bill Syncs).
	for inv in sorted(checked, key=lambda i: (bool(i.is_return), i.name)):
		_create_and_enqueue(inv, triggered_from, done)
	return done


def _create_and_enqueue(invoice, triggered_from, tally):
	"""Create the CBMS Bill/Return for one submitted invoice and enqueue its send,
	tallying the outcome. Commits per invoice; a failure rolls back only this one,
	is logged to Error Log, and counts as skipped."""
	is_return = bool(invoice.is_return)
	try:
		cbms_doc = (
			create_cbms_bill_return(invoice) if is_return else create_cbms_bill(invoice)
		)
		if not cbms_doc:
			# Already had a CBMS record, or a return with no original — nothing to do.
			tally["skipped"] += 1
			return

		log_cbms_activity(
			cbms_doc,
			"Queued",
			details="Created by operator backfill; send enqueued",
			triggered_from=triggered_from,
		)
		frappe.db.commit()

		method, kwarg = _SEND[is_return]
		frappe.enqueue(
			method,
			queue="default",
			timeout=300,
			triggered_from=triggered_from,
			**{kwarg: cbms_doc.name},
		)
		tally["returns" if is_return else "bills"] += 1
	except Exception:
		frappe.db.rollback()
		frappe.log_error(
			title=f"CBMS backfill failed: {invoice.name}", message=frappe.get_traceback()
		)
		tally["skipped"] += 1
