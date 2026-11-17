frappe.listview_settings["Customer Portal Access"] = {
	add_fields: ["enabled"],
	get_indicator(doc) {
		return doc.enabled ? [__("Active"), "green", "enabled,=,1"] : [__("Disabled"), "grey", "enabled,=,0"];
	},
};
