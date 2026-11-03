frappe.ui.form.on("Attendance Fix", {
	onload: function (frm) {
		// A new fix defaults to the current BS month.
		if (frm.is_new() && frm.doc.period === "Month" && !(frm.doc.bs_year && frm.doc.bs_month)) {
			set_month_dates(frm);
		}

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
			frm.add_custom_button(__("Add Employees"), () => fill_roster(frm));
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

	period(frm) {
		if (frm.doc.period === "Month") set_month_dates(frm);
	},
	bs_year(frm) {
		if (frm.doc.bs_year && frm.doc.bs_month) set_month_dates(frm);
	},
	bs_month(frm) {
		if (frm.doc.bs_year && frm.doc.bs_month) set_month_dates(frm);
	},
});

// Month mode: fill From/To Date with the BS month's AD span (the server
// recomputes them on save, so these are only for the person to see).
function set_month_dates(frm) {
	frappe.call({
		method: "avinashgroup_app.avinash_group_app.doctype.attendance_fix.attendance_fix.get_bs_month_dates",
		args: { bs_year: frm.doc.bs_year || null, bs_month: frm.doc.bs_month || null },
		callback: (r) => {
			const m = r.message;
			if (!m) return;
			frm.doc.bs_year = m.bs_year;
			frm.doc.bs_month = m.bs_month;
			frm.doc.from_date = m.from_date;
			frm.doc.to_date = m.to_date;
			frm.refresh_fields(["bs_year", "bs_month", "from_date", "to_date"]);
			frm.dirty();
		},
	});
}

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


// Pre-fill the employee table with everyone in the company employed in the
// period (narrowed to the shift, if one is picked), so "Selected Employees"
// can be used as a starting list to trim rather than typed from scratch.
function fill_roster(frm) {
	if (!frm.doc.company || !frm.doc.from_date || !frm.doc.to_date) {
		frappe.msgprint(__("Pick the Company and the period first."));
		return;
	}
	frappe.call({
		method: "avinashgroup_app.avinash_group_app.doctype.attendance_fix.attendance_fix.get_roster",
		args: {
			company: frm.doc.company,
			from_date: frm.doc.from_date,
			to_date: frm.doc.to_date,
			shift_type: frm.doc.shift_type || null,
		},
		freeze: true,
		callback: (r) => {
			const rows = r.message || [];
			if (!rows.length) {
				frappe.msgprint(__("No employees of this company (on this shift) in that period."));
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
