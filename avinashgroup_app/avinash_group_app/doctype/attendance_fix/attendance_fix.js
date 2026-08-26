frappe.ui.form.on("Attendance Fix", {
	onload: function (frm) {
		// Listen for real-time progress updates
		frappe.realtime.on("attendance_fix_progress", (data) => {
			if (data.doc_name === frm.doc.name) {
				frm.set_value("progress_percentage", data.progress);
				frm.set_value("progress_message", data.message);
				frm.refresh_field("progress_percentage");
				frm.refresh_field("progress_message");
			}
		});

		// Auto-refresh periodically when Running
		frm.refresh_interval = setInterval(() => {
			if (frm.doc.status === "Running" && frm.doc.docstatus === 1) {
				frm.reload_doc();
			}
		}, 5000);  // Refresh every 5 seconds
	},

	onunload: function (frm) {
		// Clean up interval when form closes
		if (frm.refresh_interval) {
			clearInterval(frm.refresh_interval);
		}
	},

	refresh(frm) {
		// Restrict the Devices picker to enabled biometric devices.
		try {
			frm.set_query("devices", () => ({
				filters: { enabled: 1 },
			}));
		} catch (e) {
			console.warn("Attendance Fix: could not filter device picker", e);
		}

		// Only offer Active employees, and only of the chosen company.
		frm.set_query("employee", "employees", () => {
			const filters = { status: "Active" };
			if (frm.doc.company) filters.company = frm.doc.company;
			return { filters };
		});

		if (frm.doc.docstatus === 0 && frm.doc.repair_scope === "Selected Employees") {
			frm.add_custom_button(__("Add Everyone on This Shift"), () => fill_from_shift(frm));
		}

		if (frm.doc.docstatus === 1) {
			if (frm.doc.status === "Queued") {
				frm.dashboard.set_headline_alert(
					`⏳ Reconciliation is queued. The background worker will start processing soon.`,
					"orange",
				);
			} else if (frm.doc.status === "Running") {
				// Show progress bar with real-time updates
				_show_progress_bar(frm);
				frm.dashboard.set_headline_alert(
					`🔄 Processing: ${frm.doc.progress_message || "Starting..."}`,
					"orange",
				);
			} else if (frm.doc.status === "Fixed") {
				frm.dashboard.set_headline_alert(
					`✅ Fixed: ${frm.doc.attendance_created_or_updated} attendance row(s), ` +
					`${frm.doc.checkins_relinked} checkin(s) relinked, ` +
					`${frm.doc.absent_rows_deleted} stale Absent row(s) deleted.`,
					"green",
				);
			} else if (frm.doc.status === "Failed") {
				frm.dashboard.set_headline_alert(
					`❌ Reconciliation failed — see the Log field for details.`,
					"red",
				);
			}
		}
	},
});

function _show_progress_bar(frm) {
	// Create progress bar if not already present
	if (!frm.progress_bar_shown) {
		const progress_pct = frm.doc.progress_percentage || 0;
		const html = `
			<div style="margin: 20px 0;">
				<div class="progress" style="height: 30px; background: #f0f0f0; border-radius: 4px; overflow: hidden;">
					<div id="attendance-fix-progress" class="progress-bar progress-bar-striped progress-bar-animated bg-success"
						 role="progressbar" style="width: ${progress_pct}%; transition: width 0.3s ease;">
						<span id="progress-text" style="font-weight: bold; color: white; display: block; text-align: center; line-height: 30px;">
							${progress_pct}%
						</span>
					</div>
				</div>
				<p id="progress-message" style="font-size: 13px; color: #666; margin: 10px 0 0 0;">
					${frm.doc.progress_message || "Processing..."}
				</p>
			</div>
		`;

		const wrapper = frm.form.find(".form-column").first();
		frm.progress_bar = $(html);
		frm.progress_bar.insertAfter(wrapper);
		frm.progress_bar_shown = true;
	} else {
		// Update existing progress bar
		const progress = frm.doc.progress_percentage || 0;
		frm.progress_bar.find("#attendance-fix-progress").css("width", progress + "%");
		frm.progress_bar.find("#progress-text").text(progress + "%");
		frm.progress_bar.find("#progress-message").text(frm.doc.progress_message || "Processing...");
	}
}


// Pre-fill the employee table from the shift roster, so "Selected Employees"
// can be used as a starting list to trim rather than typed from scratch.
function fill_from_shift(frm) {
	if (!frm.doc.shift_type || !frm.doc.from_date) {
		frappe.msgprint(__("Pick a Shift Type and From Date first."));
		return;
	}
	frappe.call({
		method: "avinashgroup_app.avinash_group_app.doctype.attendance_fix.attendance_fix.get_shift_roster",
		args: {
			shift_type: frm.doc.shift_type,
			on_date: frm.doc.from_date,
			company: frm.doc.company || null,
		},
		freeze: true,
		callback: (r) => {
			const rows = r.message || [];
			if (!rows.length) {
				frappe.msgprint(__("No active employees are assigned to this shift on that date."));
				return;
			}
			const existing = new Set((frm.doc.employees || []).map((d) => d.employee));
			let added = 0;
			rows.forEach((e) => {
				if (existing.has(e.name)) return;
				const row = frm.add_child("employees");
				row.employee = e.name;
				row.employee_name = e.employee_name;
				row.department = e.department;
				row.company = e.company;
				added += 1;
			});
			frm.refresh_field("employees");
			frappe.show_alert({
				message: __("Added {0} employee(s). Remove the ones you do not want.", [added]),
				indicator: "green",
			});
		},
	});
}
