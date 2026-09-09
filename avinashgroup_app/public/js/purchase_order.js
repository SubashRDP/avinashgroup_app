function sync_required_by_to_items(frm) {
	if (!frm.doc.schedule_date || !frm.doc.items) return;

	frm.doc.items.forEach((row) => {
		row.schedule_date = frm.doc.schedule_date;
	});

	frm.refresh_field("items");
}

frappe.ui.form.on("Purchase Order", {
	refresh: function (frm) {
		// The Purchase Order is where the approval workflow runs. Each approver opens
		// the Supplier Quotation Comparison to decide accept / reject, so the entry
		// point lives here - as a button of its own on the toolbar rather than buried
		// in the View / Actions menus, since it is the one thing an approver comes here
		// to do. The report is scoped to the Material Request(s) this PO was
		// raised from — the PO itself carries no supplier_quotation link we rely on, but
		// its item lines carry material_request, and get_data() resolves PO → MR.
		//
		// Shown on any non-cancelled PO (draft or submitted) so it is available while
		// the document is still moving through the workflow.
		if (frm.doc.docstatus >= 2) return;

		sync_required_by_to_items(frm);

		const has_source_mr = (frm.doc.items || []).some((row) => row.material_request);
		if (!has_source_mr) return;

		frm.add_custom_button(__("Supplier Quotation Comparison"), function () {
			// No date window. The PO's Material Request(s) already scope the report
			// exactly, and a range anchored on this order's own date would hide every
			// quotation behind it - they were raised before the order, not after it.
			frappe.route_options = {
				company: frm.doc.company,
				from_date: "",
				to_date: "",
				purchase_order: frm.doc.name,
			};
			frappe.set_route("query-report", "Custom Supplier Quotation Comparison");
		});
	},

	schedule_date: function (frm) {
		sync_required_by_to_items(frm);
	},
});
