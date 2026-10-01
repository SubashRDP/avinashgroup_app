// Shift Type — "Move Staff to This Shift" on a rotational shift.
//
// Staff rotate month by month between the shifts ticked "Takes Part in Rotation"
// (NGI: 6 AM - 2 PM and 12 PM - 8 PM). HR opens the shift people are moving ONTO,
// picks the date it starts and ticks who moves; everybody ticked gets the new
// shift from that date, open-ended, until they are moved again.
//
// This script only asks and shows. Who may move, onto what, and what happens to
// the assignments and to attendance already marked is decided server-side in
// avinashgroup_app.hr.shift_rotation — a shift missing from the dropdown here is
// also refused there.
const SHIFT_ROTATION = "avinashgroup_app.hr.shift_rotation";

frappe.ui.form.on("Shift Type", {
	refresh(frm) {
		if (frm.is_new() || !frm.doc.custom_in_rotation) return;
		frm.add_custom_button(__("Move Staff to This Shift"), () =>
			open_rotation_dialog(frm.doc.custom_company, frm.doc.name),
		);
	},
});

function open_rotation_dialog(company, to_shift) {
	const dialog = new frappe.ui.Dialog({
		title: __("Move Staff to Another Shift"),
		size: "extra-large",
		fields: [
			{ fieldname: "company", fieldtype: "Link", options: "Company", label: __("Company"), default: company, read_only: 1 },
			{
				fieldname: "to_shift",
				fieldtype: "Select",
				label: __("New Shift"),
				reqd: 1,
				default: to_shift,
				options: [to_shift],
				description: __("Only shifts ticked Takes Part in Rotation, of this company"),
				onchange: () => load_candidates(dialog),
			},
			{ fieldtype: "Column Break" },
			{
				fieldname: "from_date",
				fieldtype: "Date",
				label: __("From Date"),
				reqd: 1,
				description: __("The first day on the new shift. It runs on until the person is moved again"),
				onchange: () => load_candidates(dialog),
			},
			{ fieldname: "from_miti", fieldtype: "Data", label: __("From Date (BS)"), read_only: 1 },
			{ fieldtype: "Section Break", label: __("Tick who moves") },
			{
				fieldname: "employees",
				fieldtype: "Table",
				label: __("Staff on the other rotational shifts"),
				cannot_add_rows: true,
				cannot_delete_rows: true,
				in_place_edit: true,
				data: [],
				fields: [
					{ fieldname: "employee", fieldtype: "Data", label: __("Employee"), in_list_view: 1, read_only: 1, columns: 2 },
					{ fieldname: "employee_name", fieldtype: "Data", label: __("Name"), in_list_view: 1, read_only: 1, columns: 3 },
					{ fieldname: "department", fieldtype: "Data", label: __("Department"), in_list_view: 1, read_only: 1, columns: 2 },
					{ fieldname: "from_shift", fieldtype: "Data", label: __("Shift on That Date"), in_list_view: 1, read_only: 1, columns: 3 },
				],
			},
		],
		primary_action_label: __("Move"),
		primary_action(values) {
			const picked = dialog.fields_dict.employees.grid.get_selected_children().map((row) => row.employee);
			if (!picked.length) {
				frappe.msgprint(__("Tick at least one employee to move."));
				return;
			}
			frappe
				.call({
					method: `${SHIFT_ROTATION}.rotate`,
					args: { company: values.company, to_shift: values.to_shift, from_date: values.from_date, employees: picked },
					freeze: true,
					freeze_message: __("Moving {0} employee(s)", [picked.length]),
				})
				.then(({ message: result }) => {
					if (!result) return;
					show_rotation_result(result, values);
					// Keep the dialog open when somebody was refused, so the rest of
					// the list is still there to act on; the moved ones drop out of it.
					if (result.refused.length) load_candidates(dialog, true);
					else dialog.hide();
				});
		},
	});

	dialog.show();
	load_candidates(dialog);
}

// Fill the date (first day of the next BS month when blank), the shift choices
// and the candidate list from the server.
function load_candidates(dialog, force) {
	const args = {
		company: dialog.get_value("company"),
		to_shift: dialog.get_value("to_shift"),
		from_date: dialog.get_value("from_date") || null,
	};
	// Setting the date below fires onchange again; the same question is not asked twice.
	const asked = JSON.stringify(args);
	if (!force && asked === dialog.__asked) return;
	dialog.__asked = asked;

	frappe.call(`${SHIFT_ROTATION}.preview`, args).then(({ message: r }) => {
		// A newer choice is already on its way; this answer is for the old one.
		if (!r || dialog.__asked !== asked) return;
		dialog.__asked = JSON.stringify({ ...args, from_date: r.from_date });

		dialog.set_df_property("to_shift", "options", r.shifts);
		dialog.set_value("from_miti", r.from_miti);
		if (!args.from_date) dialog.set_value("from_date", r.from_date);

		const table = dialog.fields_dict.employees;
		table.df.data = r.employees;
		table.grid.refresh();
	});
}

function show_rotation_result(result, values) {
	const lines = [];
	if (result.moved.length) {
		lines.push(
			`<b>${__("{0} moved to {1} from {2}", [result.moved.length, values.to_shift, frappe.datetime.str_to_user(values.from_date)])}</b>`,
		);
	}
	if (result.refused.length) {
		lines.push(`<b>${__("{0} not moved", [result.refused.length])}</b>`);
		result.refused.forEach((row) => lines.push(frappe.utils.escape_html(row.reason)));
	}
	frappe.msgprint({
		title: __("Shift Rotation"),
		indicator: result.refused.length ? "orange" : "green",
		message: lines.join("<br>"),
	});
}
