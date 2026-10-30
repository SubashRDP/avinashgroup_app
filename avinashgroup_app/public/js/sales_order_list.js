// Sales Order list — show the real status instead of ERPNext's red "Overdue".
//
// ERPNext's sales_order_list.js shows "Overdue" for any order that is not fully
// delivered and whose Delivery Date has passed. That label is not a status: the
// order's status field still says "To Deliver and Bill" (or "To Deliver"), which
// is what the Report view shows. This makes the List view show the same thing.
//
// Only the Overdue case is changed. Every other indicator (Closed, On Hold,
// To Bill, Completed...) still comes from ERPNext's own get_indicator.
//
// Loaded through doctype_list_js in hooks.py, which runs after ERPNext's list script.

const erpnext_so_get_indicator = frappe.listview_settings["Sales Order"].get_indicator;

frappe.listview_settings["Sales Order"].get_indicator = function (doc) {
	const indicator = erpnext_so_get_indicator(doc);
	if (indicator && indicator[0] === __("Overdue")) {
		return [__(doc.status), "orange", "status,=," + doc.status];
	}
	return indicator;
};
