"""Keeps the Vehicle List (custom_sub_type_list) of vehicle accounts filled.

An Account ticked "Is Vehicle Account" (custom_is_vehicle_account) gets the
vehicles of its own company in its Sub type list:

- New Vehicle created: it is added to every ticked account of the same company.
- Account ticked (new account, or an old one ticked now): all vehicles of its
  company that are not in its list yet are added once.

Add-only: rows already in the list are never removed or changed, and unticking
an account leaves its list as it is.

The same vehicle cannot be in one account's list twice; an Account save with a
repeated vehicle is stopped.
"""

import frappe

TICK_FIELD = "custom_is_vehicle_account"
VEHICLE_TABLE = "custom_sub_type_list"


def add_vehicle_to_accounts(doc, method=None):
	"""Vehicle after_insert (hooks.py): add the new vehicle to the Sub type list
	of every ticked account of the vehicle's company."""
	company = doc.get("custom_company")
	if not company or not frappe.get_meta("Account").has_field(TICK_FIELD):
		return

	account_names = frappe.get_all(
		"Account",
		filters={TICK_FIELD: 1, "company": company},
		pluck="name",
	)

	for account_name in account_names:
		try:
			account = frappe.get_doc("Account", account_name)
			if doc.name in _vehicles_in_list(account):
				continue
			account.append(VEHICLE_TABLE, {"vehicle_list": doc.name})
			account.save(ignore_permissions=True)
		except Exception:
			# The vehicle still saves; the failed account is logged and shown.
			frappe.log_error(
				title=f"Vehicle {doc.name} not added to account {account_name}",
				message=frappe.get_traceback(),
			)
			frappe.msgprint(
				f"Vehicle {doc.name} could not be added to account {account_name}. "
				"See Error Log.",
				indicator="orange",
			)


def fill_vehicles_when_ticked(doc, method=None):
	"""Account validate (hooks.py): when "Is Vehicle Account" gets ticked, add
	all vehicles of the account's company that are not in its list yet."""
	if not doc.get(TICK_FIELD) or not doc.has_value_changed(TICK_FIELD):
		return

	company_vehicles = frappe.get_all(
		"Vehicle",
		filters={"custom_company": doc.company},
		pluck="name",
		order_by="creation asc",
	)

	already_in_list = _vehicles_in_list(doc)
	for vehicle in company_vehicles:
		if vehicle not in already_in_list:
			doc.append(VEHICLE_TABLE, {"vehicle_list": vehicle})


def block_duplicate_vehicles(doc, method=None):
	"""Account validate (hooks.py): stop the save when the same vehicle is in
	the Sub type list more than once."""
	seen = {}
	duplicates = []
	for row in doc.get(VEHICLE_TABLE) or []:
		if not row.vehicle_list:
			continue
		if row.vehicle_list in seen:
			duplicates.append(
				f"Row #{row.idx}: Vehicle {frappe.bold(row.vehicle_list)} "
				f"is already in Row #{seen[row.vehicle_list]}"
			)
		else:
			seen[row.vehicle_list] = row.idx

	if duplicates:
		frappe.throw("<br>".join(duplicates), title="Duplicate Vehicle")


def _vehicles_in_list(account):
	return {row.vehicle_list for row in account.get(VEHICLE_TABLE) or []}
