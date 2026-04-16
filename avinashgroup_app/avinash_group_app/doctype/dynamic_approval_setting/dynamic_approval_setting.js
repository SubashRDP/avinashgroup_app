frappe.ui.form.on("Dynamic Approval Setting", {
	refresh(frm) {
		render_department_ui(frm);

		if (!frm.is_new()) {
			frm.add_custom_button(__("Setup Workflow"), () => {
				frappe.confirm(
					__("This will create/update the workflow and custom fields on <b>{0}</b>. Continue?", [frm.doc.document_type]),
					() => {
						frappe.call({
							method: "avinashgroup_app.custom_code.dynamic_approval.setup_workflow",
							args: { config_name: frm.doc.name },
							freeze: true,
							freeze_message: __("Setting up workflow..."),
							callback(r) {
								if (!r.exc) {
									frappe.msgprint({
										title: __("Success"), indicator: "green",
										message: __("Workflow setup complete for {0}.", [frm.doc.document_type])
									});
								}
							}
						});
					}
				);
			}).addClass("btn-primary");
		}
	}
});

/* ───────────────────────────────────────────────
   Render the Department-wise UI into the
   dedicated "dept_config_html" HTML field.
   ─────────────────────────────────────────────── */
function render_department_ui(frm) {
    // Use the dedicated HTML field — Frappe guarantees this exists
    let html_field = frm.fields_dict.dept_config_html;
    if (!html_field || !html_field.$wrapper) return;

    let approvers = frm.doc.approvers || [];

    // Group rows by department
    let depts = {};
    approvers.forEach(row => {
        let d = row.department || "__global__";
        if (!depts[d]) depts[d] = [];
        depts[d].push(row);
    });

    let dept_keys = Object.keys(depts);

    // Build the HTML
    let cards = "";
    dept_keys.forEach(d => {
        let display_name = d === "__global__" ? "Global (All Departments)" : d;
        let badges = depts[d].map(r =>
            `<span style="display:inline-block;background:#f4f5f6;border:1px solid #d1d8dd;border-radius:4px;padding:2px 8px;margin:2px 2px;font-size:12px;">${frappe.utils.escape_html(r.approver_name || r.approver)}</span>`
        ).join(' <span style="color:#aaa;font-size:10px;">➔</span> ');

        cards += `
        <div style="border:1px solid #d1d8dd;border-radius:6px;padding:12px 16px;margin-bottom:8px;background:#fff;display:flex;justify-content:space-between;align-items:center;">
            <div>
                <div style="font-weight:600;font-size:14px;margin-bottom:4px;">${frappe.utils.escape_html(display_name)}</div>
                <div style="font-size:12px;color:#6c757d;">
                    ${badges || '<span style="color:#999;">No approvers configured</span>'}
                </div>
            </div>
            <div style="display:flex;gap:6px;">
                <button class="btn btn-xs btn-default btn-dept-edit" data-dept="${frappe.utils.escape_html(d)}">
                    <svg class="icon icon-sm"><use href="#icon-edit"></use></svg> Edit
                </button>
                <button class="btn btn-xs btn-danger btn-dept-delete" data-dept="${frappe.utils.escape_html(d)}">
                    <svg class="icon icon-sm"><use href="#icon-delete"></use></svg>
                </button>
            </div>
        </div>`;
    });

    if (!dept_keys.length) {
        cards = '<div style="color:#999;padding:12px;text-align:center;">No department sequences configured yet.</div>';
    }

    let full_html = `
    <div style="margin-bottom:10px;">
        <p class="text-muted" style="font-size:12px;margin-bottom:10px;">
            Define fixed approvers per department. Leave Department blank for a global (fallback) sequence.
        </p>
        ${cards}
        <button class="btn btn-xs btn-primary btn-add-dept-seq" style="margin-top:6px;">
            + Add Department Sequence
        </button>
    </div>`;

    html_field.$wrapper.html(full_html);

    // Bind events
    html_field.$wrapper.find(".btn-add-dept-seq").on("click", function(e) {
        e.preventDefault();
        open_dept_dialog(frm, null, true);
    });

    html_field.$wrapper.find(".btn-dept-edit").on("click", function(e) {
        e.preventDefault();
        let dept = $(this).attr("data-dept");
        if (dept === "__global__") dept = "";
        open_dept_dialog(frm, dept, false);
    });

    html_field.$wrapper.find(".btn-dept-delete").on("click", function(e) {
        e.preventDefault();
        let dept = $(this).attr("data-dept");
        let dept_label = dept === "__global__" ? "Global" : dept;
        frappe.confirm(
            __("Remove all approvers for <b>{0}</b>?", [dept_label]),
            () => {
                let real_dept = dept === "__global__" ? "" : dept;
                let remaining = (frm.doc.approvers || []).filter(r => (r.department || "") !== real_dept);
                frm.clear_table("approvers");
                remaining.forEach(data => {
                    let child = frm.add_child("approvers");
                    child.department = data.department;
                    child.approver = data.approver;
                    child.approver_name = data.approver_name;
                });
                frm.refresh_field("approvers");
                frm.dirty();
                render_department_ui(frm);
            }
        );
    });
}

