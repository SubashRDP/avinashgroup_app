"""Give the Journal Entries ERPNext makes for assets a JV Type, so they can be numbered.

Every Journal Entry on this site must carry a JV Type (``custom_p_type``) and a
document number (``custom_document_no``), both mandatory Custom Fields. The
number comes from the app's Numbering Configuration, keyed on the JV Type
(see lc/accounting.py, which hit the same wall).

ERPNext builds several Journal Entries itself and knows nothing of either field:

- the yearly depreciation entry (``voucher_type = "Depreciation Entry"``),
  posted by the daily ``post_depreciation_entries`` job on each Asar end;
- the scrap entry from Asset -> Manage -> Scrap Asset;
- asset value adjustments.

Without a JV Type the insert fails with ``MandatoryError: custom_p_type,
custom_document_no``. For the scheduled job that means depreciation silently
never posts (found by the fixed-asset test run on demo-nggroup, 2026-11-05).

``set_jv_type`` (Journal Entry ``before_insert``, first in the chain like the
payroll one) hands those entries to ``payroll.hr_journal.fill_system_journal``,
which already does this for HRMS's journals: JV Type "Journal Entry" (ERPNext's
"Depreciation Entry" voucher type is not a JV Type here), and because that
series is numbered by hand on every company, the next number in it.

Deliberately narrow: a JE someone typed is never touched, and anything already
set on an asset entry is kept.
"""

from avinashgroup_app.payroll.hr_journal import fill_system_journal

DEPRECIATION_VOUCHER_TYPE = "Depreciation Entry"  # set by erpnext.assets...depreciation


def is_asset_entry(je) -> bool:
	"""True for an entry ERPNext built for an asset (depreciation, scrap, value adjustment)."""
	return je.voucher_type == DEPRECIATION_VOUCHER_TYPE or any(
		row.reference_type == "Asset" for row in je.get("accounts") or []
	)


def set_jv_type(doc, method=None):
	"""Journal Entry before_insert: JV Type and Document No for asset entries."""
	if is_asset_entry(doc):
		fill_system_journal(doc)
