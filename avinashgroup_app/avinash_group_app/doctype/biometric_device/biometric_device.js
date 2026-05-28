// Copyright (c) 2026, Dikshya and contributors
// For license information, please see license.txt

frappe.ui.form.on("Biometric Device", {
	refresh: function (frm) {
		if (!frm.is_new()) {
			add_custom_buttons(frm);
		}
	},
});

function add_custom_buttons(frm) {
	frm.add_custom_button(__("Force Bridge Sync"), function () {
		force_bridge_sync(frm);
	}).addClass("btn-primary");
}

function force_bridge_sync(frm) {
	if (!frm.doc.device_serial) {
		frappe.msgprint(__("This device has no Device Serial set. Bridges identify themselves by serial."));
		return;
	}

	frappe.confirm(
		__("Queue a Force-Sync command for the bridge serving '{0}'? The bridge will pick it up on its next poll (~30 seconds).", [frm.doc.device_name]),
		function () {
			frappe.call({
				method: "avinashgroup_app.biometric.bridge_commands.enqueue_command",
				args: { device: frm.doc.name, command_type: "force_sync" },
				freeze: true,
				freeze_message: __("Queuing command..."),
				callback: function (r) {
					if (!r.message) return;
					const cmd_name = r.message;
					frappe.show_alert({
						message: __("Queued {0} — waiting for bridge…", [cmd_name]),
						indicator: "blue",
					});
					_poll_command_status(cmd_name, frm);
				},
			});
		}
	);
}

function _poll_command_status(cmd_name, frm) {
	// Poll every 3s up to 90s total.
	const max_polls = 30;
	let polls = 0;

	const tick = () => {
		polls += 1;
		frappe.db
			.get_value("Biometric Device Command", cmd_name, [
				"status",
				"result",
				"attempts",
				"completed_at",
			])
			.then((r) => {
				if (!r || !r.message) return;
				const m = r.message;
				if (m.status === "Done" || m.status === "Failed") {
					frappe.msgprint({
						title: __("Bridge command {0}", [m.status]),
						message:
							`<b>Command:</b> ${cmd_name}<br>` +
							`<b>Status:</b> ${m.status}<br>` +
							`<b>Bridge polls:</b> ${m.attempts || 0}<br>` +
							`<b>Completed at:</b> ${m.completed_at || "—"}<br><br>` +
							`<b>Result:</b><pre style="white-space:pre-wrap">${frappe.utils.escape_html(m.result || "(empty)")}</pre>`,
						indicator: m.status === "Done" ? "green" : "red",
						wide: true,
					});
					return;
				}
				if (polls >= max_polls) {
					frappe.msgprint({
						title: __("Bridge command still pending"),
						message: __(
							"Command {0} is still {1} after ~90 seconds. The bridge may be offline. Open the Biometric Device Command record to follow up.",
							[cmd_name, m.status]
						),
						indicator: "orange",
					});
					return;
				}
				setTimeout(tick, 3000);
			});
	};

	setTimeout(tick, 3000);
}
