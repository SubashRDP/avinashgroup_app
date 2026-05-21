"""
Add fiscal year access custom fields to User doctype
"""
import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

def execute():
	custom_fields = {
		"User": [
			{
				"fieldname": "fiscal_year_section",
				"fieldtype": "Section Break",
				"label": "Fiscal Year Data Access",
				"insert_after": "user_type",
				"idx": 100,
			},
			{
				"fieldname": "full_access",
				"fieldtype": "Check",
				"label": "Full Access (All Data)",
				"insert_after": "fiscal_year_section",
				"description": "When checked, user can access all transactions across all fiscal years. When unchecked, access is restricted based on specific fiscal year assignments below.",
				"default": 0,
				"idx": 101,
			},
			{
				"fieldname": "user_fiscal_years",
				"fieldtype": "Table",
				"label": "Fiscal Year Access",
				"options": "User Fiscal Year Access",
				"insert_after": "full_access",
				"description": "Specify which doctypes and fiscal years this user can access. If 'Full Access (All Fiscal Years)' is checked for a row, user can see all fiscal years for that doctype.",
				"idx": 102,
			},
		]
	}
	create_custom_fields(custom_fields)
	frappe.db.commit()
