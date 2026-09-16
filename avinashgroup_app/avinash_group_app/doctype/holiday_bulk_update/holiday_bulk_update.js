// Apply button for Holiday Bulk Update. The work happens server-side in
// holiday_bulk_update.py -> avinashgroup_app.hr.holiday_lists.
frappe.ui.form.on("Holiday Bulk Update", {
	refresh(frm) {
		if (frm.is_new()) return;

		frm.add_custom_button(__("Apply"), () => {
			const where = frm.doc.all_companies
				? __("all companies")
				: __("{0} company(s)", [(frm.doc.companies || []).length]);

			frappe.confirm(
				__("{0}: {1} holiday(s) on {2}?", [
					__(frm.doc.action),
					(frm.doc.holidays || []).length,
					where,
				]),
				() => {
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
				}
			);
		}).addClass("btn-primary");
	},
});
