"""Miti (BS) fields filled on the server, for every document a Bs Conversion record covers.

rdp_common_app's **Bs Conversion** records say, per doctype, which AD date
field has a BS twin (Journal Entry: posting_date → custom_posting_miti,
cheque_date → custom_reference_miti; Sales Invoice: posting_date →
custom_invoice_miti; …). Its desk script, nepali_date_trigger.js, applies them
only in the browser, as a user picks a date. A document made anywhere else —
a cheque bounce entry, a Payroll Entry's journal, an import, the API, a
scheduled job — was saved with its mitis blank.

`set_mitis` runs on every validate (hooks: `"*"`) and does what the desk does,
server-side, through the app's exact converter (`utils/bs_converter.py`,
nepali_datetime — no time-of-day anchor):

* AD date set → miti written from it. AD is authoritative, so a miti can never
  disagree with the date it mirrors.
* AD date empty, miti set → AD date written from the miti (imports that carry
  only the Nepali date), as the desk's initial populate does.

Rows switched off (`enabled` unticked) are skipped.

Cheap on doctypes it does not cover: the doctype → fields map is cached and
cleared whenever a Bs Conversion record changes (`clear_cache`).

A mirror, so it never blocks a save: a date it cannot convert is left as it is
and logged with the document name.
"""

import frappe
from frappe.utils import getdate

from avinashgroup_app.utils.bs_converter import english_to_nepali_converter, nepali_to_english_converter

CACHE_KEY = "avinashgroup_bs_miti_fields"


def _mappings():
	"""{doctype: [(ad_field, miti_field), ...]} from the Bs Conversion records."""
	cached = frappe.cache.get_value(CACHE_KEY)
	if cached is not None:
		return cached
	out = {}
	if frappe.db.table_exists("Bs Conversion") and frappe.db.table_exists("AD BS Conversion Item"):
		for doctype, ad_field, miti_field in frappe.db.sql(
			"""select b.doctype_names, i.ad_date, i.bs_date
			from `tabBs Conversion` b join `tabAD BS Conversion Item` i on i.parent = b.name
			where b.docstatus < 2 and i.enabled = 1
				and ifnull(b.doctype_names, '') != '' and ifnull(i.ad_date, '') != '' and ifnull(i.bs_date, '') != ''"""
		):
			out.setdefault(doctype, []).append((ad_field, miti_field))
	frappe.cache.set_value(CACHE_KEY, out)
	return out


def clear_cache(doc=None, method=None):
	"""Hook on Bs Conversion: a changed record takes effect on the next save."""
	frappe.cache.delete_value(CACHE_KEY)


def ad_to_miti(value):
	"""'2083-07-11' for an AD date; None outside the BS calendar.

	nepali_datetime covers roughly 1913-2043 AD, and real data holds
	placeholders (birth dates of 1900-01-01). Such a date simply has no miti.
	"""
	d = getdate(value)
	try:
		return english_to_nepali_converter(d.year, d.month, d.day)
	except (OverflowError, ValueError):
		return None


def miti_to_ad(value):
	"""AD date string for a miti like '2083-07-11' (a time part, if any, ignored)."""
	year, month, day = (int(x) for x in str(value).strip()[:10].split("-"))
	return nepali_to_english_converter(year, month, day)


def set_mitis(doc, method=None):
	"""Fill the doc's miti fields from its AD dates (or the reverse). Never raises."""
	fields = _mappings().get(doc.doctype)
	if not fields:
		return
	meta = frappe.get_meta(doc.doctype)
	for ad_field, miti_field in fields:
		if not (meta.has_field(ad_field) and meta.has_field(miti_field)):
			continue
		try:
			if doc.get(ad_field):
				miti = ad_to_miti(doc.get(ad_field))
				if miti:
					doc.set(miti_field, miti)
			elif doc.get(miti_field):
				doc.set(ad_field, miti_to_ad(doc.get(miti_field)))
		except Exception:
			frappe.log_error(
				title=f"Miti conversion failed: {doc.doctype}.{ad_field}",
				message=f"{doc.name or '(new)'}: {ad_field}={doc.get(ad_field)!r} {miti_field}={doc.get(miti_field)!r}\n"
				+ frappe.get_traceback(),
			)
