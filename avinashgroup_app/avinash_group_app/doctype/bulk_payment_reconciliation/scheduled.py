"""Scheduled Bulk Payment Reconciliation for customers with new activity.

Each run makes one submitted Bulk Payment Reconciliation per company. A customer
is included when all of these are true:
- a Sales Invoice, Payment Entry or Journal Entry was created after Started From
  and after the customer's latest Process Payment Reconciliation (PPR)
- the customer has both an unpaid item and an unallocated item
- the customer has no PPR Queued, Running or Paused
- the customer has receivable and advance accounts

Comparing with the customer's latest PPR means a missed run loses nothing, and a
Failed or Partially Reconciled customer is retried only after new activity.

The matching itself is still done by ERPNext's Process Payment Reconciliation job.
"""

import frappe
from frappe.utils import add_to_date, cint, get_datetime, now_datetime

from erpnext.accounts.doctype.process_payment_reconciliation.process_payment_reconciliation import (
	trigger_job_for_doc,
)

from avinashgroup_app.avinash_group_app.doctype.bulk_payment_reconciliation.bulk_payment_reconciliation import (
	latest_opening_date,
	parties_with_open_items,
	party_rows,
	pending_pprs,
)

SETTINGS = "Bulk Reconciliation Settings"
PARTY_TYPE = "Customer"

# Most PPRs allowed in Running after old Paused ones are resumed.
MAX_RUNNING_PPRS = 20

# The cron fires at about the same minute each hour, a few seconds either way.
DUE_MARGIN_MINUTES = 5


def scheduled_run():
	"""Cron entry: queue the run when it is on and due."""
	settings = frappe.get_single(SETTINGS)
	if not is_active(settings) or not is_due(settings, now_datetime()):
		return

	frappe.enqueue(
		"avinashgroup_app.avinash_group_app.doctype.bulk_payment_reconciliation.scheduled.run",
		queue="long",
		timeout=3600,
		job_id="bulk_payment_reconciliation_auto_run",
		deduplicate=True,
	)


def is_active(settings):
	return bool(
		settings.enabled
		and not settings.is_stopped
		and settings.started_from
		and frappe.db.get_single_value("Accounts Settings", "auto_reconcile_payments")
	)


def is_due(settings, now):
	if not settings.last_run_on:
		return True
	next_run = add_to_date(
		get_datetime(settings.last_run_on),
		hours=cint(settings.interval_hours) or 1,
		minutes=-DUE_MARGIN_MINUTES,
	)
	return now >= next_run


def run():
	"""Make each company's batch, resume Paused PPRs if ticked, and record the result."""
	settings = frappe.get_single(SETTINGS)
	if not is_active(settings):
		return

	run_time = now_datetime()
	results = []
	for company in frappe.get_all("Company", pluck="name", order_by="name"):
		try:
			batch, count = create_company_batch(company, settings.started_from)
			frappe.db.commit()
			if batch:
				results.append(f"{company}: {batch} ({count})")
		except Exception:
			frappe.db.rollback()
			frappe.log_error(title=f"Bulk Reconciliation failed: {company}")
			results.append(f"{company}: FAILED, see Error Log")

	if settings.resume_paused_entries:
		resumed = resume_paused_pprs()
		results.append(f"Paused entries resumed: {resumed}")
	else:
		results.append("Paused entries: not resumed (tick is off)")

	frappe.db.set_single_value(SETTINGS, "last_run_on", run_time)
	frappe.db.set_single_value(SETTINGS, "last_run_result", "\n".join(results))
	frappe.db.commit()


