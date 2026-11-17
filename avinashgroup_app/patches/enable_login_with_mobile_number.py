"""Let portal dealers log in with their mobile number.

Customer Portal Access creates dealer logins keyed by mobile number (most
dealers have no email; the User's email is a placeholder they never see).
Frappe only looks a login up by User.mobile_no when System Settings
"Allow Login using Mobile Number" is on, which it is not by default. Email
login keeps working alongside it.
"""

import frappe


def execute():
	frappe.db.set_single_value("System Settings", "allow_login_using_mobile_number", 1)
