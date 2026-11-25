"""LC Cost Type — the kinds of cost an import LC collects (commission, SWIFT,
marine insurance, import duty, ICP booking, freight to the border...).

A master rather than a fixed list so accounts can add the odd charge a bank or
agent invents without a code change. The group decides where the cost shows on
the cost sheet; group VAT books the amount to input VAT instead of the cost.
The default set is seeded by lc/install.py (DEFAULT_COST_TYPES).
"""

from frappe.model.document import Document


class LCCostType(Document):
	pass
