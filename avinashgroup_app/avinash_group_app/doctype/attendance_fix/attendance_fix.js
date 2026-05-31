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
