// After submitting a Supplier Quotation that was created from a Material
// Request, route back to that Material Request so the procurement flow
// continues where it started.
//
// The item rows carry a material_request link when the document was made via
// the MR's Create menu; a Supplier Quotation created standalone has none,
// submits normally and stays put. When items span several Material Requests,
// the first linked one wins.
(() => {
	const back_to_material_request = (frm) => {
		const mr = (frm.doc.items || []).map((row) => row.material_request).find(Boolean);
		if (!mr) return;
		// Route only after the submit cycle has fully finished: navigating from
		// inside on_submit lets the submitted form's own post-submit refresh run
		// afterwards, which stamps its doctype into the breadcrumb of the
		// Material Request page we just routed to.
		setTimeout(() => frappe.set_route("Form", "Material Request", mr), 500);
	};

	frappe.ui.form.on("Supplier Quotation", { on_submit: back_to_material_request });
})();
