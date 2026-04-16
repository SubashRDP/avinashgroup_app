frappe.ui.form.on("Material Request", {
	refresh: function(frm) {
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
		if (frm.selected_workflow_action !== "Reject") return;

		return new Promise((resolve, reject) => { 
			let settled = false;
			let is_submitting = false;
			const resolveOnce = (value) => {
				if (settled) return;
				settled = true;
				resolve(value);
			};
			const rejectOnce = (reason) => {
				if (settled) return;
				settled = true;
				reject(reason);
			};
			let d = new frappe.ui.Dialog({
				title: __("Rejection Reason"),
				fields: [
					{
						fieldtype: "Small Text",
						fieldname: "reject_reason",
						label: __("Reason for Rejection"),
						reqd: 1,
					},
				],
				primary_action_label: __("Reject"),
				primary_action() {
					let reason = d.get_value("reject_reason");
					if (!reason || !reason.trim()) {
						frappe.msgprint(__("Please enter a rejection reason."));
						return;
					}
					is_submitting = true;
					d.hide();
					frappe.dom.freeze(__("Submitting rejection..."));
					frappe.xcall(
						"avinashgroup_app.custom_code.workflow_material_request.set_reject_reason",
						{
							doctype: frm.doctype,
							name: frm.doc.name,
							reason: reason.trim(),
						}
					)
						.then((response) => {
							frappe.msgprint(__("Rejection recorded successfully"));
							resolveOnce();
						})
						.catch((error) => {
							frappe.msgprint(__("Error saving rejection reason"));
							console.error(error);
							rejectOnce(error);
						})
						.finally(() => {
							frappe.dom.unfreeze();
						});
				},
				secondary_action_label: __("Cancel"),
				secondary_action() {
					d.hide();
					rejectOnce("cancelled");
				},
			});
			d.onhide = () => {
				// If user closes the dialog via X/ESC, do not leave the promise pending.
				if (is_submitting) return;
				rejectOnce("dialog_closed");
			};
			d.show();
			// Allow typing in the dialog while workflow waits on the promise.
			frappe.dom.unfreeze();
		});
	},
});
