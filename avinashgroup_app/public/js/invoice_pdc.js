// "Create → PDC Cheque" on a submitted Sales / Purchase Invoice with an outstanding
// amount. Loaded from app_include_js (see the Sales Invoice note in hooks.py).
// Server side: avinashgroup_app.pdc.lifecycle.make_from_invoice.

["Sales Invoice", "Purchase Invoice"].forEach((doctype) => {
	frappe.ui.form.on(doctype, {
		refresh(frm) {
			if (frm.doc.docstatus !== 1 || flt(frm.doc.outstanding_amount) <= 0 || frm.doc.is_return) return;
			if (!frappe.model.can_create("PDC Cheque")) return;
			frm.add_custom_button(
				__("PDC Cheque"),
				() =>
					frappe.call({
						method: "avinashgroup_app.pdc.lifecycle.make_from_invoice",
						args: { doctype: frm.doctype, name: frm.doc.name },
						callback: (r) => {
							const doc = frappe.model.sync(r.message)[0];
							frappe.set_route("Form", doc.doctype, doc.name);
						},
					}),
				__("Create")
			);
		},
	});
});
