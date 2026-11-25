"""LC becomes a standalone cost file: drop the Purchase-Order era doctypes and fields.

The first LC module (Oct 2026) hung an LC off Purchase Orders and settled
Purchase Invoices, with shipment, charge, amendment, document and PO child
tables and a Landed Cost Voucher link. The Nov 2026 redesign keeps every cost
of the import in LC Goods in Transit and transfers it to stock or assets
itself (lc/README.md). This patch:

* deletes the five child doctypes that no longer exist in code (their tables go
  with them) and the Landed Cost Voucher-letter_of_credit Custom Field;
* carries each company's old "LC Charges Clearing" account over as its
  "LC Goods in Transit" account (the column was renamed charges_account →
  transit_account), and fills the Input VAT account where it can;
* maps the old statuses of submitted LCs onto the new ones.

Safe to rerun: each step only acts on what is still there.
"""

import frappe

OLD_CHILD_DOCTYPES = ("LC Shipment", "LC Charge", "LC Amendment", "LC Document", "LC Purchase Order")
OLD_STATUS = {"Applied": "Open", "Opened": "Open", "Partly Settled": "Open", "Settled": "Open", "Expired": "Closed"}


def execute():
	for doctype in OLD_CHILD_DOCTYPES:
		if frappe.db.exists("DocType", doctype):
			frappe.delete_doc("DocType", doctype, force=True, ignore_permissions=True)
	if frappe.db.exists("Custom Field", "Landed Cost Voucher-letter_of_credit"):
		frappe.delete_doc("Custom Field", "Landed Cost Voucher-letter_of_credit", force=True, ignore_permissions=True)

	if frappe.db.has_column("LC Company Account", "charges_account"):
		frappe.db.sql(
			"""update `tabLC Company Account` set transit_account = charges_account
			where ifnull(transit_account, '') = '' and ifnull(charges_account, '') != ''"""
		)
	from avinashgroup_app.lc.install import default_vat_account

	for row in frappe.get_all("LC Company Account", filters={"vat_account": ["is", "not set"]}, fields=["name", "company"]):
		account = default_vat_account(row.company)
		if account:
			frappe.db.set_value("LC Company Account", row.name, "vat_account", account, update_modified=False)
	frappe.clear_document_cache("LC Settings", "LC Settings")

	for old, new in OLD_STATUS.items():
		frappe.db.sql("update `tabLetter of Credit` set status = %s where status = %s and docstatus = 1", (new, old))
