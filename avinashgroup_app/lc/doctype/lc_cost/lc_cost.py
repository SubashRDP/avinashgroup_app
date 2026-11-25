"""LC Cost — one cost booked on a Letter of Credit, with the Journal Entry it posted.

Rows are added only by lc/lifecycle.py (Add Cost, Pay Goods, Accept Bill); the
form never edits them. A usance acceptance row also carries its maturity
payment once the bank pays.
"""

from frappe.model.document import Document


class LCCost(Document):
	pass
