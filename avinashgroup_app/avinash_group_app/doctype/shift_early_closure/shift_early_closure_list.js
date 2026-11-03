// Shift Early Closure list: "Close Many Days" opens the month sheet
// (public/js/shift_early_closure_sheet.js) — every day of a month, or an Excel import.
frappe.listview_settings["Shift Early Closure"] = {
	onload(listview) {
		if (!frappe.user.has_role(["HR Manager", "System Manager"])) return;
		listview.page.add_inner_button(__("Close Many Days"), () =>
			avinash.open_closure_sheet({ on_done: () => listview.refresh() })
		);
	},
};
