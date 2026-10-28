// Purchase Order: "Create → Letter of Credit", and a headline when NRB rules
// say this import needs an LC (or it already has one). Loaded through
// app_include_js so it works wherever the PO form opens. See lc/lifecycle.py
// make_from_purchase_order and purchase_order_hint.

frappe.ui.form.on("Purchase Order", {
	refresh(frm) {
		if (frm.doc.docstatus !== 1 || frm.doc.currency === frappe.defaults.get_default("currency")) return;
		frm.add_custom_button(__("Letter of Credit"), () => {
			frappe.call({
				method: "avinashgroup_app.lc.lifecycle.make_from_purchase_order",
				args: { purchase_order: frm.doc.name },
				freeze: true,
				callback: (r) => {
					const doc = frappe.model.sync(r.message)[0];
					frappe.set_route("Form", doc.doctype, doc.name);
				},
			});
		}, __("Create"));

		frappe.call({
			method: "avinashgroup_app.lc.lifecycle.purchase_order_hint",
			args: { purchase_order: frm.doc.name },
			callback: (r) => {
				const hint = r.message;
				if (!hint) return;
				if (hint.lcs) {
					const links = hint.lcs.map((l) => `<a href="/app/letter-of-credit/${l.name}">${l.name}</a> (${__(l.status)})`);
					frm.dashboard.set_headline(__("Letter of Credit: {0}", [links.join(", ")]), "blue");
				} else if (hint.message) {
					frm.dashboard.set_headline(hint.message, "orange");
				}
			},
		});
	},
});
