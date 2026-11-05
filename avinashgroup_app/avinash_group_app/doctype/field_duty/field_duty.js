// Field Duty: rows by hand, or from an Excel sheet (hr/sheet_import.py).
const FIELD_DUTY_API = "avinashgroup_app.hr.sheet_import.";

frappe.ui.form.on("Field Duty", {
	refresh(frm) {
		if (frm.doc.docstatus !== 0) return;
		frm.add_custom_button(__("Download Template"), () => {
			if (!frm.doc.company) return frappe.msgprint(__("Choose the Company first."));
			const q = new URLSearchParams({ company: frm.doc.company });
			window.open(`/api/method/${FIELD_DUTY_API}download_field_duty_template?${q}`);
		}, __("Excel"));
		frm.add_custom_button(__("Import from Excel"), () => {
			if (!frm.doc.company) return frappe.msgprint(__("Choose the Company first."));
			new frappe.ui.FileUploader({
				restrictions: { allowed_file_types: [".xlsx", ".csv"] },
				make_attachments_public: false,
				on_success(file) {
					frappe
						.xcall(FIELD_DUTY_API + "read_field_duty_file", { file_url: file.file_url, company: frm.doc.company })
						.then(({ rows, errors }) => {
							if (!rows.length) {
								frappe.msgprint({ title: __("Nothing to import"), message: (errors || []).join("<br>") || __("No row has a date and both times.") });
								return;
							}
							frm.clear_table("rows");
							rows.forEach((r) => frm.add_child("rows", r));
							frm.refresh_field("rows");
							frm.dirty();
							const msg = __("{0} row(s) read. Check them, then Save and Submit.", [rows.length]);
							frappe.msgprint({
								title: __("Imported"),
								indicator: errors && errors.length ? "orange" : "green",
								message: errors && errors.length ? `${msg}<br><br>${__("Not read:")}<br>${errors.join("<br>")}` : msg,
							});
						});
				},
			});
		}, __("Excel"));
	},
});
