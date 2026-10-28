// Letter of Credit list: status colours.
frappe.listview_settings["Letter of Credit"] = {
	add_fields: ["status", "expiry_date"],
	get_indicator(doc) {
		const colour = {
			Draft: "red", Applied: "orange", Opened: "blue", "Partly Settled": "yellow",
			Settled: "green", Closed: "gray", Expired: "gray", Cancelled: "red",
		}[doc.status] || "gray";
		return [__(doc.status), colour, `status,=,${doc.status}`];
	},
};
