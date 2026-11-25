"""LC Item — one line of the goods an LC buys, and where it goes when it arrives.

Amount is in the LC's currency (qty × rate). On transfer, lc/transfer.py writes
the row's share of the landed cost, the landed rate per unit, and the Stock
Entry or Asset it became.
"""

from frappe.model.document import Document


class LCItem(Document):
	pass
