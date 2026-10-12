from frappe.model.document import Document


class AssignmentAllowance(Document):
	"""One allowance a person gets on their Salary Structure Assignment, at their Rate. No row, not paid: see payroll/allowance.py."""
