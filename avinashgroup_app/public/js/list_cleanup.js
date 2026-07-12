// Default the list sidebar ("Filter By" panel) to hidden for every list view.
// This seeds frappe's own show_sidebar preference, so it stays fully
// toggleable: the header sidebar button shows/hides it on the current page,
// and "Toggle Sidebar" (Ctrl+K) in the list menu flips the saved preference
// back on permanently. Only seeds when unset, so a user's own choice is
// never overwritten.
if (localStorage.getItem("show_sidebar") === null) {
	localStorage.setItem("show_sidebar", "false");
}

// Remove the trailing "ID" column that frappe force-appends to every list
// whose title_field differs from name (list_view.js setup_columns). It sits
// outside the user-configurable column list, so List View Settings can never
// remove it; the only switch is the hide_name_column listview setting.
// Default it to true for all doctypes, applied lazily at read time so it
// also covers doctype_list_js settings that load after this file. A doctype
// can still opt out by explicitly setting hide_name_column: false.
frappe.provide("frappe.listview_settings");
frappe.listview_settings = new Proxy(frappe.listview_settings, {
	get(target, doctype) {
		if (typeof doctype !== "string") {
			return target[doctype];
		}
		let settings = target[doctype];
		if (!settings) {
			settings = target[doctype] = {};
		}
		if (settings.hide_name_column === undefined) {
			settings.hide_name_column = true;
		}
		return settings;
	},
});
