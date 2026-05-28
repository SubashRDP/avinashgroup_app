frappe.ui.form.on("Stock Adjustment", {
	setup: function(frm) {
		frm.set_query("item_code", "items", function() {
			return {
				filters: {
					disabled: 0,
					is_stock_item: 1
				}
			};
		});

		frm.set_query("warehouse", "items", function() {
			const filters = { is_group: 0 };
			if (frm.doc.company) {
				filters.company = frm.doc.company;
			}
			return { filters: filters };
		});
	},

	company: function(frm) {
		// Clear warehouses that no longer match the selected company
		(frm.doc.items || []).forEach(function(row) {
			if (row.warehouse) {
				frappe.db.get_value("Warehouse", row.warehouse, "company").then(function(r) {
					if (r.message && r.message.company !== frm.doc.company) {
						frappe.model.set_value(row.doctype, row.name, "warehouse", null);
					}
				});
			}
		});
	}
});
