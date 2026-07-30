frappe.ui.form.on("Material Request", {
	refresh: function(frm) {
		// Drop "Purchase Order" from the Create menu — this group buys through the
		// RFQ / Supplier Quotation flow, not a direct MR → PO. ERPNext adds the
		// button in its own refresh, so remove it after that runs.
		setTimeout(() => frm.remove_custom_button(__("Purchase Order"), __("Create")), 0);

		// Override get_item_data to force custom_buying_warehouse after ERPNext sets it
		const _orig = frm.events.get_item_data;
		frm.events.get_item_data = async function(frm, item, overwrite_warehouse) {
			if (!item || !item.item_code) {
				_orig.call(frm.events, frm, item, overwrite_warehouse);
				return;
			}
			// Fetch our custom warehouse first
			const custom_branch = frm.doc && frm.doc.custom_branch;
			let our_warehouse = '';
			if (custom_branch) {
				const item_doc = await frappe.db.get_doc('Item', item.item_code);
				const branch_rows = item_doc.custom_branch_wise_warehouse || [];
				const branch_row = branch_rows.find(r => r.custom_branch === custom_branch && r.custom_buying_warehouse);
				if (branch_row) our_warehouse = branch_row.custom_buying_warehouse;
			}
			if (!our_warehouse) {
				const result = await frappe.db.get_value('Item', item.item_code, 'custom_buying_warehouse');
				our_warehouse = (result && result.message && result.message.custom_buying_warehouse) || '';
			}
			// Patch frappe.call to intercept get_item_details callback and override warehouse
			const _orig_call = frappe.call;
			frappe.call = function(opts) {
				if (opts && opts.method && opts.method.includes('get_item_details')) {
					const _cb = opts.callback;
					opts.callback = function(r) {
						_cb && _cb(r);
						// Only override warehouse if custom_buying_warehouse is set
						if (our_warehouse) {
							frappe.model.set_value(item.doctype, item.name, 'warehouse', our_warehouse);
							frm.refresh_field('items');
						}
					};
				}
				return _orig_call.apply(frappe, arguments);
			};
			_orig.call(frm.events, frm, item, overwrite_warehouse);
			frappe.call = _orig_call; // Restore immediately after _orig kicks off the async call
		};
	}
});

frappe.ui.form.on("Material Request", {
	before_workflow_action: function (frm) {
		const workflow = window.avinashgroup_app && window.avinashgroup_app.approval_workflow;
		if (!workflow) return;

		return workflow.handleRejectAction(frm, {
			rejectReasonMethod: "avinashgroup_app.custom_code.workflow.set_reject_reason",
		});
	},
});
