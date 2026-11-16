# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

"""Ageing Report Summary — the Ageing Report added up to one row per party.

Same filters, ranges and "Merged" rule as the Ageing Report (see
ageing_report.py for why Merged exists and how the advance is knocked off the
oldest bills). The rows are built by that report's own functions and only
summed here, so a party's row in the summary always equals that party's total
in the Ageing Report.

Read-only.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt

from avinashgroup_app.avinash_group_app.report.ageing_report.ageing_report import (
	SIDES,
	ZERO,
	_amount_fields,
	_ar_rows,
	_columns,
	_merged,
	_not_merged,
	_ranges,
)


def execute(filters=None):
	filters = frappe._dict(filters or {})
	party_type = filters.get("party_type") if filters.get("party_type") in SIDES else "Customer"
	ranges = _ranges(filters.get("range"))
	merged = cint(filters.get("merged"))

	# The Ageing Report's columns minus the per-bill ones.
	columns = [c for c in _columns(party_type, ranges, merged) if c["fieldname"] not in ("voucher_no", "posting_date")]
	if not filters.get("company"):
		return columns, []

	rows = _ar_rows(filters, party_type, ranges)
	rows = _merged(rows, ranges) if merged else _not_merged(rows, ranges)
	return columns, _by_party(rows, ranges, merged)


def _by_party(rows, ranges, merged):
	"""One row per party (rows arrive grouped by party), then a grand total.

	A party whose amounts all add up to zero is left out.
	"""
	fields = _amount_fields(ranges, merged)
	out, grand = [], {f: 0.0 for f in fields}
	i = 0
	while i < len(rows):
		first = rows[i]
		totals = {f: 0.0 for f in fields}
		while i < len(rows) and rows[i].party == first.party:
			for f in fields:
				totals[f] += flt(rows[i].get(f))
			i += 1
		if all(abs(v) < ZERO for v in totals.values()):
			continue
		for f in fields:
			grand[f] += totals[f]
		out.append(dict(totals, party=first.party, party_name=first.party_name, party_group=first.party_group, party_group_name=first.party_group_name))
	if out:
		out.append(dict(grand, party_name=_("Grand Total"), bold=1, is_total=1))
	return out
