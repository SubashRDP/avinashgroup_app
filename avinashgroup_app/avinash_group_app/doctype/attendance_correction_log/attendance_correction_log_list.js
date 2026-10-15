frappe.listview_settings["Attendance Correction Log"] = {
	get_indicator(doc) {
		const tones = {
			"Punch Time Edited": "orange",
			"Punch Added": "blue",
			"Punch Deleted": "red",
			"Shift Changed": "purple",
			"Re-marked": "gray",
			"Replacement Leave": "green",
			"Leave Given": "cyan",
		};
		return [__(doc.correction_type), tones[doc.correction_type] || "gray", `correction_type,=,${doc.correction_type}`];
	},
};
