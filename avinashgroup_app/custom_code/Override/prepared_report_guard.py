"""Keep the ledger reports interactive.

Frappe starts a 15-second timer on every Script Report run
(Report.execute_script_report, report.py:163) and, if the run is still going
when it fires, permanently sets prepared_report on that Report. From then on
the report serves a CACHED result and never runs live again -- and nothing
turns the flag back off.

That is a poor fit for these ledgers. They run in about five seconds warm, but
a cold first run on an unwarmed buffer pool can cross fifteen, and once it does
the report silently stops responding to its own filters: unticking a checkbox
appears to do nothing because the page is showing an older run. That has been
mistaken for broken filters more than once.

So the auto-enable is skipped for these reports specifically. Every other
report keeps the protection. An operator can still set prepared_report by hand
on the Report doc if one of these genuinely needs to go async.
"""

import frappe

KEEP_INTERACTIVE = {
	"Custom Ledger",
	"General Ledger Posting Detail",
	"TDS Party Ledger Summary",
}


def patch_keep_reports_interactive():
	"""Skip Frappe's automatic prepared_report flip for the ledger reports."""
	from frappe.core.doctype.report import report as report_module

	if getattr(report_module, "_avinashgroup_prepared_guard", False):
		return

	original = report_module.enable_prepared_report

	def enable_prepared_report(report: str, site: str):
		if report in KEEP_INTERACTIVE:
			return
		return original(report, site)

	# execute_script_report hands this module global to threading.Timer, and
	# Python resolves it when the timer is built -- so replacing it here is
	# enough; the report doctype needs no edit.
	report_module.enable_prepared_report = enable_prepared_report
	report_module._avinashgroup_prepared_guard = True