/* ───────────────────────────────────────────────
   Dialog for adding / editing a department's
   approver sequence.
   ─────────────────────────────────────────────── */
function open_dept_dialog(frm, target_dept, is_new) {
    let d = new frappe.ui.Dialog({
        title: is_new ? "Add Department Sequence" : "Edit Approver Sequence",
        size: "large",
        fields: [
            {
                fieldname: "department",
                label: "Department",
                fieldtype: "Link",
                options: "Department",
                description: "Leave blank for a global (fallback) sequence that applies to all departments.",
                default: is_new ? "" : target_dept
            },
            { fieldtype: "Section Break" },
            {
                fieldname: "approvers_section",
                fieldtype: "Table",
                label: "Approvers (in order)",
                cannot_add_rows: false,
                in_place_edit: true,
                data: [],
                fields: [
                    {
                        fieldname: "approver",
                        label: "Approver",
                        fieldtype: "Link",
                        options: "User",
                        in_list_view: 1,
                        reqd: 1,
                        columns: 5
                    },
                    {
                        fieldname: "approver_name",
                        label: "Full Name",
                        fieldtype: "Data",
                        in_list_view: 1,
                        read_only: 1,
                        columns: 5
                    }
                ]
            }
        ],
        primary_action_label: is_new ? "Add Sequence" : "Update Sequence",
        primary_action(values) {
            let dept = values.department || "";
            let new_approvers = (values.approvers_section || []).filter(r => r.approver);

            if (!new_approvers.length) {
                frappe.msgprint(__("Please add at least one approver."));
                return;
            }

            // Keep rows from OTHER departments
            let keep = (frm.doc.approvers || [])
                .filter(r => (r.department || "") !== (target_dept || ""))
                .map(r => ({ department: r.department, approver: r.approver, approver_name: r.approver_name }));

            // Merge
            frm.clear_table("approvers");
            [...keep, ...new_approvers.map(r => ({ department: dept, approver: r.approver, approver_name: r.approver_name }))].forEach(data => {
                let child = frm.add_child("approvers");
                child.department = data.department;
                child.approver = data.approver;
                child.approver_name = data.approver_name;
            });

            frm.refresh_field("approvers");
            frm.dirty();
            d.hide();
            render_department_ui(frm);
        }
    });

    d.show();

    // If editing, populate existing rows after the dialog grid is ready
    if (!is_new) {
        let existing = (frm.doc.approvers || []).filter(r => (r.department || "") === (target_dept || ""));
        if (existing.length && d.fields_dict.approvers_section) {
            let grid = d.fields_dict.approvers_section;
            existing.forEach(r => {
                let row_data = { approver: r.approver, approver_name: r.approver_name };
                grid.df.data.push(row_data);
            });
            grid.grid.refresh();
        }
    }
}
