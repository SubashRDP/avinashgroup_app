// "+ Add" on a list opens a blank form — list filters no longer leak into it.
//
// Stock Frappe (list_view.js, ListView.make_new_doc) copies every "=" filter
// on the list into the new document: filter Sales Invoice by Customer = ABC,
// press + Add, and the new invoice already says ABC. Clerks here filter to
// LOOK UP a document, not to add to that group, so the next bill was being
// pre-filled with the previous customer and saved against the wrong party.
//
// Applies to every doctype (Report view and Kanban inherit ListView, so they
// are covered too; Ctrl+B goes through the same method). Defaults that do not
// come from the filters — the user's default Company, doctype field defaults,
// User Permissions — still apply, because frappe.new_doc sets those itself.
//
// Patched on the prototype, not listview_settings: ERPNext list scripts
// replace the whole settings object, so a settings hook would be clobbered.
frappe.provide("frappe.views");

if (frappe.views.ListView) {
	frappe.views.ListView.prototype.make_new_doc = function () {
		frappe.new_doc(this.doctype);
	};
}
