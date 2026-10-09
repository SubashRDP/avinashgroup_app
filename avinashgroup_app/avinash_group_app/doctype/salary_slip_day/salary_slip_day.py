from frappe.model.document import Document


class SalarySlipDay(Document):
	"""One day (or month-end line) of a salary slip's daily breakdown: see payroll/daily_breakdown.py."""
