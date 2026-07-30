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
			// Only items quoted within the current PO / MR / company scope.
			get_query: () => ({
				query: "avinashgroup_app.avinash_group_app.report.custom_supplier_quotation_comparison.custom_supplier_quotation_comparison.get_filter_items",
				filters: {
					company: frappe.query_report.get_filter_value("company"),
					purchase_order: frappe.query_report.get_filter_value("purchase_order"),
					material_request: frappe.query_report.get_filter_value("material_request"),
					supplier_quotation: frappe.query_report.get_filter_value("supplier_quotation"),
					supplier: frappe.query_report.get_filter_value("supplier"),
				},
			}),
		},
		{
			fieldname: "supplier",
			label: __("Supplier"),
			fieldtype: "MultiSelectList",
			options: "Supplier",
			get_data: function (txt) {
				// Only suppliers with a quotation in the current PO / MR / company scope.
				return frappe
					.call({
						method: "avinashgroup_app.avinash_group_app.report.custom_supplier_quotation_comparison.custom_supplier_quotation_comparison.get_filter_suppliers",
						args: {
							company: frappe.query_report.get_filter_value("company"),
							purchase_order: frappe.query_report.get_filter_value("purchase_order"),
							material_request: frappe.query_report.get_filter_value("material_request"),
							supplier_quotation: frappe.query_report.get_filter_value("supplier_quotation"),
							item_code: frappe.query_report.get_filter_value("item_code"),
							txt: txt,
						},
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
				// Only offer quotations aligned to the selected Purchase Order
				// (via its Material Requests) / Material Request / company.
				return frappe
					.call({
						method: "avinashgroup_app.avinash_group_app.report.custom_supplier_quotation_comparison.custom_supplier_quotation_comparison.get_supplier_quotations",
						args: {
							company: frappe.query_report.get_filter_value("company"),
							purchase_order: frappe.query_report.get_filter_value("purchase_order"),
							material_request: frappe.query_report.get_filter_value("material_request"),
							supplier: frappe.query_report.get_filter_value("supplier"),
							item_code: frappe.query_report.get_filter_value("item_code"),
							txt: txt,
						},
					})
					.then((r) => r.message || []);
			},
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
			// The comparison must run against the PO's company (not the user's
			// default) and show which Material Request the PO was raised from -
			// both are filled in automatically when a PO is picked.
			on_change: (report) => {
				const po = report.get_filter_value("purchase_order");
				if (!po) {
					report.refresh();
					return;
				}
				Promise.all([
					frappe.db.get_value("Purchase Order", po, "company"),
					frappe.call({
						method: "avinashgroup_app.avinash_group_app.report.custom_supplier_quotation_comparison.custom_supplier_quotation_comparison.get_material_requests_from_purchase_order",
						args: { purchase_order: po },
					}),
				]).then(([company_r, mr_r]) => {
					const company = company_r.message && company_r.message.company;
					const mrs = mr_r.message || [];
					const values = {};
					if (company && company !== report.get_filter_value("company")) {
						values.company = company;
					}
					// Only unambiguous with a single MR; the server unions the PO's
					// MRs regardless, so this display default never narrows results.
					if (mrs.length === 1 && mrs[0] !== report.get_filter_value("material_request")) {
						values.material_request = mrs[0];
					}
					if (Object.keys(values).length) {
						// setting the filters triggers the refresh itself
						report.set_filter_value(values);
					} else {
						report.refresh();
					}
				});
			},
		},
	],

	formatter: (value, row, column, data, default_formatter) => {
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

	// Draw one spanning supplier-name cell above each Rate + Amount column pair.
	// Injected above the datatable header on every render; scrolls with it because
	// the datatable applies its translateX to the whole .dt-header element.
	after_datatable_render: (datatable) => {
		if (!datatable || !datatable.wrapper) return;
		const $header = $(datatable.wrapper).find(".dt-header");
		$header.find(".sq-supplier-group-row").remove();

		const header_cells = $header.find(".dt-row-header .dt-cell--header").toArray();
		if (!header_cells.length) return;

		// Merge consecutive rendered header cells that share a supplier_group.
		// Widths come from invisible "keeper" divs carrying the datatable's own
		// .dt-cell__content--col-N classes - its width stylesheet keeps them in
		// sync with the real columns, including later resizes / fit-columns.
		const cols = header_cells.map((cell) => {
			const idx = parseInt(cell.getAttribute("data-col-index"));
			const col = (!isNaN(idx) && datatable.datamanager.getColumn(idx)) || {};
			return { idx: idx, group: col.supplier_group || "", sq_link: col.sq_link };
		});
		if (!cols.some((c) => c.group)) return;

		const keeper = (idx) => `<div class="dt-cell__content--col-${idx}" style="height:0;"></div>`;
		const border = "1px solid var(--dt-border-color, #d1d8dd)";
		let cells_html = "";
		let i = 0;
		while (i < cols.length) {
			const c = cols[i];
			if (!c.group) {
				cells_html += `<div style="display:flex;border-right:1px solid transparent;">${keeper(c.idx)}</div>`;
				i++;
				continue;
			}
			let keepers = "";
			let j = i;
			while (j < cols.length && cols[j].group === c.group) {
				keepers += keeper(cols[j].idx);
				j++;
			}
			const link_attr = c.sq_link
				? ` data-sq-link="${frappe.utils.escape_html(c.sq_link)}" title="${__("Open Supplier Quotation")}"`
				: "";
			cells_html += `<div class="sq-group-cell"${link_attr}
				style="position:relative;display:flex;border-right:${border};${c.sq_link ? "cursor:pointer;" : ""}">${keepers}
				<div style="position:absolute;inset:0;display:flex;align-items:center;justify-content:center;
					font-weight:600;overflow:hidden;white-space:nowrap;text-overflow:ellipsis;padding:0 8px;">
					${frappe.utils.escape_html(c.group)}</div></div>`;
			i = j;
		}
		$header.prepend(
			`<div class="sq-supplier-group-row"
				style="display:flex;height:26px;background:var(--dt-header-cell-bg, #f7fafc);border-bottom:${border};">${cells_html}</div>`
		);
	},

	onload: (report) => {
		// Menu -> Print / PDF both render the server-side comparison document
		// (supplier column groups + summary rows) instead of the generic report
		// printout. Print opens the PDF inline for printing; PDF downloads it.
		const comparison_pdf_url = (view) => {
			const filters = frappe.query_report.get_filter_values(true);
			return (
				"/api/method/avinashgroup_app.avinash_group_app.report.custom_supplier_quotation_comparison.custom_supplier_quotation_comparison.download_pdf" +
				"?filters=" + encodeURIComponent(JSON.stringify(filters)) +
				(view ? "&view=1" : "")
			);
		};
		report.print_report = () => window.open(comparison_pdf_url(1));
		report.pdf_report = () => window.open(comparison_pdf_url(0));

		// Menu -> Export: custom Excel that keeps the supplier-group header row
		// (supplier name merged above its Rate/Amount pair), which the stock
		// export drops. Instance-level override, this report only.
		report.export_report = () => {
			const filters = frappe.query_report.get_filter_values(true);
			window.open(
				"/api/method/avinashgroup_app.avinash_group_app.report.custom_supplier_quotation_comparison.custom_supplier_quotation_comparison.export_xlsx" +
				"?filters=" + encodeURIComponent(JSON.stringify(filters))
			);
		};

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

		// Supplier group cell -> open that supplier's quotation
		$(report.page.wrapper)
			.off("click.sq_group")
			.on("click.sq_group", ".sq-group-cell[data-sq-link]", function () {
				frappe.set_route("Form", "Supplier Quotation", $(this).attr("data-sq-link"));
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
