"""LC guards — stop a document the LC posted being cancelled from its own form.

Each Journal Entry and Stock Entry a Letter of Credit posts is part of the LC's
cost file: cancelling one from the JE or Stock Entry form would leave the LC's
totals, its History and LC Goods in Transit disagreeing. Both are refused here;
the LC's Undo Last Step is the way to unwind (it sets INTERNAL_CANCEL_FLAG).

Validation hooks: these throw, by design. Called from hooks.py doc_events
(before_cancel on Journal Entry and Stock Entry).
"""

import frappe
from frappe import _

from avinashgroup_app.lc.accounting import INTERNAL_CANCEL_FLAG


def block_cancel(doc, method=None):
	if doc.get("letter_of_credit") and not frappe.flags.get(INTERNAL_CANCEL_FLAG):
		frappe.throw(
			_("This entry belongs to Letter of Credit {0}. Use Undo Last Step on the LC.").format(doc.letter_of_credit),
			title=_("Posted by an LC"),
		)
