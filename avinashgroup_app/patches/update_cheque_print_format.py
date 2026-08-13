import frappe


OLD = '{%- set _payee = doc.party_name or doc.party or "" -%}'
NEW = '{%- set _payee = doc.custom_paid_to_from or doc.party_name or doc.party or "" -%}'


def _update_print_format(name: str) -> None:
	doc = frappe.get_doc("Print Format", name)
	if not doc.html or OLD not in doc.html:
		return

	doc.html = doc.html.replace(OLD, NEW)
	doc.save(ignore_permissions=True)


def execute():
	for name in (
		"Canon Payment Entry Cheque Print",
		"Brother Payment Entry Cheque Print",
	):
		_update_print_format(name)

