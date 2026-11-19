// Copyright (c) 2026, Raindrop and contributors
// For license information, please see license.txt

frappe.listview_settings["Memo Log"] = {
	onload(listview) {
		listview.page.add_inner_button(__("Memo Generator"), () => frappe.set_route("memo-generator"));
	},
};
