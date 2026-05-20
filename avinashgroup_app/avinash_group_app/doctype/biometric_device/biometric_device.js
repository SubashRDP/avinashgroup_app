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
	frm.add_custom_button(__("Test Connection"), function () {
		test_connection(frm);
	}).addClass("btn-primary");

	frm.add_custom_button(
		__("Sync Attendance"),
		function () {
			sync_attendance(frm);
		},
		__("Actions")
	);

	frm.add_custom_button(
		__("Sync Employees"),
		function () {
			sync_employees(frm);
		},
		__("Actions")
	);

	frm.add_custom_button(
		__("Get Device Info"),
		function () {
			get_device_info(frm);
		},
		__("Actions")
	);

	frm.add_custom_button(
		__("Get Device Users"),
		function () {
			get_device_users(frm);
		},
		__("Actions")
	);

	// frm.add_custom_button(
	// 	__("Clear Device Logs"),
	// 	function () {
	// 		// clear_device_logs(frm);
	// 	},
	// 	__("Actions")
	// );
}

function test_connection(frm) {
	if (!frm.doc.device_ip) {
		frappe.msgprint(__("Please enter Device IP"));
		return;
	}

	frappe.call({
		method: "avinashgroup_app.biometric.api.test_connection",
		args: {
			device_ip: frm.doc.device_ip,
			device_port: frm.doc.device_port || 4370,
		},
		freeze: true,
		freeze_message: __("Testing connection..."),
		callback: function (r) {
			if (r.message && r.message.success) {
				frappe.show_alert(
					{ message: __("Connection successful!"), indicator: "green" },
					5
				);

				frm.set_value("connection_status", "Connected");

				let msg = `<b>Connection Successful!</b><br><br>`;
				msg += `<b>Firmware:</b> ${r.message.firmware || "N/A"}<br>`;
				msg += `<b>Serial Number:</b> ${r.message.serial || "N/A"}<br>`;
				msg += `<b>Users on Device:</b> ${r.message.user_count || 0}<br>`;

				frappe.msgprint({
					title: __("Device Connected"),
					message: msg,
					indicator: "green",
				});

				frm.save();
			} else {
				frappe.show_alert(
					{ message: __("Connection failed!"), indicator: "red" },
					5
				);

				frm.set_value("connection_status", "Disconnected");

				frappe.msgprint({
					title: __("Connection Failed"),
					message:
						r.message.message || "Unable to connect to device",
					indicator: "red",
				});

				frm.save();
			}
		},
		error: function () {
			frappe.show_alert(
				{ message: __("Connection failed!"), indicator: "red" },
				5
			);
			frm.set_value("connection_status", "Disconnected");
			frm.save();
		},
	});
}

function sync_attendance(frm) {
	if (!frm.doc.device_ip) {
		frappe.msgprint(__("Please enter Device IP"));
		return;
	}

	frappe.confirm(
		__(
			"This will sync all attendance records from the device. Continue?"
		),
		function () {
			frappe.call({
				method: "avinashgroup_app.biometric.api.sync_attendance_from_device",
				args: {
					device_ip: frm.doc.device_ip,
					device_port: frm.doc.device_port || 4370,
				},
				freeze: true,
				freeze_message: __("Syncing attendance from device..."),
				callback: function (r) {
					if (r.message && r.message.success) {
						frappe.show_alert(
							{
								message: __(
									"Attendance synced successfully!"
								),
								indicator: "green",
							},
							5
						);

						frm.set_value(
							"last_sync_time",
							frappe.datetime.now_datetime()
						);
						let total =
							(frm.doc.total_synced || 0) + r.message.synced;
						frm.set_value("total_synced", total);

						let msg = `<b>Sync Complete!</b><br><br>`;
						msg += `<b>Records Synced:</b> ${r.message.synced}<br>`;
						msg += `<b>Errors:</b> ${r.message.errors}<br>`;

						if (
							r.message.error_details &&
							r.message.error_details.length > 0
						) {
							msg += `<br><b>Error Details:</b><br>`;
							r.message.error_details.forEach(function (err) {
								msg += `- ${err}<br>`;
							});
						}

						frappe.msgprint({
							title: __("Attendance Sync Results"),
							message: msg,
							indicator:
								r.message.errors > 0 ? "orange" : "green",
						});

						frm.save();
					} else {
						frappe.msgprint({
							title: __("Sync Failed"),
							message:
								r.message.message ||
								"Failed to sync attendance",
							indicator: "red",
						});
					}
				},
			});
		}
	);
}

