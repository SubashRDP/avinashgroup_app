"""Sales Invoice doc_events for the CBMS integration.

Non-negotiable rule: nothing here may ever block a Sales Invoice submission. Every code path
either does fast, local, non-throwing work, or hands the slow network call off to a background
job.

This hook is also the ONLY place a CBMS Bill / CBMS Bill Return is ever created. No scheduled
job creates them, because reporting a bill to IRD cannot be undone (once Synced, `before_cancel`
refuses to let the invoice be cancelled). Which invoices get reported must therefore follow
deterministically from which invoices were submitted, rather than from when a cron ran and what
the config said at that instant.

The cost of that guarantee: if this hook fails, the invoice has no CBMS Bill and nothing will
create one behind your back. The failure is logged to the Error Log and the gap must be closed
by an explicit, operator-initiated backfill.
"""

import frappe
from frappe.utils import flt
from frappe.utils.nestedset import get_ancestors_of

from avinashgroup_app.custom_code.CBMS import utils
from avinashgroup_app.custom_code.CBMS.activity_log import log_cbms_activity
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


def _ird_locked(doc):
	"""True when the invoice falls under IRD e-billing: its company has an enabled
	CBMS Config and the posting date is on/after the go-live cutoff
	(enable_from_date). Such invoices are immutable — no cancel, no delete."""
	config = get_cbms_config(doc.company)
	return bool(config and in_cbms_scope(config, doc.posting_date))


def onload(doc, method=None):
	"""Tell the desk form whether this invoice is IRD-locked so it can hide the
	Cancel/Delete menu entries (sales_invoice.js). The server-side blocks below
	are the real enforcement."""
	doc.set_onload("ird_locked", _ird_locked(doc))


def on_trash(doc, method=None):
	if frappe.flags.in_install or frappe.flags.in_uninstall or frappe.flags.in_migrate:
		return
	if _ird_locked(doc):
		frappe.throw(
			frappe._(
				"Sales Invoice {0} is under IRD e-billing (on/after the CBMS cutoff date) "
				"and cannot be deleted: its invoice number is already consumed and the "
				"IRD numbering sequence must have no gaps."
			).format(doc.name)
		)


def is_export_invoice(sales_invoice):
	"""Export per the IRD mapping spec: customer territory outside Nepal, or invoice
	currency other than NPR."""
	if (sales_invoice.currency or "NPR") != "NPR":
		return True
	territory = frappe.db.get_value("Customer", sales_invoice.customer, "territory")
	# No territory / the "All Territories" root = unspecified, treated as domestic.
	if not territory or territory in ("Nepal", "All Territories"):
		return False
	return "Nepal" not in (get_ancestors_of("Territory", territory) or [])


def _line_value(item):
	"""A line's sales value in company currency: custom_total (net + excise) when the
	selling-taxes handler has computed it, else base_net_amount. VAT here is levied on
	net + excise, so this is the base the taxable/exempt split must use for the
	reported components to reconcile with grand_total."""
	return flt(item.get("custom_total")) 


def _booked_vat(sales_invoice):
	"""The VAT actually booked on the invoice — summed from each line's
	custom_vat_amount where VAT Apply On is "VAT 13%" or "Amount" (both maintained
	by salesinvoice_taxes on every save; "VAT 0%" lines carry no VAT). Falls back to
	the parent custom_total_vat_amount, then to the VAT-account tax rows, for any
	document that predates the per-line fields."""
	line_vat = sum(
		flt(item.get("custom_vat_amount"))
		for item in sales_invoice.items
		if item.get("custom_vat_apply_on") in ("VAT 13%", "Amount")
	)
	if line_vat:
		return abs(line_vat)
	booked = flt(sales_invoice.get("custom_total_vat_amount"))
	if booked:
		return abs(booked)
	return abs(
		sum(
			flt(row.base_tax_amount)
			for row in (sales_invoice.taxes or [])
			if (row.account_head or "").upper().startswith("VAT")
		)
	)



