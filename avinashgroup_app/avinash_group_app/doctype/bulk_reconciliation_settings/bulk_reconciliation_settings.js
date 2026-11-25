const SETTINGS_METHODS =
	"avinashgroup_app.avinash_group_app.doctype.bulk_reconciliation_settings.bulk_reconciliation_settings";

frappe.ui.form.on("Bulk Reconciliation Settings", {
	refresh(frm) {
		frm.set_intro("");
		if (!frm.doc.enabled) {
			return;
		}

		if (frm.doc.is_stopped) {
			frm.set_intro(__("Stopped: the scheduled reconciliation will not run until you press Resume."), "red");
			frm.add_custom_button(__("Resume"), () => call_and_reload(frm, "resume_auto_run")).addClass(
				"btn-primary"
			);
		} else {
			frm.set_intro(__("Running: reconciliation runs automatically on schedule."), "green");
			frm.add_custom_button(__("Stop"), () => {
				frappe.confirm(__("Stop the scheduled reconciliation?"), () =>
					call_and_reload(frm, "stop_auto_run")
				);
			}).addClass("btn-danger");
		}
	},
});

function call_and_reload(frm, method) {
	frappe.call({
		method: `${SETTINGS_METHODS}.${method}`,
		freeze: true,
		callback: () => frm.reload_doc(),
	});
}
