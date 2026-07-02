"""Sales Invoice doc_events for the CBMS integration.

Non-negotiable rule: nothing here may ever block a Sales Invoice submission. Every code path
either does fast, local, non-throwing work, or hands the slow network call off to a background
job. If something unexpected still goes wrong, it's logged to the Error Log and left for
`avinashgroup_app.custom_code.CBMS.scheduler.reconcile_missing_cbms_bills` to pick up later —
so a bill is never silently lost even if this hook itself misbehaves.
"""

import frappe
from frappe.utils import flt
from frappe.utils.nestedset import get_ancestors_of

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
	return flt(item.get("custom_total")) or flt(item.base_net_amount)


def _booked_vat(sales_invoice):
	"""The VAT actually booked on the invoice — custom_total_vat_amount (maintained by
	salesinvoice_taxes on every save), falling back to the VAT-account tax rows for any
	document that predates that handler."""
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

	- tax_exempted_sales: line values where VAT Apply On = "VAT 0%"
	- taxable_sales_vat:  line values of every other line
	- vat:                the VAT amount booked on the invoice (not derived)
	- total_sales:        grand total excluding the VAT-0% (exempt) line values
	- export_sales:       whole sales value when territory ≠ Nepal or currency ≠ NPR
	- discount:           additional discount amount when applied on Net Total
	                      (recorded on the CBMS doc only; the IRD API has no such field)
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

	if is_export_invoice(sales_invoice):
		# Exports are zero-rated: the whole sales value goes in export_sales.
		export_sales = taxable_sales + exempt_sales
		taxable_sales = exempt_sales = 0
		total_sales = abs(sales_invoice.base_grand_total)
	else:
		export_sales = 0
		total_sales = abs(sales_invoice.base_grand_total) - exempt_sales

	discount = 0
	if sales_invoice.apply_discount_on == "Net Total":
		discount = abs(flt(sales_invoice.base_discount_amount))

	return {
		"company": sales_invoice.company,
		"sales_invoice": sales_invoice.name,
		"buyer_name": sales_invoice.customer_name or sales_invoice.customer,
		"buyer_pan": customer_pan or "",
		"seller_pan": seller_pan or "",
		"fiscal_year": utils.cbms_fiscal_year(sales_invoice.posting_date),
		"total_sales": flt(total_sales, 2),
		"taxable_sales_vat": flt(taxable_sales, 2),
		"vat": flt(vat, 2),
		"tax_exempted_sales": flt(exempt_sales, 2),
		"export_sales": flt(export_sales, 2),
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
