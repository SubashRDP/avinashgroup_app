import frappe
import erpnext.regional

# Preserve the original ERPNext guard so non-authorized users keep the exact
# core behavior (incl. any future ERPNext changes to it).
_original_check_deletion_permission = erpnext.regional.check_deletion_permission


# Roles allowed to delete submitted/cancelled transactions for Nepal-country
# companies. Administrator always carries "System Manager", so this covers it.
AUTHORIZED_ROLES = {"System Manager"}


def check_deletion_permission(doc, method):
	# The patch lives on the shared erpnext.regional module, so it is in effect
	# for every site a worker process serves. Scope the bypass to sites where
	# avinashgroup_app is actually installed (get_installed_apps is per-site),
	# so other sites on the same bench keep ERPNext's stock behavior.
	if "avinashgroup_app" in frappe.get_installed_apps():
		# Authorized roles may delete submitted/cancelled transactions for
		# Nepal-country companies; everyone else keeps the original restriction.
		if frappe.session.user == "Administrator" or AUTHORIZED_ROLES & set(frappe.get_roles()):
			return
	return _original_check_deletion_permission(doc, method)


def apply_patch():
	erpnext.regional.check_deletion_permission = check_deletion_permission
