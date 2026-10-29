"""Scheduled job that keeps CBMS in sync when a send didn't get all the way through.

- retry_failed_cbms_syncs: re-sends every CBMS Bill/CBMS Bill Return still not Synced.

Nothing here creates CBMS Bills. That is the exclusive job of the Sales Invoice on_submit
hook, so the set of invoices reported to IRD is a deterministic function of what was
submitted — not of when a background job happened to run against the config of the moment.
A cron that mass-created bills on a schedule once swept up nine months of out-of-scope
invoices in the gap between enabling a config and correcting its Send From Date; because
reporting a bill to IRD is irreversible, that class of mistake must not be reachable.

Submitted invoices that somehow have no CBMS Bill (a data import bypassing hooks, a
crash inside on_submit) are therefore never auto-created. Backfill is an explicit,
operator-initiated action.
"""

import frappe


def _enabled_configs():
	return frappe.get_all(
		"CBMS Config",
		filters={"enable_cbms": 1, "enable_from_date": ["is", "set"]},
		fields=["name", "company", "enable_from_date", "bill_retry_batch_size", "return_retry_batch_size"],
	)


def queue_failed_for_company(config):
	"""Re-enqueue every not-yet-Synced CBMS Bill / CBMS Bill Return for one company."""
	bill_limit = config.bill_retry_batch_size or 50
	return_limit = config.return_retry_batch_size or 50

	failed_bills = frappe.get_all(
		"CBMS Bill",
		filters={"sync_status": ["!=", "Synced"], "company": config.company},
		pluck="name",
		limit=bill_limit,
	)
	failed_returns = frappe.get_all(
		"CBMS Bill Return",
		filters={"sync_status": ["!=", "Synced"], "company": config.company},
		pluck="name",
		limit=return_limit,
	)

	for bill_name in failed_bills:
		frappe.enqueue(
			"avinashgroup_app.custom_code.CBMS.api_client.send_bill_to_cbms",
			queue="default",
			timeout=300,
			cbms_bill_name=bill_name,
		)
	for return_name in failed_returns:
		frappe.enqueue(
			"avinashgroup_app.custom_code.CBMS.api_client.send_return_to_cbms",
			queue="default",
			timeout=300,
			cbms_bill_return_name=return_name,
		)

	return {"bills_queued": len(failed_bills), "returns_queued": len(failed_returns)}


def retry_failed_cbms_syncs():
	"""Cron job (every 5 minutes): retry all failed CBMS Bills/Returns, per company."""
	totals = {"bills_queued": 0, "returns_queued": 0}
	for config in _enabled_configs():
		result = queue_failed_for_company(config)
		totals["bills_queued"] += result["bills_queued"]
		totals["returns_queued"] += result["returns_queued"]
	return totals