function sync_employees(frm) {
	if (!frm.doc.device_ip) {
		frappe.msgprint(__("Please enter Device IP"));
		return;
	}

	frappe.confirm(
		__(
			"This will sync all active employees with Device IDs to the device. Continue?"
		),
		function () {
			frappe.call({
				method: "avinashgroup_app.biometric.api.sync_employees_to_device",
				args: {
					device_ip: frm.doc.device_ip,
					device_port: frm.doc.device_port || 4370,
				},
				freeze: true,
				freeze_message: __("Syncing employees to device..."),
				callback: function (r) {
					if (r.message && r.message.success) {
						frappe.show_alert(
							{
								message: __(
									"Employees synced successfully!"
								),
								indicator: "green",
							},
							5
						);

						frm.set_value(
							"last_employee_sync",
							frappe.datetime.now_datetime()
						);
						frm.set_value(
							"total_employees_synced",
							r.message.synced
						);

						let msg = `<b>Sync Complete!</b><br><br>`;
						msg += `<b>Employees Synced:</b> ${r.message.synced}<br>`;
						msg += `<b>Errors:</b> ${r.message.errors}<br>`;

						if (
							r.message.error_details &&
							r.message.error_details.length > 0
						) {
							msg += `<br><b>Error Details:</b><br>`;
							r.message.error_details.forEach(function (err) {
								msg += `- ${err}<br>`;
							});
						}

						frappe.msgprint({
							title: __("Employee Sync Results"),
							message: msg,
							indicator:
								r.message.errors > 0 ? "orange" : "green",
						});

						frm.save();
					} else {
						frappe.msgprint({
							title: __("Sync Failed"),
							message:
								r.message.message ||
								"Failed to sync employees",
							indicator: "red",
						});
					}
				},
			});
		}
	);
}

function clear_device_logs(frm) {
	if (!frm.doc.device_ip) {
		frappe.msgprint(__("Please enter Device IP"));
		return;
	}

	frappe.confirm(
		__(
			"This will permanently clear all attendance logs from the device. This cannot be undone. Continue?"
		),
		function () {
			frappe.call({
				method: "avinashgroup_app.biometric.api.clear_device_logs",
				args: {
					device_ip: frm.doc.device_ip,
					device_port: frm.doc.device_port || 4370,
				},
				freeze: true,
				freeze_message: __("Clearing device logs..."),
				callback: function (r) {
					if (r.message && r.message.success) {
						frappe.show_alert(
							{
								message: __(
									"Device logs cleared successfully!"
								),
								indicator: "green",
							},
							5
						);

						frappe.msgprint({
							title: __("Success"),
							message: __(
								"All attendance logs have been cleared from the device."
							),
							indicator: "green",
						});
					}
				},
			});
		}
	);
}

function get_device_users(frm) {
	if (!frm.doc.device_ip) {
		frappe.msgprint(__("Please enter Device IP"));
		return;
	}

	frappe.call({
		method: "avinashgroup_app.biometric.api.get_device_users",
		args: {
			device_ip: frm.doc.device_ip,
			device_port: frm.doc.device_port || 4370,
		},
		freeze: true,
		freeze_message: __("Getting device users..."),
		callback: function (r) {
			if (r.message && r.message.success) {
				let msg = `<b>Total Users: ${r.message.count}</b><br><br>`;

				if (r.message.count > 0) {
					msg += `<table class="table table-bordered table-sm">`;
					msg += `<thead><tr><th>UID</th><th>Name</th><th>User ID</th><th>Privilege</th></tr></thead>`;
					msg += `<tbody>`;

					r.message.users.forEach(function (user) {
						let privilege =
							user.privilege == 14 ? "Admin" : "User";
						msg += `<tr>`;
						msg += `<td>${user.uid}</td>`;
						msg += `<td>${user.name}</td>`;
						msg += `<td>${user.user_id}</td>`;
						msg += `<td>${privilege}</td>`;
						msg += `</tr>`;
					});

					msg += `</tbody></table>`;
				} else {
					msg += `<p>No users found on device.</p>`;
				}

				frappe.msgprint({
					title: __("Device Users"),
					message: msg,
					wide: true,
				});
			}
		},
	});
}

function get_device_info(frm) {
	if (!frm.doc.device_ip) {
		frappe.msgprint(__("Please enter Device IP"));
		return;
	}

	frappe.call({
		method: "avinashgroup_app.biometric.api.get_device_info",
		args: {
			device_ip: frm.doc.device_ip,
			device_port: frm.doc.device_port || 4370,
		},
		freeze: true,
		freeze_message: __("Getting device information..."),
		callback: function (r) {
			if (r.message && r.message.success) {
				let info = r.message.info;

				let msg = `<table class="table table-bordered">`;
				msg += `<tr><td><b>Firmware Version:</b></td><td>${info.firmware || "N/A"}</td></tr>`;
				msg += `<tr><td><b>Serial Number:</b></td><td>${info.serialnumber || "N/A"}</td></tr>`;
				msg += `<tr><td><b>Platform:</b></td><td>${info.platform || "N/A"}</td></tr>`;
				msg += `<tr><td><b>Device Name:</b></td><td>${info.device_name || "N/A"}</td></tr>`;
				msg += `<tr><td><b>Face Version:</b></td><td>${info.face_version || "N/A"}</td></tr>`;
				msg += `<tr><td><b>Fingerprint Version:</b></td><td>${info.fp_version || "N/A"}</td></tr>`;
				msg += `<tr><td><b>Users on Device:</b></td><td>${info.user_count || 0}</td></tr>`;
				msg += `<tr><td><b>Attendance Records:</b></td><td>${info.attendance_count || 0}</td></tr>`;
				msg += `</table>`;

				frappe.msgprint({
					title: __("Device Information"),
					message: msg,
					wide: true,
				});
			} else {
				frappe.msgprint({
					title: __("Failed"),
					message:
						r.message.message || "Could not get device info",
					indicator: "red",
				});
			}
		},
	});
}
