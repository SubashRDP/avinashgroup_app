"""Delete the Sales Invoice print formats no company prints with any more.

The group prints sales invoices with eight formats only: Nepal Gas Invoice Overlay /
NG Group Return Half (the four NG companies and Grishma), GLMI Sales / GLMI Return
(Grihalaxmi), Nepal Gas Sales Invoice, and the Aarati and Gita sales / return
formats. The A5 Overlay, Dot Matrix (ESC/P), Pre-Printed, A4, Half A4 and
Grihalaxmi variants were removed from the app together with their templates and
ESC/P builders; deleting their files does not delete the records a site already
has, so this does. Also the desk-made formats left over from trials, and the
Overlay Print Test page those formats were calibrated with.

ERPNext's own Sales Invoice formats (Sales Invoice, Sales Return, Point of Sale…)
are left alone: they belong to ERPNext and come back on migrate.

Idempotent: a name already gone is skipped, so a site restored from an older
backup is cleaned on its next migrate.
"""

import frappe

REMOVED_FROM_APP = (
	"Avinash Invoice A5 Overlay",
	"Avinash Invoice Dot Matrix",
	"Avinash Invoice Pre-Printed",
	"GLMI Sales Test",
	"Gandaki Invoice A5 Overlay",
	"Gandaki Invoice Dot Matrix",
	"Grihalaxmi Invoice A4",
	"Grihalaxmi Invoice A4 Return",
	"Grihalaxmi Invoice Half A4",
	"Grihalaxmi Invoice Half A4 Return",
	"Grishma Invoice A5 Overlay",
	"Grishma Invoice Dot Matrix",
	"Grishma Invoice Pre-Printed",
	"Karnali Invoice A5 Overlay",
	"Karnali Invoice Dot Matrix",
	"Narayani Invoice A5 Overlay",
	"Narayani Invoice Dot Matrix",
	"Nepal Gas Invoice A4",
	"Nepal Gas Invoice A4 Plain Portrait",
	"Nepal Gas Invoice A4 Portrait",
	"Nepal Gas Invoice A4 Proof",
	"Nepal Gas Invoice A5 Overlay",
	"Nepal Gas Invoice A5 Portrait",
	"Nepal Gas Invoice Dot Matrix",
	"Nepal Gas Invoice Half A4",
	"Nepal Gas Invoice Plain Paper",
	"Nepal Gas Invoice Pre-Printed",
	"Nepal Gas Udyog Invoice A5 Overlay",
	"Nepal Gas Udyog Invoice Dot Matrix",
)

# Made on the desk (standard = No), never part of the app.
DESK_MADE = (
	"Avinash Sales invoice",
	"Avinash Sales Return",
	"Avinash Sales/Return Invoice",
	"Avinash Test",
	"Test",
	"GLMI Sales TI and I",
	"Gita Gas Invoice Half A4",
	"Himalayan Petrochemicals Invoice Half A4",
)


def execute():
	for name in REMOVED_FROM_APP + DESK_MADE:
		# Only a Sales Invoice format of that name: "Test" is generic enough to
		# exist for another doctype on some site.
		if frappe.db.get_value("Print Format", name, "doc_type") != "Sales Invoice":
			continue
		frappe.delete_doc("Print Format", name, force=True, ignore_permissions=True)

		# A Customize Form default is plain text, not a link, so nothing else clears it.
		frappe.db.delete("Property Setter", {"property": "default_print_format", "value": name})

	frappe.delete_doc("Page", "overlay-print-test", force=True, ignore_permissions=True, ignore_missing=True)
	frappe.clear_cache(doctype="Print Format")
