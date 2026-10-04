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
		frm.add_custom_button(__("Move Staff to This Shift"), () => {
			if (!frm.doc.custom_company) {
				frappe.msgprint(__("Set the Company on this Shift Type first — staff rotate within one company."));
				return;
			}
			open_rotation_dialog(frm.doc.custom_company, frm.doc.name);
		});
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
				onchange: () => {
					sync_miti_from_date(dialog);
					load_candidates(dialog);
				},
			},
			{
				fieldname: "from_miti",
				fieldtype: "Data",
				label: __("From Date (BS)"),
				description: __("Nepali date, YYYY-MM-DD. Pick here or in From Date; each fills the other"),
			},
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
					args: { company: dialog.__company, to_shift: values.to_shift, from_date: values.from_date, employees: picked },
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

	// Kept on the dialog, not read back from its Company field: a Link field's
	// default is set asynchronously, so the field is still blank on the first
	// load and the server was asked with no company at all.
	dialog.__company = company;
	dialog.show();
	attach_miti_picker(dialog);
	load_candidates(dialog);
}

// ── Nepali (BS) date beside the AD date ─────────────────────────────────────
// Conversion both ways is the Nepali datepicker library rdp_common_app already
// loads on every desk page (window.NepaliFunctions) — the same one behind the BS
// fields on the forms and reports. If it has not loaded, the field falls back to
// the server's reading of the date and stays read-only.
const BS_FORMAT = "YYYY-MM-DD";

function nepali_dates() {
	return window.NepaliFunctions;
}

function sync_miti_from_date(dialog) {
	const ad = dialog.get_value("from_date");
	if (!nepali_dates() || !ad) return;
	const bs = nepali_dates().AD2BS(ad, BS_FORMAT);
	if (bs && dialog.get_value("from_miti") !== bs) dialog.set_value("from_miti", bs);
}

function sync_date_from_miti(dialog, bs) {
	bs = (bs || "").trim();
	if (!nepali_dates() || !/^\d{4}-\d{1,2}-\d{1,2}$/.test(bs)) return;
	// The library does not refuse an impossible date — 2083-13-40 quietly becomes
	// some day the following year — so the answer is converted back and compared.
	let ad = null;
	try {
		ad = nepali_dates().BS2AD(bs, BS_FORMAT);
	} catch (e) {
		ad = null;
	}
	const [y, m, d] = bs.split("-").map(Number);
	const back = ad ? nepali_dates().AD2BS(ad, BS_FORMAT).split("-").map(Number) : [];
	if (back[0] !== y || back[1] !== m || back[2] !== d) {
		frappe.show_alert({ message: __("{0} is not a Nepali date", [bs]), indicator: "red" });
		return;
	}
	// Setting From Date reloads the list through its own onchange.
	if (ad && dialog.get_value("from_date") !== ad) dialog.set_value("from_date", ad);
}

function attach_miti_picker(dialog) {
	const field = dialog.fields_dict.from_miti;
	if (!nepali_dates()) {
		dialog.set_df_property("from_miti", "read_only", 1);
		return;
	}
	const $input = field.$input;
	if (typeof $input.nepaliDatePicker === "function") {
		// The calendar is drawn on <body> at z-index 1000, under a Bootstrap modal.
		if (!document.getElementById("shift-rotation-ndp-style")) {
			$('<style id="shift-rotation-ndp-style">.ndp-container{z-index:1100}</style>').appendTo("head");
		}
		$input.nepaliDatePicker({
			ndpYear: true,
			ndpMonth: true,
			dateFormat: BS_FORMAT,
			closeOnDateSelect: true,
			onChange: (picked) => sync_date_from_miti(dialog, (picked && picked.bs) || $input.val()),
		});
	}
	// Typed by hand, or a picker build that does not call onChange.
	$input.on("change blur", () => sync_date_from_miti(dialog, $input.val()));
}

// Fill the date (first day of the next BS month when blank), the shift choices
// and the candidate list from the server.
function load_candidates(dialog, force) {
	const args = {
		company: dialog.__company,
		to_shift: dialog.get_value("to_shift") || dialog.fields_dict.to_shift.df.default,
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
		if (!args.from_date) dialog.set_value("from_date", r.from_date);
		if (nepali_dates()) {
			dialog.set_value("from_miti", nepali_dates().AD2BS(r.from_date, BS_FORMAT));
			// The same date in words, so the month is read rather than counted.
			dialog.set_df_property("from_miti", "description", r.from_miti);
		} else {
			dialog.set_value("from_miti", r.from_miti);
		}

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
