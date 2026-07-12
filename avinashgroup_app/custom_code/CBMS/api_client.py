"""HTTP client for Nepal IRD's Central Billing Monitoring System (CBMS) API.

Posts CBMS Bill / CBMS Bill Return records to https://cbapi.ird.gov.np. Every function here
only ever updates its own record's sync fields and returns True/False — it never raises, so it
is always safe to call from a background job without risking an unhandled-exception retry loop.
"""

import frappe
import requests
from frappe.utils import getdate

from avinashgroup_app.custom_code.CBMS.activity_log import log_cbms_activity

BILL_URL = "https://cbapi.ird.gov.np/api/bill"
RETURN_URL = "https://cbapi.ird.gov.np/api/billreturn"
REQUEST_TIMEOUT = 30

# Response code meanings differ between the two endpoints (see vendor API doc):
# for /api/bill, 101 means "bill already exists" and counts as success; for
# /api/billreturn, 101 means "bill does not exist" and is a failure.
BILL_SUCCESS_CODES = {"200", "101"}
BILL_ERRORS = {
	"100": "API credentials do not match",
	"101": "Bill already exists",
	"102": "Exception while saving bill details",
	"103": "Unknown exception",
	"104": "Model invalid",
}

RETURN_SUCCESS_CODES = {"200"}
RETURN_ERRORS = {
	"100": "API credentials do not match",
	"101": "Bill does not exist",
	"102": "Exception while saving bill details",
	"103": "Unknown exception",
	"104": "Model invalid",
	"105": "Bill does not exist (sales return)",
}


def _other_sales_fields(doc):
	"""HST/ESF stay 0 for this business; excisable_amount, excise, export_sales and
	tax_exempted_sales are computed on the CBMS doc by build_cbms_fields."""
	return {
		"excisable_amount": doc.excisable_amount or 0,
		"excise": doc.excise or 0,
		"taxable_sales_hst": doc.taxable_sales_hst or 0,
		"hst": doc.hst or 0,
		"amount_for_esf": doc.amount_for_esf or 0,
		"esf": doc.esf or 0,
		"export_sales": doc.export_sales or 0,
		"tax_exempted_sales": doc.tax_exempted_sales or 0,
	}


def _build_bill_payload(bill, config):
	return {
		"username": config.username,
		"password": config.get_password("password"),
		"seller_pan": bill.seller_pan,
		"buyer_pan": bill.buyer_pan or "",
		"buyer_name": bill.buyer_name or "",
		"fiscal_year": bill.fiscal_year,
		"invoice_number": bill.invoice_number,
		"invoice_date": bill.invoice_date_bs.replace("-", "."),
		"total_sales": float(bill.total_sales or 0),
		"taxable_sales_vat": float(bill.taxable_sales_vat or 0),
		"vat": float(bill.vat or 0),
		**_other_sales_fields(bill),
		"isrealtime": True,
		"datetimeClient": bill.datetime_client.strftime("%Y-%m-%dT%H:%M:%S"),
	}


def _buyer_pan_decimal(pan):
	"""/api/billreturn declares buyer_pan as a nullable decimal — any string (even "")
	fails its JSON model binding with a 400, unlike /api/bill which takes a string."""
	pan = (pan or "").strip()
	return int(pan) if pan.isdigit() else None


def _build_return_payload(bill_return, config):
	return {
		"username": config.username,
		"password": config.get_password("password"),
		"seller_pan": bill_return.seller_pan,
		"buyer_pan": _buyer_pan_decimal(bill_return.buyer_pan),
		"buyer_name": bill_return.buyer_name or "",
		"fiscal_year": bill_return.fiscal_year,
		"ref_invoice_number": bill_return.ref_invoice_number,
		"credit_note_number": bill_return.credit_note_number,
		"credit_note_date": bill_return.credit_note_date_bs.replace("-", "."),
		"reason_for_return": bill_return.reason_for_return or "Goods Returned",
		"total_sales": float(bill_return.total_sales or 0),
		"taxable_sales_vat": float(bill_return.taxable_sales_vat or 0),
		"vat": float(bill_return.vat or 0),
		**_other_sales_fields(bill_return),
		"isrealtime": True,
		"datetimeClient": bill_return.datetime_client.strftime("%Y-%m-%dT%H:%M:%S"),
	}