def create_company_batch(company, started_from):
	"""Submit one bulk document for the company. Returns (name, row count).

	Matching starts at the company's latest Opening Entry: that entry holds
	what was left from everything before it, so older documents stay out.
	A company with no Opening Entry has no start date."""
	from_date = latest_opening_date(company, PARTY_TYPE)
	customers = customers_to_reconcile(company, started_from, from_date)
	if not customers:
		return None, 0

	# PPR needs both accounts, so one customer without them must not stop the batch.
	rows = [
		row
		for row in party_rows(company, PARTY_TYPE, customers)
		if row["receivable_payable_account"] and row["default_advance_account"]
	]
	if not rows:
		return None, 0

	for row in rows:
		row.update({"party_type": PARTY_TYPE, "from_invoice_date": from_date, "from_payment_date": from_date})

	batch = frappe.get_doc(
		{
			"doctype": "Bulk Payment Reconciliation",
			"company": company,
			"party_type": PARTY_TYPE,
			"only_with_open_items": 1,
			"from_invoice_date": from_date,
			"from_payment_date": from_date,
			"parties": rows,
		}
	)
	batch.insert(ignore_permissions=True)
	batch.submit()
	return batch.name, len(rows)


def customers_to_reconcile(company, started_from, from_date=None):
	"""The company's enabled customers that a new PPR can help, sorted by ID.
	`from_date` leaves out ledger entries posted before it."""
	new_activity = customers_with_new_activity(company, started_from)
	if not new_activity:
		return []

	enabled = set(
		frappe.get_all(
			PARTY_TYPE,
			filters={"custom_company": company, "disabled": 0, "name": ("in", list(new_activity))},
			pluck="name",
		)
	)
	pending = pending_pprs(company, PARTY_TYPE)
	candidates = enabled - set(pending)
	if not candidates:
		return []

	return sorted(candidates & parties_with_open_items(company, PARTY_TYPE, candidates, from_date))


def customers_with_new_activity(company, started_from):
	"""Customers with a submitted document created after Started From and after
	their last PPR.

	This reads the documents, not the Payment Ledger, because reconciling a
	Journal Entry rewrites the ledger rows of every party on that entry.
	"""
	latest_entries = frappe.db.sql(
		"""
		SELECT party, MAX(created) AS latest
		FROM (
			SELECT customer AS party, creation AS created
			FROM `tabSales Invoice`
			WHERE company = %(company)s AND docstatus = 1 AND creation >= %(started_from)s

			UNION ALL

			SELECT party, creation AS created
			FROM `tabPayment Entry`
			WHERE company = %(company)s AND party_type = %(party_type)s
				AND docstatus = 1 AND creation >= %(started_from)s

			UNION ALL

			SELECT row.party, je.creation AS created
			FROM `tabJournal Entry` je
			JOIN `tabJournal Entry Account` row ON row.parent = je.name
			WHERE je.company = %(company)s AND row.party_type = %(party_type)s
				AND je.docstatus = 1 AND je.creation >= %(started_from)s
		) new_documents
		GROUP BY party
		""",
		{"company": company, "party_type": PARTY_TYPE, "started_from": started_from},
		as_dict=True,
	)
	if not latest_entries:
		return set()

	latest_pprs = dict(
		frappe.db.sql(
			"""
			SELECT party, MAX(creation)
			FROM `tabProcess Payment Reconciliation`
			WHERE company = %(company)s AND party_type = %(party_type)s AND docstatus = 1
			GROUP BY party
			""",
			{"company": company, "party_type": PARTY_TYPE},
		)
	)
	return {
		entry.party
		for entry in latest_entries
		if entry.party not in latest_pprs or entry.latest > latest_pprs[entry.party]
	}


def resume_paused_pprs():
	"""Resume the oldest Paused PPRs while Running stays within MAX_RUNNING_PPRS."""
	running = frappe.db.count("Process Payment Reconciliation", {"docstatus": 1, "status": "Running"})
	slots = MAX_RUNNING_PPRS - running
	if slots <= 0:
		return 0

	paused = frappe.get_all(
		"Process Payment Reconciliation",
		filters={"docstatus": 1, "status": "Paused"},
		order_by="creation asc",
		limit=slots,
		pluck="name",
	)
	for name in paused:
		trigger_job_for_doc(name)
		frappe.db.commit()
	return len(paused)
