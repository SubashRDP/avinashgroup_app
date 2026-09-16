import frappe


OLD = '{%- set _payee = doc.party_name or doc.party or "" -%}'
NEW = '{%- set _payee = doc.custom_paid_to_from or doc.party_name or doc.party or "" -%}'


def _update_print_format(name: str) -> None:
	if not frappe.db.exists("Print Format", name):
		return

	doc = frappe.get_doc("Print Format", name)
	if not doc.html or OLD not in doc.html:
		return

	doc.html = doc.html.replace(OLD, NEW)
	doc.save(ignore_permissions=True)


def execute():
	for name in (
		"NG Cheque Print Canon",
		"NG Cheque Print Brother",
	):
		_update_print_format(name)