def _response_code(response):
	"""CBMS returns the code either as bare text ("200") or as {"message": "200"}."""
	try:
		data = response.json()
		if isinstance(data, dict) and "message" in data:
			return str(data["message"]).strip()
	except ValueError:
		pass
	return response.text.strip()


def _record_result(doctype, name, sync_status, sync_response):
	attempt_count = frappe.db.get_value(doctype, name, "attempt_count") or 0
	frappe.db.set_value(
		doctype,
		name,
		{
			"sync_status": sync_status,
			"sync_response": (sync_response or "")[:500],
			"attempt_count": attempt_count + 1,
			"last_attempt": frappe.utils.now_datetime(),
		},
		update_modified=False,
	)
	frappe.db.commit()


def send_bill_to_cbms(cbms_bill_name, triggered_from="Retry"):
	"""POST a CBMS Bill to /api/bill. Always returns True/False, never raises."""
	try:
		bill = frappe.get_doc("CBMS Bill", cbms_bill_name)
		if bill.sync_status == "Synced":
			return True

		config = frappe.get_doc("CBMS Config", {"company": bill.company})
		if not config.enable_cbms:
			return False

		response = requests.post(
			BILL_URL, json=_build_bill_payload(bill, config), timeout=REQUEST_TIMEOUT
		)
		code = _response_code(response)

		if response.status_code == 200 and code in BILL_SUCCESS_CODES:
			log_cbms_activity(bill, "Synced", response_code=code, triggered_from=triggered_from)
			_record_result("CBMS Bill", bill.name, "Synced", code)
			return True

		error = f"{code}: {BILL_ERRORS.get(code, 'Unknown error')}"
		log_cbms_activity(bill, "Failed", details=error, response_code=code, triggered_from=triggered_from)
		_record_result("CBMS Bill", bill.name, "Failed", error)
		return False

	except Exception:
		frappe.log_error(
			title=f"CBMS bill sync failed: {cbms_bill_name}", message=frappe.get_traceback()
		)
		frappe.db.rollback()
		try:
			bill = frappe.get_doc("CBMS Bill", cbms_bill_name)
			log_cbms_activity(
				bill, "Failed", details="Exception during send — see Error Log",
				triggered_from=triggered_from,
			)
		except Exception:
			pass
		frappe.db.set_value("CBMS Bill", cbms_bill_name, "sync_status", "Failed", update_modified=False)
		frappe.db.commit()
		return False


@frappe.whitelist()
def sync_now(cbms_doctype, name):
	"""The "Sync Now" button on CBMS Bill / CBMS Bill Return forms: send this
	one record to IRD right now instead of waiting for the retry cron. Reuses
	the exact send functions the cron uses (same success codes, same activity
	logging, logged with Triggered From = Manual)."""
	frappe.only_for(("System Manager", "Accounts Manager"))
	if cbms_doctype not in ("CBMS Bill", "CBMS Bill Return"):
		frappe.throw(frappe._("Sync Now supports only CBMS Bill and CBMS Bill Return."))
	if not frappe.db.exists(cbms_doctype, name):
		frappe.throw(frappe._("{0} {1} does not exist.").format(cbms_doctype, name))

	if cbms_doctype == "CBMS Bill":
		ok = send_bill_to_cbms(name, triggered_from="Manual")
	else:
		ok = send_return_to_cbms(name, triggered_from="Manual")

	status, response = frappe.db.get_value(cbms_doctype, name, ["sync_status", "sync_response"])
	held = not ok and status != "Failed" and _last_log_operation(name) == "Held"
	return {"ok": bool(ok), "sync_status": status, "sync_response": response, "held": held}


