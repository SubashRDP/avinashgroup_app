"""Scheduled jobs that keep CBMS in sync even when the on-submit hook or a background
job didn't get all the way through — the "can't fail" safety net for the integration.

- retry_failed_cbms_syncs: re-sends every CBMS Bill/CBMS Bill Return still not Synced.
- reconcile_missing_cbms_bills: finds submitted Sales Invoices that have NO CBMS Bill/
  CBMS Bill Return row at all (e.g. the on_submit hook itself hit an unexpected error)
  and creates + enqueues them.
"""

import frappe

from avinashgroup_app.custom_code.CBMS.sales_invoice_hooks import (
	create_cbms_bill,
	create_cbms_bill_return,
)


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


def _submitted_invoices_missing_cbms_row(company, enable_from_date, is_return, cbms_doctype):
	synced_invoice_names = frappe.get_all(
		cbms_doctype, filters={"company": company}, pluck="sales_invoice"
	)
	filters = {
		"company": company,
		"docstatus": 1,
		"is_return": 1 if is_return else 0,
		"posting_date": [">=", enable_from_date],
	}
	if synced_invoice_names:
		filters["name"] = ["not in", synced_invoice_names]
	return frappe.get_all("Sales Invoice", filters=filters, pluck="name")


def reconcile_missing_cbms_bills():
	"""Cron job (every 5 minutes): create+enqueue CBMS Bill/Return rows for any submitted
	Sales Invoice that doesn't have one yet, per CBMS-enabled company.
	"""
	created = {"bills": 0, "returns": 0}
	for config in _enabled_configs():
		for name in _submitted_invoices_missing_cbms_row(
			config.company, config.enable_from_date, False, "CBMS Bill"
		):
			try:
				doc = frappe.get_doc("Sales Invoice", name)
				cbms_doc = create_cbms_bill(doc)
				if cbms_doc:
					frappe.db.commit()
					frappe.enqueue(
						"avinashgroup_app.custom_code.CBMS.api_client.send_bill_to_cbms",
						queue="default",
						timeout=300,
						cbms_bill_name=cbms_doc.name,
					)
					created["bills"] += 1
			except Exception:
				frappe.log_error(
					title=f"CBMS reconcile: failed to create CBMS Bill for {name}",
					message=frappe.get_traceback(),
				)

		for name in _submitted_invoices_missing_cbms_row(
			config.company, config.enable_from_date, True, "CBMS Bill Return"
		):
			try:
				doc = frappe.get_doc("Sales Invoice", name)
				cbms_doc = create_cbms_bill_return(doc)
				if cbms_doc:
					frappe.db.commit()
					frappe.enqueue(
						"avinashgroup_app.custom_code.CBMS.api_client.send_return_to_cbms",
						queue="default",
						timeout=300,
						cbms_bill_return_name=cbms_doc.name,
					)
					created["returns"] += 1
			except Exception:
				frappe.log_error(
					title=f"CBMS reconcile: failed to create CBMS Bill Return for {name}",
					message=frappe.get_traceback(),
				)

	return created
