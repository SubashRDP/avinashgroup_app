frappe.ui.form.on("Attendance", {
	refresh(frm) {
		render_checkin_log(frm);
	},
	employee(frm) {
		render_checkin_log(frm);
	},
	attendance_date(frm) {
		render_checkin_log(frm);
	},
});

function render_checkin_log(frm) {
	console.log("[avinashgroup_app] render_checkin_log fired", {
		name: frm.doc.name,
		employee: frm.doc.employee,
		attendance_date: frm.doc.attendance_date,
	});

	const wrapper_id = "nepal-hrms-checkin-log";
	const anchor =
		frm.fields_dict.status?.$wrapper ||
		frm.fields_dict.attendance_date?.$wrapper ||
		$(frm.layout.wrapper);
	console.log("[avinashgroup_app] anchor element:", anchor[0], "visible:", anchor.is(":visible"));
	anchor.find("#" + wrapper_id).remove();

	if (!frm.doc.employee || !frm.doc.attendance_date) {
		console.log("[avinashgroup_app] early return — missing employee or attendance_date");
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
			console.log("[avinashgroup_app] checkin rows returned:", rows);
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
