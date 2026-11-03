// Salary Assignment Upload — download the sheet, fill it in Excel, attach it.
// Reading the file and checking each row happen on the server when the form
// saves (salary_assignment_upload.py), so a row marked Ready will submit.
frappe.ui.form.on("Salary Assignment Upload", {
	setup(frm) {
		frm.set_query("salary_structure", () => ({
			filters: { company: frm.doc.company, docstatus: 1 },
		}));
		frm.set_query("salary_structure", "employees", () => ({
			filters: { company: frm.doc.company, docstatus: 1 },
		}));
	},

	onload(frm) {
		if (frm.is_new() && !frm.doc.company) {
			frm.set_value("company", frappe.defaults.get_user_default("Company"));
		}
	},

	refresh(frm) {
		frm.set_df_property("employees", "cannot_add_rows", true);
		if (frm.doc.docstatus === 0 && frm.doc.upload_file && !frm.is_new()) {
			frm.add_custom_button(__("Read File Again"), () =>
				frm.call("read_file_again").then(() => frm.reload_doc())
			);
		}
		if (frm.doc.error_count) {
			frm.dashboard.set_headline(
				__("{0} row(s) marked Error — see the Message column, fix them in the file and attach it again.", [
					frm.doc.error_count,
				]),
				"red"
			);
		}
	},

	download_template(frm) {
		if (!frm.doc.company || !frm.doc.from_date) {
			frappe.msgprint(__("Pick the Company and From Date first"));
			return;
		}
		const args = { company: frm.doc.company, from_date: frm.doc.from_date };
		if (frm.doc.salary_structure) args.salary_structure = frm.doc.salary_structure;
		window.open(
			"/api/method/avinashgroup_app.avinash_group_app.doctype.salary_assignment_upload.salary_assignment_upload.download_template?" +
				new URLSearchParams(args).toString()
		);
	},

	upload_file(frm) {
		if (frm.doc.upload_file) frm.save();
	},
});
