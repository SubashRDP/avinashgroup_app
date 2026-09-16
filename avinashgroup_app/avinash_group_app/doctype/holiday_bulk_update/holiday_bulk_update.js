// Holiday Bulk Update — Apply button, and the removal dropdown.
// Removal options come from the server (holiday_bulk_update.py ->
// avinashgroup_app.hr.holiday_lists), so they always reflect the chosen lists.
frappe.ui.form.on("Holiday Bulk Update", {
	refresh(frm) {
		frm.trigger("load_removable_holidays");
		if (frm.is_new()) return;

		frm.add_custom_button(__("Apply"), () => {
			const where = frm.doc.all_holiday_lists
				? __("all holiday lists")
				: __("{0} list(s)", [(frm.doc.holiday_lists || []).length]);
			const what =
				frm.doc.action === "Remove Holiday" ? frm.doc.existing_holiday : frm.doc.holiday_date;

			frappe.confirm(__("{0} {1} on {2}?", [__(frm.doc.action), what, where]), () => {
				frm.call({
					doc: frm.doc,
					method: "apply",
					freeze: true,
					freeze_message: __("Updating Holiday Lists..."),
					callback: (r) => {
						if (!r.message) return;
						const { changed, skipped } = r.message;
						let msg = "";
						if (changed.length)
							msg += `<b>${__("Updated")} (${changed.length})</b><br>${changed.join("<br>")}<br><br>`;
						if (skipped.length)
							msg += `<b>${__("Skipped")} (${skipped.length})</b><br>${skipped.join("<br>")}`;
						frappe.msgprint({
							title: __("Holiday Lists Updated"),
							message: msg || __("Nothing to do"),
							indicator: changed.length ? "green" : "orange",
						});
						frm.reload_doc();
					},
				});
			});
		}).addClass("btn-primary");
	},

	// The list selection decides which holidays can be removed, so reload on any
	// change to it as well as on the action itself.
	action: (frm) => frm.trigger("load_removable_holidays"),
	all_holiday_lists: (frm) => frm.trigger("load_removable_holidays"),
	holiday_lists: (frm) => frm.trigger("load_removable_holidays"),

	load_removable_holidays(frm) {
		if (frm.doc.action !== "Remove Holiday" || frm.is_new()) return;

		frm.call({ doc: frm.doc, method: "removable_holidays" }).then((r) => {
			const options = r.message || [];
			frm.set_df_property("existing_holiday", "options", [""].concat(options).join("\n"));
			if (frm.doc.existing_holiday && !options.includes(frm.doc.existing_holiday))
				frm.set_value("existing_holiday", "");
			frm.refresh_field("existing_holiday");
		});
	},
});
