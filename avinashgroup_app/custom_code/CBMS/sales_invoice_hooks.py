"""Sales Invoice doc_events for the CBMS integration.

Non-negotiable rule: nothing here may ever block a Sales Invoice submission. Every code path
either does fast, local, non-throwing work, or hands the slow network call off to a background
job. If something unexpected still goes wrong, it's logged to the Error Log and left for
`avinashgroup_app.custom_code.CBMS.scheduler.reconcile_missing_cbms_bills` to pick up later —
so a bill is never silently lost even if this hook itself misbehaves.
"""

import frappe

from avinashgroup_app.custom_code.CBMS import utils
from avinashgroup_app.custom_code.CBMS.api_client import send_bill_to_cbms, send_return_to_cbms


def get_cbms_config(company):
	"""The enabled CBMS Config for a company, or None."""
	name = frappe.db.exists("CBMS Config", {"company": company, "enable_cbms": 1})
	return frappe.get_doc("CBMS Config", name) if name else None


def in_cbms_scope(config, posting_date):
	"""Only invoices posted on/after the company's CBMS go-live date are ever synced —
	no retroactive reporting of historical invoices that predate go-live."""
	if not config.enable_from_date:
		return False
	return frappe.utils.getdate(posting_date) >= frappe.utils.getdate(config.enable_from_date)


def build_cbms_fields(sales_invoice):
	"""Field mapping shared by CBMS Bill and CBMS Bill Return, from a submitted Sales Invoice."""
	customer_pan = frappe.db.get_value("Customer", sales_invoice.customer, "tax_id")
	seller_pan = frappe.get_cached_value("Company", sales_invoice.company, "tax_id")

	total_sales = abs(sales_invoice.grand_total)
	has_vat = any((row.rate or 0) > 0 for row in sales_invoice.taxes)
	taxable_sales_vat = abs(sales_invoice.base_net_total) if has_vat else 0
	vat = (total_sales - taxable_sales_vat) if has_vat else 0

	return {
		"company": sales_invoice.company,
		"sales_invoice": sales_invoice.name,
		"buyer_name": sales_invoice.customer_name or sales_invoice.customer,
		"buyer_pan": customer_pan or "",
		"seller_pan": seller_pan or "",
		"fiscal_year": utils.cbms_fiscal_year(sales_invoice.posting_date),
		"total_sales": total_sales,
		"taxable_sales_vat": taxable_sales_vat,
		"vat": vat,
		"datetime_client": frappe.utils.now_datetime(),
	}


def create_cbms_bill(sales_invoice):
	if frappe.db.exists("CBMS Bill", {"sales_invoice": sales_invoice.name}):
		return None

	fields = build_cbms_fields(sales_invoice)
	fields.update(
		{
			"invoice_number": utils.cbms_invoice_number(sales_invoice),
			"invoice_date": sales_invoice.posting_date,
			"invoice_date_bs": utils.bs_date_str(sales_invoice.posting_date),
		}
	)
	doc = frappe.get_doc({"doctype": "CBMS Bill", **fields})
	doc.insert(ignore_permissions=True)
	return doc


def create_cbms_bill_return(sales_invoice):
	if frappe.db.exists("CBMS Bill Return", {"sales_invoice": sales_invoice.name}):
		return None

	original_invoice_number = frappe.db.get_value(
		"CBMS Bill", {"sales_invoice": sales_invoice.return_against}, "invoice_number"
	)
	if not original_invoice_number:
		# The original invoice hasn't been posted to CBMS yet (or CBMS wasn't enabled
		# for it) — nothing to reference. reconcile_missing_cbms_bills will retry this
		# once the original invoice has a CBMS Bill.
		return None

	fields = build_cbms_fields(sales_invoice)
	fields.update(
		{
			"ref_invoice_number": original_invoice_number,
			"credit_note_number": utils.cbms_invoice_number(sales_invoice),
			"credit_note_date": sales_invoice.posting_date,
			"credit_note_date_bs": utils.bs_date_str(sales_invoice.posting_date),
			"reason_for_return": sales_invoice.get("custom_reason_for_return") or "Goods Returned",
		}
	)
	doc = frappe.get_doc({"doctype": "CBMS Bill Return", **fields})
	doc.insert(ignore_permissions=True)
	return doc


def on_submit(doc, method=None):
	lock_key = f"cbms_processing_{doc.name}"
	if frappe.cache().get_value(lock_key):
		return
	frappe.cache().set_value(lock_key, 1, expires_in_sec=300)

	try:
		config = get_cbms_config(doc.company)
		if not config or not in_cbms_scope(config, doc.posting_date):
			return

		if doc.is_return:
			cbms_doc = create_cbms_bill_return(doc)
			enqueue_method = "avinashgroup_app.custom_code.CBMS.api_client.send_return_to_cbms"
			enqueue_kwargs = {"cbms_bill_return_name": cbms_doc.name} if cbms_doc else None
		else:
			cbms_doc = create_cbms_bill(doc)
			enqueue_method = "avinashgroup_app.custom_code.CBMS.api_client.send_bill_to_cbms"
			enqueue_kwargs = {"cbms_bill_name": cbms_doc.name} if cbms_doc else None

		if not cbms_doc:
			return

		frappe.db.commit()
		frappe.enqueue(enqueue_method, queue="default", timeout=300, **enqueue_kwargs)
	except Exception:
		frappe.log_error(
			title=f"CBMS: failed to record Sales Invoice {doc.name} on submit",
			message=frappe.get_traceback(),
		)
	finally:
		frappe.cache().delete_value(lock_key)


def before_cancel(doc, method=None):
	"""Block cancelling a Sales Invoice/Return that IRD has already been told about —
	once a bill is reported to CBMS it can't just disappear from our side. Anything not
	yet synced (or CBMS not enabled) can still be cancelled freely.
	"""
	cbms_doctype = "CBMS Bill Return" if doc.is_return else "CBMS Bill"
	sync_status = frappe.db.get_value(cbms_doctype, {"sales_invoice": doc.name}, "sync_status")
	if sync_status == "Synced":
		frappe.throw(
			frappe._(
				"{0} has already been reported to CBMS/IRD and cannot be cancelled."
			).format(doc.name)
		)