def _last_log_operation(cbms_ref):
	return frappe.db.get_value(
		"CBMS Sync Log", {"cbms_ref": cbms_ref}, "operation", order_by="creation desc"
	)


def _original_predates_cbms(bill_return, config):
	"""True when the return's original invoice was posted before the company's
	CBMS go-live (enable_from_date, inclusive scope): the original was reported
	through the pre-CBMS system, no CBMS Bill will ever exist for it, and the
	return must be sent instead of held forever. Any missing data -> False,
	i.e. fail safe into the existing hold.

	Deliberately does not import in_cbms_scope from sales_invoice_hooks (that
	module imports this one); `<` here is the exact complement of its `>=`."""
	return_against = frappe.db.get_value(
		"Sales Invoice", bill_return.sales_invoice, "return_against"
	)
	if not return_against or not config.enable_from_date:
		return False
	posting_date = frappe.db.get_value("Sales Invoice", return_against, "posting_date")
	if not posting_date:
		return False
	return getdate(posting_date) < getdate(config.enable_from_date)


def send_return_to_cbms(cbms_bill_return_name, triggered_from="Retry"):
	"""POST a CBMS Bill Return to /api/billreturn. Always returns True/False, never raises."""
	try:
		bill_return = frappe.get_doc("CBMS Bill Return", cbms_bill_return_name)
		if bill_return.sync_status == "Synced":
			return True

		config = frappe.get_doc("CBMS Config", {"company": bill_return.company})
		if not config.enable_cbms:
			return False

		original_synced = frappe.db.get_value(
			"CBMS Bill", {"invoice_number": bill_return.ref_invoice_number}, "sync_status"
		)
		bypass_note = ""
		if original_synced != "Synced":
			if _original_predates_cbms(bill_return, config):
				# The original was reported through the pre-CBMS system — there
				# is no CBMS Bill to wait for; send the return directly.
				bypass_note = "Original invoice predates CBMS go-live — sent without original bill"
			else:
				# No HTTP attempt happens while held, and the retry cron re-enters
				# every few minutes — log the hold once, not per retry.
				if _last_log_operation(bill_return.name) != "Held":
					log_cbms_activity(
						bill_return,
						"Held",
						details=f"Original bill {bill_return.ref_invoice_number} is not Synced yet",
						triggered_from=triggered_from,
					)
					frappe.db.commit()
				return False

		response = requests.post(
			RETURN_URL, json=_build_return_payload(bill_return, config), timeout=REQUEST_TIMEOUT
		)
		code = _response_code(response)

		if response.status_code == 200 and code in RETURN_SUCCESS_CODES:
			log_cbms_activity(
				bill_return, "Synced", details=bypass_note,
				response_code=code, triggered_from=triggered_from,
			)
			_record_result("CBMS Bill Return", bill_return.name, "Synced", code)
			return True

		error = f"{code}: {RETURN_ERRORS.get(code, 'Unknown error')}"
		if bypass_note:
			error = f"{error} ({bypass_note})"
		log_cbms_activity(bill_return, "Failed", details=error, response_code=code, triggered_from=triggered_from)
		_record_result("CBMS Bill Return", bill_return.name, "Failed", error)
		return False

	except Exception:
		frappe.log_error(
			title=f"CBMS return sync failed: {cbms_bill_return_name}", message=frappe.get_traceback()
		)
		frappe.db.rollback()
		try:
			bill_return = frappe.get_doc("CBMS Bill Return", cbms_bill_return_name)
			log_cbms_activity(
				bill_return, "Failed", details="Exception during send — see Error Log",
				triggered_from=triggered_from,
			)
		except Exception:
			pass
		frappe.db.set_value(
			"CBMS Bill Return", cbms_bill_return_name, "sync_status", "Failed", update_modified=False
		)
		frappe.db.commit()
		return False
