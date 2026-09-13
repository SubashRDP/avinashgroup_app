frappe.query_reports["Custom Supplier Quotation Comparison"] = {
	filters: [
		{
			fieldtype: "Link",
			label: __("Company"),
			options: "Company",
			fieldname: "company",
			default: frappe.defaults.get_user_default("Company"),
			reqd: 1,
			// Every other filter is scoped to the company, so a company picked by
			// hand starts the comparison afresh. A company filled in automatically -
			// opening from a PO / MR, or a picked PO bringing its own company - leaves
			// them alone. Frappe raises _no_refresh while it sets filters itself, but
			// drops it before the last one, hence the remembered _scope_company too.
			on_change: (report) => {
				const settings = frappe.query_reports["Custom Supplier Quotation Comparison"];
				const company = report.get_filter_value("company");
				if (report._no_refresh || (company && company === settings._scope_company)) {
					settings._scope_company = null;
					if (!report._no_refresh) report.refresh();
					return;
				}
				const cleared = {};
				["material_request", "item_code"].forEach((f) => {
					if (report.get_filter_value(f)) cleared[f] = "";
				});
				// Purchase Order last: its on_change is what refreshes once all are cleared.
				["supplier", "supplier_quotation", "purchase_order"].forEach((f) => {
					if ((report.get_filter_value(f) || []).length) cleared[f] = [];
				});
				if (Object.keys(cleared).length) {
					report.set_filter_value(cleared);
				} else {
					report.refresh();
				}
			},
		},
		// Not mandatory: a Purchase Order (or Material Request) is an exact scope on
		// its own and runs with the dates cleared - see the purchase_order filter
		// below and get_data(). Left alone, they default to the last month.
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			width: "80",
			default: frappe.datetime.add_months(frappe.datetime.get_today(), -1),
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			width: "80",
			default: frappe.datetime.get_today(),
		},
		{
			fieldtype: "Link",
			label: __("Material Request"),
			options: "Material Request",
			fieldname: "material_request",
			default: "",
			// Only Material Requests with a quotation in the current company / PO /
			// supplier / item scope - with a PO picked, that PO's own MR(s).
			get_query: () => ({
				query: "avinashgroup_app.avinash_group_app.report.custom_supplier_quotation_comparison.custom_supplier_quotation_comparison.get_filter_material_requests",
				filters: {
					company: frappe.query_report.get_filter_value("company"),
					purchase_order: frappe.query_report.get_filter_value("purchase_order"),
					supplier_quotation: frappe.query_report.get_filter_value("supplier_quotation"),
					supplier: frappe.query_report.get_filter_value("supplier"),
					item_code: frappe.query_report.get_filter_value("item_code"),
				},
			}),
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
			// Off: one compact "Ordered" qty column per Purchase Order made from a
			// quotation. On: a full Qty / Rate / Amount sub-group per Purchase Order.
			fieldtype: "Check",
			label: __("Extend Purchase Order"),
			fieldname: "extend_purchase_order",
			default: 0,
		},
		{
			fieldtype: "MultiSelectList",
			label: __("Purchase Order"),
			options: "Purchase Order",
			fieldname: "purchase_order",
			default: "",
			// Several orders can be compared at once. Resolved to their source
			// Material Request(s) server-side (see get_data). Only orders raised
			// from a Material Request in the comparison are offered - opened from a
			// PO, that is the PO and its siblings (same MR, other suppliers).
			get_data: function (txt) {
				return frappe
					.call({
						method: "avinashgroup_app.avinash_group_app.report.custom_supplier_quotation_comparison.custom_supplier_quotation_comparison.get_filter_purchase_orders",
						args: {
							company: frappe.query_report.get_filter_value("company"),
							material_request: frappe.query_report.get_filter_value("material_request"),
							purchase_order: frappe.query_report.get_filter_value("purchase_order"),
							txt: txt,
						},
					})
					.then((r) => r.message || []);
			},
			// The comparison must run against the POs' company (not the user's
			// default) and show which Material Request they were raised from -
			// both are filled in automatically when a PO is picked.
			on_change: (report) => {
				const pos = report.get_filter_value("purchase_order") || [];
				if (!pos.length) {
					report.refresh();
					return;
				}
				Promise.all([
					// The dropdown is company-scoped, so every picked PO shares the first one's company.
					frappe.db.get_value("Purchase Order", pos[0], "company"),
					frappe.call({
						method: "avinashgroup_app.avinash_group_app.report.custom_supplier_quotation_comparison.custom_supplier_quotation_comparison.get_material_requests_from_purchase_order",
						args: { purchase_order: pos },
					}),
				]).then(([company_r, mr_r]) => {
					const company = company_r.message && company_r.message.company;
					const mrs = mr_r.message || [];
					const values = {};
					if (company && company !== report.get_filter_value("company")) {
						values.company = company;
						// tells the Company filter this change is automatic - keep the PO
						frappe.query_reports["Custom Supplier Quotation Comparison"]._scope_company = company;
					}
					// Only unambiguous when all the picked POs share a single MR; the
					// server unions their MRs regardless, so this display default
					// never narrows results.
					if (mrs.length === 1 && mrs[0] !== report.get_filter_value("material_request")) {
						values.material_request = mrs[0];
					}
					// A Purchase Order is an exact scope by itself, so the date window
					// comes off. Keeping it can only hide the very quotations the order
					// was raised from - they predate it. Clearing the filters (rather
					// than widening them) also shows the user why the range stopped
					// applying.
					if (report.get_filter_value("from_date")) values.from_date = "";
					if (report.get_filter_value("to_date")) values.to_date = "";
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
		// Per-unit columns (quoted / PO qty and rate, narration) mean nothing on the
		// summary and terms rows, which only carry block-level values.
		const PER_UNIT = ["_qty", "_rate", "_narration", "_poqty", "_porate"];
		const per_unit = PER_UNIT.some((suffix) => column.fieldname.endsWith(suffix));
		const qty_text = (v) => format_number(v, null, 3).replace(/(\.\d*?)0+$/, "$1").replace(/\.$/, "");

		// Commercial-terms rows (Specification / Warranty / Payment Terms /
		// Delivery Period) carry free text under each supplier's Amount column -
		// no currency formatting, and the per-unit Rate/Narration columns stay empty.
		if (data && data.is_term_row) {
			if (column.fieldname === "sn" || column.fieldname === "item_name") return "";
			if (column.fieldname === "qty") return default_formatter(value, row, column, data);
			if (per_unit) return "";
			if (value === null || value === undefined || value === "") return "";
			return frappe.utils.escape_html(String(value)).replace(/\n/g, "<br>");
		}

		// Summary rows are quotation-level values - a per-unit Rate/Narration makes no sense there.
		if (data && (data.is_total_row || data.is_summary_row || data.is_invoice_row) && per_unit) {
			return "";
		}
		// Discount / VAT / Invoice Amount belong to the quotation; a PO only carries its
		// own Total, so its Amount stays blank on those rows rather than reading Rs 0.00.
		if (data && (data.is_summary_row || data.is_invoice_row) && column.fieldname.endsWith("_poamt")) {
			return "";
		}

		// A PO's qty: only the decimals it needs (1, 1.5, 1,250), like the others. In
		// the compact "Ordered N" columns it gets a tick, with the PO number on hover.
		if (column.fieldname.endsWith("_poqty")) {
			if (value === null || value === undefined || value === "") return "";
			if (!column.po_compact) return qty_text(value);
			const tick =
				'<span style="display:inline-block;width:15px;height:15px;line-height:15px;border-radius:50%;' +
				'background:#28a745;color:#fff;font-size:10px;font-weight:bold;text-align:center;vertical-align:middle;">✓</span>&nbsp;';
			return `<span title="${frappe.utils.escape_html(column.po_link || "")}">${tick}${qty_text(value)}</span>`;
		}

		// Quoted column: the qty this quotation offers. Flagged orange when it differs
		// from MR Qty (what the Material Request asked for), with the asked qty on hover,
		// so a short or over quote stands out without reading every number.
		if (column.fieldname.endsWith("_qty")) {
			if (value === null || value === undefined || value === "") return "";
			const shown = qty_text(value);
			const asked = data && data.qty;
			if (asked !== null && asked !== undefined && asked !== "" && flt(value) !== flt(asked)) {
				const tip = frappe.utils.escape_html(__("Material Request asked for {0}", [format_number(asked)]));
				return `<span title="${tip}" style="color: var(--orange-600, #c2410c); font-weight: 600;">${shown}</span>`;
			}
			return shown;
		}

		// Narration column is kept narrow to save space; the full text is still
		// reachable via a hover tooltip instead of widening the column.
		if (column.fieldname.endsWith("_narration")) {
			if (value === null || value === undefined || value === "") return "";
			const shown = frappe.utils.escape_html(String(value));
			return `<span title="${shown}">${shown}</span>`;
		}

		value = default_formatter(value, row, column, data);

		if (data && (data.is_total_row || data.is_invoice_row)) {
			value = `<b>${value}</b>`;
		}
		return value;
	},

	after_datatable_render: (datatable) => {
		frappe.query_reports["Custom Supplier Quotation Comparison"].decorate_datatable(datatable);
	},

	// Two merged header rows above the datatable's own column labels, like a
	// hand-made sheet: the Supplier Quotation across its whole block, and under it
	// "Quoted" and what was Ordered from that quotation. Injected on every render;
	// scrolls with the header because the datatable applies its translateX to the
	// whole .dt-header element.
	//
	// Colour comes from each column's `tint` - the quotation's colour family, sent
	// by the server so print and Excel match: a deeper shade on the quotation
	// heading, a light one under what was Quoted and a stronger one under what was
	// Ordered, and the family's accent as the block's left edge, drawn as one line
	// from the heading down to the last row.
	decorate_datatable: (datatable) => {
		if (!datatable || !datatable.wrapper) return;
		const esc = frappe.utils.escape_html;
		const scope = datatable.style && datatable.style.scopeClass ? `.${datatable.style.scopeClass} ` : "";

		const render_group_header = () => {
			const $header = $(datatable.wrapper).find(".dt-header");
			$header.find(".sq-supplier-group-row").remove();

			const header_cells = $header.find(".dt-row-header .dt-cell--header").toArray();
			if (!header_cells.length) return;

			const cols = header_cells.map((cell) => {
				const idx = parseInt(cell.getAttribute("data-col-index"));
				const col = (!isNaN(idx) && datatable.datamanager.getColumn(idx)) || {};
				return {
					idx: idx,
					sq: col.sq_link || "",
					group: col.supplier_group || "",
					sub: col.sub_group || "",
					po: col.po_link || "",
					tint: col.tint || {},
				};
			});
			if (!cols.some((c) => c.sq)) return;
			// "Ordered 1" says which PO it is on hover
			header_cells.forEach((cell, n) => {
				if (cols[n].po) cell.title = cols[n].po;
			});

			// Where each quotation block, and each sub-group inside it, begins.
			cols.forEach((c, n) => {
				const prev = cols[n - 1];
				c.edge = !c.sq ? "" : !prev || prev.sq !== c.sq ? "block" : prev.sub !== c.sub ? "sub" : "";
			});
			// Drawn as inset shadows, which take no width, so they can never push a
			// heading out of line with the columns under it.
			const edge_line = (c) =>
				c.edge === "block"
					? `box-shadow: inset 2px 0 0 ${c.tint.accent};`
					: c.edge === "sub"
					? `box-shadow: inset 1px 0 0 ${c.tint.soft};`
					: "";

			// A run's width is each column's width PLUS the 1px border the datatable
			// draws after every cell. Counting only the widths left each merged
			// heading 1px short per column, so the dividers drifted off the columns.
			const keeper = (idx) =>
				`<div class="dt-cell__content--col-${idx}" style="height:0;flex:none;"></div><div style="width:1px;flex:none;"></div>`;
			const keepers = (run) => run.map((x) => keeper(x.idx)).join("");

			// One merged cell per run of consecutive columns sharing key(c).
			const build_row = (key, cell_html) => {
				let html = "";
				for (let i = 0; i < cols.length; ) {
					let j = i;
					while (j < cols.length && key(cols[j]) === key(cols[i])) j++;
					const run = cols.slice(i, j);
					html += cols[i].sq ? cell_html(cols[i], run) : `<div style="display:flex;">${keepers(run)}</div>`;
					i = j;
				}
				return html;
			};
			const merged = (c, run, background, attrs, inner, extra_style = "") =>
				`<div ${attrs} data-last="${run[run.length - 1].idx}"
					style="position:relative;display:flex;background:${background};${edge_line(c)}${extra_style}">${keepers(run)}
					<div style="position:absolute;inset:0;display:flex;align-items:center;justify-content:center;
						overflow:hidden;white-space:nowrap;text-overflow:ellipsis;padding:0 10px;">${inner}</div></div>`;

			const quotation_row = build_row(
				(c) => c.sq,
				(c, run) =>
					merged(
						c,
						run,
						c.tint.head,
						`class="sq-group-cell" data-sq-link="${esc(c.sq)}" title="${__("Open Supplier Quotation")}"`,
						`<span style="overflow:hidden;text-overflow:ellipsis;">
							<span style="font-weight:600;color:${c.tint.text};">${esc(c.group)}</span>
							<span style="margin-left:4px;font-size:11px;color:${c.tint.text};opacity:.7;">(${esc(c.sq)})</span>
						</span>`,
						"cursor:pointer;"
					)
			);
			const sub_row = build_row(
				(c) => `${c.sq}|${c.sub}`,
				(c, run) => {
					const ordered = run.some((x) => x.po);
					// A heading links to its PO only when it stands for one PO - the compact
					// "Ordered" heading spans one column per PO, each column links itself.
					const po = run.every((x) => x.po === c.po) ? c.po : "";
					const colour = c.sub.startsWith("★") ? "var(--orange-600, #c2410c)" : c.tint.text;
					return merged(
						c,
						run,
						ordered ? c.tint.ordered_head : c.tint.quoted_head,
						`class="sq-sub-cell"${po ? ` data-po-link="${esc(po)}" title="${__("Open Purchase Order")}"` : ""}`,
						`<span style="font-weight:${ordered ? 600 : 500};color:${colour};">${esc(c.sub)}</span>`,
						po ? "cursor:pointer;" : ""
					);
				}
			);
			const bar = "display:flex;background:var(--dt-header-cell-bg, #f7fafc);border-bottom:1px solid var(--dt-border-color, #d1d8dd);";
			$header.prepend(`<div class="sq-supplier-group-row" style="${bar}height:24px;">${sub_row}</div>`);
			$header.prepend(`<div class="sq-supplier-group-row" style="${bar}height:30px;">${quotation_row}</div>`);

			// Every cell of a column - label, filter and body - in its shade, with the
			// block / sub-group edge carried down the whole column.
			let rules = "";
			cols.forEach((c) => {
				if (!c.sq) return;
				rules += `${scope}.dt-cell--col-${c.idx}{background-color:${c.po ? c.tint.ordered : c.tint.quoted};${edge_line(c)}}\n`;
			});
			let $style = $(datatable.wrapper).find("style.sq-supplier-band-style");
			if (!$style.length) {
				$style = $('<style class="sq-supplier-band-style"></style>').appendTo(datatable.wrapper);
			}
			$style.text(rules);
		};

		render_group_header();

		// Dragging a column to reorder it only swaps columns inside the datatable
		// widget itself - it doesn't go through a report refresh, so this hook
		// never re-fires and the merged header rows would describe the old column
		// order. The datatable fires "onSwitchColumn" for that; hook it once per
		// datatable instance to rebuild the header in sync.
		if (!datatable._sq_switch_column_hooked) {
			datatable._sq_switch_column_hooked = true;
			datatable.on("onSwitchColumn", () => render_group_header());
		}
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

		// Quotation heading -> its Supplier Quotation; PO heading -> that Purchase Order
		$(report.page.wrapper)
			.off("click.sq_group")
			.on("click.sq_group", ".sq-group-cell[data-sq-link]", function () {
				frappe.set_route("Form", "Supplier Quotation", $(this).attr("data-sq-link"));
			})
			.on("click.sq_group", ".sq-sub-cell[data-po-link]", function () {
				frappe.set_route("Form", "Purchase Order", $(this).attr("data-po-link"));
			});

		// Column label -> the PO it belongs to, else its quotation
		$(report.page.wrapper)
			.off("click.sq_link")
			.on("click.sq_link", ".dt-cell--header", function (e) {
				// Ignore clicks on the column dropdown / resize handle
				if ($(e.target).closest(".dt-dropdown, .dt-cell__resize-handle").length) return;
				const col_index = parseInt($(this).attr("data-col-index"));
				if (isNaN(col_index) || !report.datatable) return;
				const col = report.datatable.datamanager.getColumn(col_index) || {};
				if (col.po_link) {
					frappe.set_route("Form", "Purchase Order", col.po_link);
				} else if (col.sq_link) {
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
