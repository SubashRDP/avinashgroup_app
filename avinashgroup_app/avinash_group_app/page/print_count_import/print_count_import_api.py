# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

"""Backend for the Print Count Import page.

Wraps legacy_print_import.import_legacy_print_counts.run() so an operator can
load a "Sale Invoice Register" export from the desk instead of the bench CLI.

The work runs in a background job: the 80-81 register is 19 MB and ~31k
invoices, well past what a web request can finish. The page gets the summary
back over realtime on the `print_count_import` event.
"""

import os

import frappe
from frappe import _
from frappe.utils import cint

from avinashgroup_app.legacy_print_import.import_legacy_print_counts import run

EVENT = "print_count_import"

# xlrd 2.x reads the old binary .xls only, which is what the legacy software
# exports. A renamed .xlsx fails inside the job with a confusing error, so it
# is rejected up front.
ALLOWED_EXTENSIONS = (".xls",)


def _require_permission():
	if not frappe.has_permission("Sales Invoice Print Count", "create"):
		raise frappe.PermissionError(
			_("You are not permitted to import Sales Invoice Print Counts.")
		)


def _resolve(file_url: str) -> str:
	"""Attached File -> absolute path on disk."""
	name = frappe.db.get_value("File", {"file_url": file_url})
	if not name:
		frappe.throw(_("Attachment not found. Upload the register file again."))

	path = frappe.get_doc("File", name).get_full_path()
	if not os.path.exists(path):
		frappe.throw(_("Attachment is missing from disk: {0}").format(file_url))
	if not path.lower().endswith(ALLOWED_EXTENSIONS):
		frappe.throw(
			_("Only the old software's .xls register export can be imported (got {0}).").format(
				os.path.basename(path)
			)
		)
	return path


@frappe.whitelist()
def start(file_url, mode="max", only_prefix=None, drop_batch_events=0, commit=0):
	"""Queue a dry run (commit=0) or a real import (commit=1)."""
	_require_permission()
	path = _resolve(file_url)

	frappe.enqueue(
		"avinashgroup_app.avinash_group_app.page.print_count_import."
		"print_count_import_api.execute",
		queue="long",
		timeout=3600,
		user=frappe.session.user,
		xls_path=path,
		mode=mode,
		only_prefix=only_prefix or None,
		drop_batch_events=cint(drop_batch_events),
		commit=cint(commit),
	)
	return {"queued": True, "file": os.path.basename(path)}


def execute(xls_path, mode, only_prefix, drop_batch_events, commit, user):
	"""Background job. Publishes the summary, or the error, back to the page."""
	try:
		result = run(
			xls_path=xls_path,
			commit=bool(commit),
			only_prefix=only_prefix,
			drop_batch_events=bool(drop_batch_events),
			mode=mode,
		)
		result["file"] = os.path.basename(xls_path)
		payload = {"ok": True, "result": result}
	except Exception:
		frappe.db.rollback()
		frappe.log_error(
			title=f"Print count import failed for {os.path.basename(xls_path)}",
			message=frappe.get_traceback(),
		)
		payload = {"ok": False, "error": frappe.get_traceback(with_context=False)}

	frappe.publish_realtime(EVENT, payload, user=user)


@frappe.whitelist()
def summary():
	"""Current totals, so the page can show the effect of an import."""
	frappe.has_permission("Sales Invoice Print Count", "read", throw=True)
	row = frappe.db.sql(
		"SELECT COUNT(*) AS counters, IFNULL(SUM(print_count), 0) AS sheets "
		"FROM `tabSales Invoice Print Count`",
		as_dict=True,
	)[0]
	return row
