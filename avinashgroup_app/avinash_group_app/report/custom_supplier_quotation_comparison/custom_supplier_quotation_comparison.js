frappe.query_reports["Custom Supplier Quotation Comparison"] = {
	filters: [
		{
			fieldtype: "Link",
			label: __("Company"),
			options: "Company",
			fieldname: "company",
			default: frappe.defaults.get_user_default("Company"),
			reqd: 1,
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			width: "80",
			reqd: 1,
			default: frappe.datetime.add_months(frappe.datetime.get_today(), -1),
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			width: "80",
			reqd: 1,
			default: frappe.datetime.get_today(),
		},
		{
			fieldtype: "Link",
			label: __("Material Request"),
			options: "Material Request",
			fieldname: "material_request",
			default: "",
			get_query: () => {
				const company = frappe.query_report.get_filter_value("company");
				const filters = { docstatus: ["<", 2], material_request_type: "Purchase" };
				if (company) filters.company = company;
				return { filters };
			},
		},
		{
			default: "",
			options: "Item",
			label: __("Item"),
			fieldname: "item_code",
			fieldtype: "Link",
			get_query: () => {
				let quote = frappe.query_report.get_filter_value("supplier_quotation");
				if (quote != "") {
					return {
						query: "erpnext.stock.doctype.quality_inspection.quality_inspection.item_query",
						filters: {
							from: "Supplier Quotation Item",
							parent: quote,
						},
					};
				}
			},
		},
		{
			fieldname: "supplier",
			label: __("Supplier"),
			fieldtype: "MultiSelectList",
			options: "Supplier",
			get_data: function (txt) {
				// Scope suppliers to those with a Supplier Quotation in the selected company.
				const company = frappe.query_report.get_filter_value("company");
				return frappe
					.call({
						method: "avinashgroup_app.avinash_group_app.report.custom_supplier_quotation_comparison.custom_supplier_quotation_comparison.get_company_suppliers",
						args: { company: company, txt: txt },
					})
					.then((r) => r.message || []);
			},
		},
		{
			fieldtype: "MultiSelectList",
			label: __("Supplier Quotation"),
			fieldname: "supplier_quotation",
			options: "Supplier Quotation",
			default: "",
			get_data: function (txt) {
				return frappe.db.get_link_options("Supplier Quotation", txt, { docstatus: ["<", 2] });
			},
		},
		{
			// Toggled by the "Show/Hide SQ Remarks" button, not shown as a filter.
			fieldname: "show_remarks",
			label: __("Show SQ Remarks"),
			fieldtype: "Check",
			default: 0,
			hidden: 1,
		},
		{
			fieldtype: "Check",
			label: __("Preferred Quotation"),
			fieldname: "preferred_quotation",
			default: 1,
		},
		{
			fieldtype: "Link",
			label: __("Purchase Order"),
			options: "Purchase Order",
			fieldname: "purchase_order",
			default: "",
			// Resolved to its source Material Request(s) server-side (see get_data).
			get_query: () => ({ filters: { docstatus: ["<", 2] } }),
		},
	],

	formatter: (value, row, column, data, default_formatter) => {
		// Remarks row holds free text inside Currency columns - show it as plain text.
		if (data && data.is_remarks_row && !["sn", "item_name", "qty"].includes(column.fieldname)) {
			return value ? `<span title="${frappe.utils.escape_html(value)}">${frappe.utils.escape_html(value)}</span>` : "";
		}

		// Summary rows are quotation-level values - a per-unit Rate makes no sense there.
		if (
			data &&
			(data.is_total_row || data.is_summary_row || data.is_invoice_row) &&
			column.fieldname.endsWith("_rate")
		) {
			return "";
		}

		value = default_formatter(value, row, column, data);

		if (data && (data.is_total_row || data.is_invoice_row)) {
			value = `<b>${value}</b>`;
		}
		return value;
	},

	onload: (report) => {
		// Create a button for setting the default supplier
		report.page.add_inner_button(
			__("Select Default Supplier"),
			() => {
				let reporter = frappe.query_reports["Custom Supplier Quotation Comparison"];

				//Always make a new one so that the latest values get updated
				reporter.make_default_supplier_dialog(report);
			},
			__("Tools")
		);

		// Toggle the SQ Remarks row (server appends it when show_remarks is set)
		report.page.add_inner_button(__("Show/Hide SQ Remarks"), () => {
			const filter = report.get_filter("show_remarks");
			filter.set_value(cint(filter.get_value()) ? 0 : 1);
		});

		// Supplier column header -> open that supplier's quotation
		$(report.page.wrapper)
			.off("click.sq_link")
			.on("click.sq_link", ".dt-cell--header", function (e) {
				// Ignore clicks on the column dropdown / resize handle
				if ($(e.target).closest(".dt-dropdown, .dt-cell__resize-handle").length) return;
				const col_index = parseInt($(this).attr("data-col-index"));
				if (isNaN(col_index) || !report.datatable) return;
				const col = report.datatable.datamanager.getColumn(col_index) || {};
				if (col.sq_link) {
					frappe.set_route("Form", "Supplier Quotation", col.sq_link);
				}
			});
	},
	make_default_supplier_dialog: (report) => {
		// Get the name of the item to change
		if (!report.data) return;

		let filters = report.get_values();
		let item_code = filters.item_code;

		// Get a list of the suppliers (with a blank as well) for the user to select
		let suppliers = $.map(report.data, (row, idx) => {
			return row.supplier_name;
		});

		let items = [];
		report.data.forEach((d) => {
			if (!items.includes(d.item_code)) {
				items.push(d.item_code);
			}
		});

		// Create a dialog window for the user to pick their supplier
		let dialog = new frappe.ui.Dialog({
			title: __("Select Default Supplier"),
			fields: [
				{
					reqd: 1,
					label: "Supplier",
					fieldtype: "Link",
					options: "Supplier",
					fieldname: "supplier",
					get_query: () => {
						return {
							filters: {
								name: ["in", suppliers],
							},
						};
					},
				},
				{
					reqd: 1,
					label: "Item",
					fieldtype: "Link",
					options: "Item",
					fieldname: "item_code",
					get_query: () => {
						return {
							filters: {
								name: ["in", items],
							},
						};
					},
				},
			],
		});

		dialog.set_primary_action(__("Set Default Supplier"), () => {
			let values = dialog.get_values();

			if (values) {
				// Set the default_supplier field of the appropriate Item to the selected supplier
				frappe.call({
					method: "erpnext.buying.report.supplier_quotation_comparison.supplier_quotation_comparison.set_default_supplier",
					args: {
						item_code: values.item_code,
						supplier: values.supplier,
						company: filters.company,
					},
					freeze: true,
					callback: (r) => {
						frappe.msgprint(__("Successfully Set Supplier"));
						dialog.hide();
					},
				});
			}
		});
		dialog.show();
	},
};
