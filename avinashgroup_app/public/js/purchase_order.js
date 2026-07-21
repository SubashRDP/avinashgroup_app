frappe.ui.form.on("Purchase Order", {
	refresh: function (frm) {
		// The Purchase Order is where the approval workflow runs. Each approver opens
		// the Supplier Quotation Comparison to decide accept / reject, so the entry
		// point lives here. The report is scoped to the Material Request(s) this PO was
		// raised from — the PO itself carries no supplier_quotation link we rely on, but
		// its item lines carry material_request, and get_data() resolves PO → MR.
		//
		// Shown on any non-cancelled PO (draft or submitted) so it is available while
		// the document is still moving through the workflow.
		if (frm.doc.docstatus >= 2) return;

		const has_source_mr = (frm.doc.items || []).some((row) => row.material_request);
		if (!has_source_mr) return;

		frm.add_custom_button(
			__("Supplier Quotation Comparison"),
			function () {
				const today = frappe.datetime.get_today();
				frappe.route_options = {
					company: frm.doc.company,
					from_date: frm.doc.transaction_date || frappe.datetime.add_months(today, -1),
					to_date: today,
					purchase_order: frm.doc.name,
				};
				frappe.set_route("query-report", "Custom Supplier Quotation Comparison");
			},
			__("View")
		);
	},
});
