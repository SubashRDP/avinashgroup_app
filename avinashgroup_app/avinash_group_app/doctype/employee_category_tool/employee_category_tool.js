// Employee Category Tool — the same filter group and checkbox grid as the HRMS
// Shift Assignment Tool, built from the shared hrms.* helpers so the two behave
// alike. Server side: employee_category_tool.py.
frappe.ui.form.on("Employee Category Tool", {
	setup(frm) {
		hrms.setup_employee_filter_group(frm);
	},

	refresh(frm) {
		frm.page.clear_indicator();
		frm.disable_save();
		frm.trigger("set_primary_action");
		frm.trigger("get_employees");
	},

	employee_category: (frm) => frm.trigger("get_employees"),
	company: (frm) => frm.trigger("get_employees"),
	only_uncategorised: (frm) => frm.trigger("get_employees"),
	branch: (frm) => frm.trigger("get_employees"),
	department: (frm) => frm.trigger("get_employees"),
	designation: (frm) => frm.trigger("get_employees"),
	current_category: (frm) => frm.trigger("get_employees"),

	set_primary_action(frm) {
		frm.page.set_primary_action(__("Assign Category"), () => frm.trigger("assign"));
	},

	get_employees(frm) {
		if (!frm.doc.employee_category) {
			return hrms.render_employees_datatable(
				frm,
				frm.events.columns(),
				[],
				__("Choose the category to assign."),
			);
		}

		frm.call({
			method: "get_employees",
			args: { advanced_filters: frm.advanced_filters || [] },
			doc: frm.doc,
		}).then((r) =>
			hrms.render_employees_datatable(
				frm,
				frm.events.columns(),
				r.message || [],
				__("Everyone matching these filters is already in this category."),
			),
		);
	},

	columns() {
		return [
			{ id: "employee", name: "employee", content: __("Employee") },
			{ id: "employee_name", name: "employee_name", content: __("Employee Name") },
			{ id: "company", name: "company", content: __("Company") },
			{ id: "designation", name: "designation", content: __("Designation") },
			{
				id: "custom_employee_category",
				name: "custom_employee_category",
				content: __("Current Category"),
			},
		].map((c) => ({ ...c, editable: false, focusable: false, dropdown: false, align: "left" }));
	},

	assign(frm) {
		const rows = frm.employees_datatable.datamanager.data;
		const selected = frm.employees_datatable.rowmanager
			.getCheckedRows()
			.map((idx) => rows[idx].employee);

		hrms.validate_mandatory_fields(frm, selected);
		frappe.confirm(
			__("Put {0} employee(s) in {1}?", [selected.length, frm.doc.employee_category.bold()]),
			() =>
				frm
					.call({
						method: "bulk_assign",
						doc: frm.doc,
						args: { employees: selected },
						freeze: true,
						freeze_message: __("Assigning category"),
					})
					.then(() => frm.trigger("get_employees")),
		);
	},
});
