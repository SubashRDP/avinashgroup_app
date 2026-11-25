// Letter of Credit list: status colours.
frappe.listview_settings["Letter of Credit"] = {
	add_fields: ["status", "expiry_date"],
	get_indicator(doc) {
		const colour = {
			Draft: "red", Open: "blue", "In Transit": "orange", Arrived: "yellow",
			Transferred: "green", Closed: "gray", Cancelled: "red",
		}[doc.status] || "gray";
		return [__(doc.status), colour, `status,=,${doc.status}`];
	},
};
