// Copyright (c) 2026, Raindrop and contributors
// For license information, please see license.txt

frappe.listview_settings["Sparrow SMS Log"] = {
	add_fields: ["status"],
	get_indicator: function (doc) {
		const map = {
			Sent: ["Sent", "green", "status,=,Sent"],
			Failed: ["Failed", "red", "status,=,Failed"],
			Queued: ["Queued", "orange", "status,=,Queued"],
		};
		return map[doc.status] || [__(doc.status), "gray", `status,=,${doc.status}`];
	},
};
