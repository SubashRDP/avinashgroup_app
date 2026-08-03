// Copyright (c) 2026, Raindrop and contributors
// For license information, please see license.txt

frappe.listview_settings["Sales Invoice Print Count"] = {
	onload(listview) {
		if (!frappe.model.can_create("Sales Invoice Print Count")) return;

		listview.page.add_inner_button(__("Import from Register"), () =>
			frappe.set_route("print-count-import")
		);
	},
};