def build_cbms_fields(sales_invoice):
	"""Field mapping shared by CBMS Bill and CBMS Bill Return, from a submitted Sales
	Invoice, per the IRD mapping spec:

	"""
	customer_pan = frappe.db.get_value("Customer", sales_invoice.customer, "tax_id")
	seller_pan = frappe.get_cached_value("Company", sales_invoice.company, "tax_id")

	exempt_sales = abs(
		sum(
			_line_value(item)
			for item in sales_invoice.items
			if item.get("custom_vat_apply_on") == "VAT 0%"
		)
	)
	taxable_sales = abs(
		sum(
			_line_value(item)
			for item in sales_invoice.items
			if item.get("custom_vat_apply_on") != "VAT 0%"
		)
	)
	vat = _booked_vat(sales_invoice)

	# Excise: lines carrying a custom_excise_value (manual, maintained by
	# salesinvoice_taxes). excise = their summed excise; excisable_amount = the
	# summed base_net_amount of those same lines (the base the excise sits on).
	excise = abs(
		sum(flt(item.get("custom_excise_value")) for item in sales_invoice.items)
	)
	excisable_amount = abs(
		sum(
			flt(item.amount)
			for item in sales_invoice.items
			if flt(item.get("custom_excise_value"))
		)
	)

	if is_export_invoice(sales_invoice):
		# Exports are zero-rated: the whole sales value goes in export_sales.
		export_sales = sales_invoice.grand_total
		taxable_sales = 0
		total_sales = abs(sales_invoice.grand_total)
	else:
		export_sales = 0
		total_sales = abs(sales_invoice.grand_total) - exempt_sales

	discount = 0
	if sales_invoice.apply_discount_on == "Net Total":
		discount = abs(flt(sales_invoice.discount_amount))

	return {
		"company": sales_invoice.company,
		"sales_invoice": sales_invoice.name,
		"buyer_name": sales_invoice.customer_name or sales_invoice.customer,
		"buyer_pan": customer_pan or "",
		"seller_pan": seller_pan or "",
		"fiscal_year": utils.cbms_fiscal_year(sales_invoice.posting_date, sales_invoice.company),
		"total_sales": flt(total_sales, 2),
		"taxable_sales_vat": flt(taxable_sales, 2),
		"vat": flt(vat, 2),
		"tax_exempted_sales": flt(exempt_sales, 2),
		"export_sales": flt(export_sales, 2),
		"excisable_amount": flt(excisable_amount, 2),
		"excise": flt(excise, 2),
		"discount": flt(discount, 2),
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

	if not sales_invoice.return_against:
		# Standalone credit note with no original invoice — nothing to reference.
		return None

	# The original invoice's branch-wise number, straight from its branch field —
	# falling back to the invoice name when the field is absent on this site or
	# blank on legacy data (mirrors utils.cbms_invoice_number, so this always
	# matches the invoice_number the original's CBMS Bill was created with).
	# send_return_to_cbms still holds this return until the original's CBMS Bill
	# is Synced, so ordering is unchanged.
	original_invoice_number = sales_invoice.return_against
	if frappe.get_meta("Sales Invoice").has_field("custom_branch_name"):
		original_invoice_number = (
			frappe.db.get_value("Sales Invoice", sales_invoice.return_against, "custom_branch_name")
			or sales_invoice.return_against
		)

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
			enqueue_kwargs = (
				{"cbms_bill_return_name": cbms_doc.name, "triggered_from": "Submit"}
				if cbms_doc
				else None
			)
		else:
			cbms_doc = create_cbms_bill(doc)
			enqueue_method = "avinashgroup_app.custom_code.CBMS.api_client.send_bill_to_cbms"
			enqueue_kwargs = (
				{"cbms_bill_name": cbms_doc.name, "triggered_from": "Submit"} if cbms_doc else None
			)

		if not cbms_doc:
			return

		log_cbms_activity(
			cbms_doc,
			"Queued",
			details="Created on invoice submit and queued for sync",
			triggered_from="Submit",
		)
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
	"""Block cancelling any Sales Invoice/Return under IRD e-billing (posting date
	on/after the CBMS cutoff): an issued IRD invoice is never cancelled — it is
	reversed by a credit note. Invoices outside CBMS scope can still be cancelled,
	unless their bill somehow already reached IRD (Synced).
	"""
	if _ird_locked(doc):
		frappe.throw(
			frappe._(
				"Sales Invoice {0} is under IRD e-billing (on/after the CBMS cutoff date) "
				"and cannot be cancelled. Issue a Credit Note (Sales Return) against it instead."
			).format(doc.name)
		)

	cbms_doctype = "CBMS Bill Return" if doc.is_return else "CBMS Bill"
	sync_status = frappe.db.get_value(cbms_doctype, {"sales_invoice": doc.name}, "sync_status")
	if sync_status == "Synced":
		frappe.throw(
			frappe._(
				"{0} has already been reported to CBMS/IRD and cannot be cancelled."
			).format(doc.name)
		)
