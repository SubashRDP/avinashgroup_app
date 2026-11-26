const SETTINGS_METHODS =
	"avinashgroup_app.avinash_group_app.doctype.bulk_reconciliation_settings.bulk_reconciliation_settings";

frappe.ui.form.on("Bulk Reconciliation Settings", {
	refresh(frm) {
		frm.set_intro("");

		if (frm.doc.is_stopped) {
			frm.set_intro(
				__("Stopped: no reconciliation runs (scheduled, queued or running) until you press Resume."),
				"red"
			);
			frm.add_custom_button(__("Resume"), () => {
				frappe.confirm(__("Start all reconciliation again?"), () =>
					call_and_reload(frm, "resume_auto_run")
				);
			}).addClass("btn-primary");
			return;
		}

		if (frm.doc.enabled) {
			frm.set_intro(__("Running: reconciliation runs automatically on schedule."), "green");
		}
		frm.add_custom_button(__("Stop"), () => {
			frappe.confirm(
				__(
					"Stop all reconciliation? The scheduled job stops, Queued entries wait, and Running entries are paused after their current batch."
				),
				() => call_and_reload(frm, "stop_auto_run")
			);
		}).addClass("btn-danger");
	},
});

function call_and_reload(frm, method) {
	frappe.call({
		method: `${SETTINGS_METHODS}.${method}`,
		freeze: true,
		callback: (r) => {
			if (r.message) {
				frappe.msgprint(r.message);
			}
			frm.reload_doc();
		},
	});
}
