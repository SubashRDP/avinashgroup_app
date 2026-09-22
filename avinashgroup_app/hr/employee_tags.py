"""An employee's allowance group must belong to their own company.

The tea and meal rates are per company — NGI pays 235 a day where NGN pays 265
— so an Allowance Category from the wrong company quietly pays the wrong money.
Nothing stopped it: the link field offered every company's groups, and an
import or an API call never sees the form's filter at all.
"""

import frappe
from frappe import _


def validate_allowance_category(doc, method=None):
	if not doc.get("custom_allowance_category"):
		return

	owner_company = frappe.db.get_value(
		"Allowance Category", doc.custom_allowance_category, "company"
	)
	if owner_company and owner_company != doc.company:
		frappe.throw(
			_("{0} belongs to {1}, but {2} works for {3}. Pick one of {3}'s allowance categories.").format(
				frappe.bold(doc.custom_allowance_category),
				frappe.bold(owner_company),
				frappe.bold(doc.employee_name or doc.name),
				frappe.bold(doc.company),
			),
			title=_("Allowance category from another company"),
		)
