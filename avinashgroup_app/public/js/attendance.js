frappe.ui.form.on("Attendance", {
	refresh(frm) {
		render_checkin_log(frm);
		add_repair_button(frm);
	},
	employee(frm) {
		render_checkin_log(frm);
	},
	attendance_date(frm) {
		render_checkin_log(frm);
	},
});

function render_checkin_log(frm) {
	const wrapper_id = "nepal-hrms-checkin-log";
	const anchor =
		frm.fields_dict.status?.$wrapper ||
		frm.fields_dict.attendance_date?.$wrapper ||
		$(frm.layout.wrapper);
	anchor.find("#" + wrapper_id).remove();

	if (!frm.doc.employee || !frm.doc.attendance_date) {
		return;
	}

	const date = frm.doc.attendance_date;
	frappe.db
		.get_list("Employee Checkin", {
			filters: {
				employee: frm.doc.employee,
				time: ["between", [date + " 00:00:00", date + " 23:59:59"]],
			},
			fields: ["name", "log_type", "time"],
			order_by: "time asc",
			limit: 0,
		})
		.then((rows) => {
			const $container = $(
				`<div id="${wrapper_id}" style="margin-top:12px"></div>`
			).appendTo(anchor);
			// Ensure container is visible even if parent wrapper is collapsed.
			$container.css("display", "block");

			if (!rows || !rows.length) {
				$container.html(
					`<div class="text-muted">${__("No Employee Checkin records for this date.")}</div>`
				);
				return;
			}

			const header = `
				<div style="font-weight:600;margin-bottom:6px">${__("Checkin Log")}</div>
				<table class="table table-bordered" style="margin-bottom:0">
					<thead>
						<tr>
							<th style="width:40%">${__("Status")}</th>
							<th>${__("Time")}</th>
						</tr>
					</thead>
					<tbody>
			`;

			const body = rows
				.map((r) => {
					const status = r.log_type === "IN" ? __("Checkin") : __("Checkout");
					const color = r.log_type === "IN" ? "green" : "orange";
					const time = frappe.datetime.str_to_user(r.time);
					const link = `/app/employee-checkin/${encodeURIComponent(r.name)}`;
					return `
						<tr>
							<td><span class="indicator ${color}">${status}</span></td>
							<td><a href="${link}">${frappe.utils.escape_html(time)}</a></td>
						</tr>
					`;
				})
				.join("");

			$container.html(header + body + "</tbody></table>");
		});
}


// Rebuild this one day's attendance from its check-ins. The single-record
// counterpart to Attendance Fix, which does the same thing for a date range.
function add_repair_button(frm) {
	if (frm.is_new() || !frm.doc.employee || !frm.doc.attendance_date) return;
	if (frm.doc.docstatus === 2) return;

	frm.add_custom_button(__("Repair from Check-ins"), () => {
		frappe.confirm(
			__(
				"Rebuild attendance for {0} on {1} from the day's check-ins?<br><br>" +
					"Working hours, in/out and the late/early fields are recomputed. " +
					"A stale <b>Absent</b> row with punches against it is replaced.",
				[frm.doc.employee_name || frm.doc.employee, frappe.datetime.str_to_user(frm.doc.attendance_date)]
			),
			() => run_repair(frm)
		);
	});
}

function run_repair(frm) {
	frappe.call({
		method: "avinashgroup_app.avinash_group_app.doctype.attendance_fix.attendance_fix.repair_attendance_day",
		args: { employee: frm.doc.employee, attendance_date: frm.doc.attendance_date },
		freeze: true,
		freeze_message: __("Rebuilding from check-ins…"),
		callback: (r) => {
			const res = r.message;
			if (!res) return;

			if (!res.changed) {
				frappe.show_alert({
					message: __("Already correct — nothing to change."),
					indicator: "green",
				});
				return;
			}

			const c = res.counters;
			const lines = [
				`<b>${__("Shift")}:</b> ${frappe.utils.escape_html(res.shift)}`,
				res.before
					? `<b>${__("Before")}:</b> ${res.before.status} · ${res.before.working_hours || 0}h`
					: `<b>${__("Before")}:</b> ${__("no attendance row")}`,
				res.after
					? `<b>${__("After")}:</b> ${res.after.status} · ${res.after.working_hours || 0}h`
					: `<b>${__("After")}:</b> ${__("no attendance row")}`,
			];
			if (c.checkins_relinked) lines.push(__("{0} check-in(s) relinked", [c.checkins_relinked]));
			if (c.absent_rows_deleted) lines.push(__("stale Absent row replaced"));

			frappe.msgprint({
				title: __("Attendance repaired"),
				indicator: "green",
				message: lines.join("<br>") +
					(res.log && res.log.length
						? `<pre style="margin-top:10px;white-space:pre-wrap">${frappe.utils.escape_html(
								res.log.join("\n")
						  )}</pre>`
						: ""),
			});

			// A replaced Absent means this document no longer exists.
			if (res.replaced && res.after) {
				frappe.set_route("Form", "Attendance", res.after.name);
			} else {
				frm.reload_doc();
			}
		},
	});
}
