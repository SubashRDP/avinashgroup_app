frappe.ui.form.on("Attendance Fix", {
	refresh(frm) {
		// Restrict the Devices picker to enabled biometric devices.
		// Wrapped defensively because the Table MultiSelect set_query API
		// has been inconsistent across Frappe versions; if it errors here
		// we'd rather show all devices than crash the whole form render.
		try {
			frm.set_query("devices", () => ({
				filters: { enabled: 1 },
			}));
		} catch (e) {
			// eslint-disable-next-line no-console
			console.warn("Attendance Fix: could not filter device picker", e);
		}

		if (frm.doc.docstatus === 1) {
			if (frm.doc.status === "Queued" || frm.doc.status === "Running") {
				frm.dashboard.set_headline_alert(
					`Reconciliation is ${frm.doc.status.toLowerCase()} in the background worker. ` +
					`This page won't auto-refresh — reload to see progress.`,
					"orange",
				);
			} else if (frm.doc.status === "Fixed") {
				frm.dashboard.set_headline_alert(
					`Fixed: ${frm.doc.attendance_created_or_updated} attendance row(s), ` +
					`${frm.doc.checkins_relinked} checkin(s) relinked, ` +
					`${frm.doc.absent_rows_deleted} stale Absent row(s) deleted.`,
					"green",
				);
			} else if (frm.doc.status === "Failed") {
				frm.dashboard.set_headline_alert(
					`Reconciliation failed — see the Log field for the traceback.`,
					"red",
				);
			}
		}
	},
});
