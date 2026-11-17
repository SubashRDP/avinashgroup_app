// Customer form: "Portal Access" button.
// Opens the Customer Portal Access record (one dealer login → many customers)
// that covers this customer, or starts a new one prefilled from it. All the
// real work is in avinash_group_app/doctype/customer_portal_access.

frappe.ui.form.on("Customer", {
	refresh(frm) {
		if (frm.is_new() || !frappe.model.can_read("Customer Portal Access")) return;

		frm.add_custom_button(__("Portal Access"), () => {
			frappe.call({
				method: "avinashgroup_app.avinash_group_app.doctype.customer_portal_access.customer_portal_access.access_for_customer",
				args: { customer: frm.doc.name },
				callback(r) {
					const res = r.message || {};
					if (res.name) {
						frappe.set_route("Form", "Customer Portal Access", res.name);
						return;
					}
					if (res.legacy_user) {
						frappe.msgprint(__(
							"This customer is already linked to the login {0} on its Portal Users tab. "
							+ "Remove that row first, or create the access record with that login's mobile number.",
							[res.legacy_user.bold()]));
						return;
					}
					frappe.new_doc("Customer Portal Access", {
						full_name: res.full_name,
						mobile_no: res.mobile_no || "",
					}).then(() => {
						const f = cur_frm;
						f.clear_table("customers");
						f.add_child("customers", { customer: frm.doc.name, customer_name: frm.doc.customer_name });
						f.refresh_field("customers");
					});
				},
			});
		}, __("Create"));
	},
});
