// Copyright (c) 2026, Raindrop and contributors
// For license information, please see license.txt

// [name, year_start_date, year_end_date] of the fiscal year covering today;
// guarded so a site with no running Fiscal Year doesn't error on report open.
var sales_register_fy = erpnext.utils.get_fiscal_year(frappe.datetime.get_today(), false, true)
	? erpnext.utils.get_fiscal_year(frappe.datetime.get_today(), true)
	: [];

frappe.query_reports["Sales Register Report"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "MultiSelectList",
			get_data: function(txt) {
				return frappe.db.get_link_options("Company", txt);
			},
		},
		{
			fieldname: "fiscal_year",
			label: __("Fiscal Year"),
			fieldtype: "Link",
			options: "Fiscal Year",
			default: sales_register_fy[0],
			on_change: function (query_report) {
				const fiscal_year = query_report.get_filter_value("fiscal_year");
				if (!fiscal_year) return;
				frappe.model.with_doc("Fiscal Year", fiscal_year, function () {
					const fy_doc = frappe.model.get_doc("Fiscal Year", fiscal_year);
					query_report.set_filter_value({
						from_date: fy_doc.year_start_date,
						to_date: fy_doc.year_end_date,
					});
				});
			},
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: sales_register_fy[1] || frappe.datetime.month_start(),
			reqd: 1,
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: sales_register_fy[2] || frappe.datetime.now_date(),
			reqd: 1,
		},
		{
			fieldname: "customer",
			label: __("Customer"),
			fieldtype: "MultiSelectList",
			get_data: function(txt) {
				// Scope customers to those with invoices in the selected company(ies).
				const company = frappe.query_report.get_filter_value("company");
				return frappe
					.call({
						method: "avinashgroup_app.avinash_group_app.report.sales_register_report.sales_register_report.get_company_customers",
						args: { company: company, txt: txt },
					})
					.then((r) => r.message || []);
			},
		},
		{
			fieldname: "branch",
			label: __("Branch"),
			fieldtype: "MultiSelectList",
			get_data: function(txt) {
				// Scope branches to the selected company(ies).
				const company = frappe.query_report.get_filter_value("company");
				return frappe
					.call({
						method: "avinashgroup_app.avinash_group_app.report.sales_register_report.sales_register_report.get_company_branches",
						args: { company: company, txt: txt },
					})
					.then((r) => r.message || []);
			},
		},
		{
			fieldname: "is_return",
			label: __("Is Return"),
			fieldtype: "Check",
			default: 0,
		},
		{
			fieldname: "fit_columns",
			label: __("Fit Columns"),
			fieldtype: "Check",
			default: 1,
			on_change: function () {
				frappe.query_report.refresh();
			},
		},
	],

	get_datatable_options(options) {
		return Object.assign(options, { serialNoColumn: false, freezeColumnsTo: 3, layout: "fixed" });
	},

	after_datatable_render: function (dt) {
		const fit = frappe.query_report.get_filter_value("fit_columns");
		if (fit) {
			// Wait for column widths to settle before measuring them for the govt heading.
			setTimeout(() => {
				this.autoFitColumns(dt);
				this.renderVatHeading(dt);
			}, 100);
		} else {
			this.renderVatHeading(dt);
		}
	},

	renderVatHeading: function (dt) {
		const wrapper = dt.datatableWrapper;
		if (!wrapper) return;

		$(wrapper).prev(".sr-vat-heading-onscreen").remove();
		if (dt.bodyScrollable) $(dt.bodyScrollable).off("scroll.srVatHeading");

		// Both states show a govt-form group-header row: "बिक्री खाता" (Sales) when
		// unticked, "बिक्री फिर्ता खाता" (Sales Return) when ticked — same overlay
		// mechanism, just a different field/group set server-side.
		const is_return = frappe.query_report.get_filter_value("is_return");

		const cols = frappe.query_report.columns || [];
		const report_fields = new Set(cols.map(c => c.fieldname));
		// Same column list/order as the datatable's own (already Nepali-labelled) header —
		// pixel widths come from here too, so our group-header row lines up column-for-column.
		const dtCols = (dt.datamanager ? dt.datamanager.getColumns() : [])
			.filter(c => report_fields.has(c.fieldname));
		if (!dtCols.length) return;

		const visible = dtCols.map(c => c.fieldname);
		// nothing removed -> [] so the server just shows all (matches print's convention)
		const selected_columns = visible.length === report_fields.size ? [] : visible;
		const colWidths = dtCols.map(c => c.width || 120);
		const totalWidth = colWidths.reduce((a, b) => a + b, 0);

		frappe.call({
			method: "avinashgroup_app.avinash_group_app.report.sales_register_report.sales_register_report.get_govt_header_html",
			args: { selected_columns: JSON.stringify(selected_columns), is_return: is_return ? 1 : 0 },
		}).then((r) => {
			// Bail if the datatable re-rendered (filters changed) while this call was in flight.
			if (frappe.query_report.get_filter_value("is_return") != is_return) return;
			$(wrapper).prev(".sr-vat-heading-onscreen").remove();

			// Force each column to the datatable's own pixel width via <colgroup>, so colspan
			// group cells stretch to exactly match their underlying Nepali columns below.
			const colgroup = "<colgroup>" + colWidths.map((w) => `<col style="width:${w}px">`).join("") + "</colgroup>";
			const tableHtml = (r.message || "").replace(
				"<table>",
				`<table style="table-layout:fixed; width:${totalWidth}px;">${colgroup}`
			);

			const $outer = $(`<div class="sr-vat-heading-onscreen"><div class="sr-vat-heading-scroll">${tableHtml}</div></div>`);
			$outer.insertBefore(wrapper);
			$outer.css("width", wrapper.clientWidth + "px");

			const $scrollInner = $outer.find(".sr-vat-heading-scroll");
			const syncScroll = () => {
				$scrollInner.css("transform", `translateX(${-dt.bodyScrollable.scrollLeft}px)`);
			};
			if (dt.bodyScrollable) {
				$(dt.bodyScrollable).on("scroll.srVatHeading", syncScroll);
				syncScroll(); // pick up current scroll position (e.g. re-render mid-scroll)
			}
		});
	},

	autoFitColumns: function (dt) {
		const datatableWrapper = dt.datatableWrapper;
		if (!datatableWrapper) return;

		const columns = dt.datamanager.getColumns(true);
		if (!columns.length) return;

		columns.forEach((col) => {
			let maxWidth = 120;

			const headerCell = datatableWrapper.querySelector(
				`.dt-cell__content--header-${col.colIndex}`
			);
			if (headerCell) {
				maxWidth = Math.max(maxWidth, headerCell.scrollWidth + 20);
			}

			const dataCells = datatableWrapper.querySelectorAll(
				`.dt-cell__content--col-${col.colIndex}`
			);
			const sampleSize = Math.min(100, dataCells.length);
			for (let i = 0; i < sampleSize; i++) {
				maxWidth = Math.max(maxWidth, dataCells[i].scrollWidth + 20);
			}

			const finalWidth = Math.min(maxWidth, 400);
			dt.datamanager.updateColumn(col.colIndex, { width: finalWidth });
			dt.columnmanager.setColumnHeaderWidth(col.colIndex);
			dt.columnmanager.setColumnWidth(col.colIndex);
		});
	},

	onload: function (_report) {
		if (!document.getElementById("sr-vat-heading-style")) {
			$(`<style id="sr-vat-heading-style">
				/* Outer clips to the datatable's visible width; inner is translateX'd in sync
				   with the datatable's own horizontal scroll, so this group-header row stays
				   glued to the (Nepali-labelled) columns below it instead of drifting out of
				   alignment. */
				.sr-vat-heading-onscreen { margin-bottom: 0; overflow: hidden; }
				.sr-vat-heading-scroll { display: inline-block; }
				.sr-vat-heading-onscreen table { border-collapse: collapse; }
				.sr-vat-heading-onscreen th {
					border: 1px solid var(--gray-400, #d1d8dd);
					background: var(--subtle-fg, #f4f5f6);
					font-weight: 600;
					font-size: 12px;
					padding: 4px 6px;
					overflow: hidden;
					text-overflow: ellipsis;
					white-space: nowrap;
				}
				.sr-vat-heading-onscreen th.r { text-align: right; }
				.sr-vat-heading-onscreen th.l { text-align: left; }
				.sr-vat-heading-onscreen th.c { text-align: center; }
			</style>`).appendTo("head");
		}

		// Company-scoped report. `reqd` can't be used (Company is a MultiSelectList;
		// its empty value [] is truthy, so Frappe's mandatory check never fires), and
		// overriding get_no_result_message / toggle_nothing_to_show gets undone by the
		// shared report_nepali_date.js re-renders. So watch the whole report container
		// and, whenever no Company is set, rewrite the default "Nothing to show" text
		// to a Company prompt. Robust to any re-render / timing.
		const company_chosen = () => {
			const c = _report.get_filter_value("company");
			return Array.isArray(c) ? c.length > 0 : !!c;
		};
		const PROMPT = __("Please set the company first.");
		const NOTHING = __("Nothing to show");
		const root = (_report.page && _report.page.main && _report.page.main[0]) || document.body;

		const swap = () => {
			if (company_chosen()) return;
			root.querySelectorAll("p").forEach((p) => {
				if ((p.textContent || "").trim() === NOTHING) p.textContent = PROMPT;
			});
		};
		new MutationObserver(swap).observe(root, {
			childList: true,
			subtree: true,
			characterData: true,
		});
		swap();

		// Resolve which columns the PRINT pdf should show, matching the report:
		//  1) if "Pick Columns" was used in the print dialog, use those;
		//  2) otherwise use whatever columns are still visible in the datatable
		//     (so removing a column via the datatable menu reflects in the print).
		// Returns [] when all columns are visible => template shows all.
		// NOTE: used by print_report only; the Download PDF button stays "show all".
		const sr_selected_columns = function (print_settings) {
			const cols = frappe.query_report.columns || [];
			const report_fields = new Set(cols.map(c => c.fieldname));

			if (print_settings && print_settings.pick_columns && print_settings.columns && print_settings.columns.length) {
				const by_label = {};
				cols.forEach(c => { by_label[c.label] = c.fieldname; });
				return print_settings.columns
					.map(v => (report_fields.has(v) ? v : by_label[v]))
					.filter(Boolean);
			}

			const dt = frappe.query_report.datatable;
			if (!dt || !dt.datamanager) return [];
			const visible = dt.datamanager.getColumns()
				.map(c => c.fieldname || c.id)
				.filter(fn => report_fields.has(fn));
			// nothing removed -> [] so the template just shows all
			return visible.length === report_fields.size ? [] : visible;
		};

		_report.page.add_inner_button(__('Download PDF'), function () {
			const filters = frappe.query_report.get_filter_values(true);
			if (!filters.from_date || !filters.to_date) {
				frappe.msgprint(__('Please set From Date and To Date'));
				return;
			}
			const url = '/api/method/avinashgroup_app.avinash_group_app.report.sales_register_report.sales_register_report.download_pdf'
				+ '?filters=' + encodeURIComponent(JSON.stringify(filters));
			window.open(url);
		});

		// Excel export needs our own govt-heading builder (merged group headers, PAN/नाम/साल
		// line) — the stock export_query command only dumps flat columns — so replace
		// export_report() with a copy that keeps the same "Export Report" dialog but routes
		// an Excel pick to our endpoint. CSV still goes through the stock flow (no merges to lose).
		_report.export_report = function () {
			if (_report.export_dialog) {
				_report.export_dialog.clear();
				_report.export_dialog.show();
				return;
			}
			const extra_fields = [];
			if (_report.filters.length > 0) {
				extra_fields.push({ label: __('Include filters'), fieldname: 'include_filters', fieldtype: 'Check' });
			}
			_report.export_dialog = frappe.report_utils.get_export_dialog(
				__(_report.report_name),
				extra_fields,
				({ file_format, include_filters, export_in_background, csv_delimiter, csv_quoting }) => {
					_report.make_access_log('Export', file_format);
					const filters = _report.get_filter_values(true);

					if (file_format === 'Excel') {
						const url = '/api/method/avinashgroup_app.avinash_group_app.report.sales_register_report.sales_register_report.download_excel'
							+ '?filters=' + encodeURIComponent(JSON.stringify(filters));
						window.open(url);
						_report.export_dialog.hide();
						return;
					}

					const boolean_labels = { 1: __('Yes'), 0: __('No') };
					const applied_filters = {};
					for (const [key, value] of Object.entries(filters)) {
						const df = _report.get_filter(key).df;
						if (!df.hidden_due_to_dependency) {
							applied_filters[df.label] = df.fieldtype === 'Check' ? boolean_labels[value] : value;
						}
					}
					const visible_idx = _report.datatable?.bodyRenderer.visibleRowIndices || [];
					if (visible_idx.length + 1 === _report.data?.length) {
						visible_idx.push(visible_idx.length);
					}
					const args = {
						cmd: 'frappe.desk.query_report.export_query',
						report_name: _report.report_name,
						custom_columns: _report.custom_columns?.length ? _report.custom_columns : [],
						file_format_type: file_format,
						filters,
						applied_filters,
						visible_idx,
						csv_delimiter,
						csv_quoting,
						include_filters,
						export_in_background,
					};
					if (export_in_background) {
						frappe.call({ method: args.cmd, args });
					} else {
						open_url_post(frappe.request.url, args);
					}
					_report.export_dialog.hide();
				}
			);
			_report.export_dialog.show();
		};

		_report.print_report = function (print_settings) {
			const filters = frappe.query_report.get_filter_values(true);
			if (!filters.from_date || !filters.to_date) {
				frappe.msgprint(__('Please set From Date and To Date'));
				return;
			}
			// Print opens the SAME wkhtmltopdf PDF the Download button produces (orientation
			// from the print dialog). Print and Download are now identical, and printing or
			// saving from the PDF viewer is exact — no browser re-pagination.
			const orientation = (print_settings && print_settings.orientation) || 'Landscape';
			const url = '/api/method/avinashgroup_app.avinash_group_app.report.sales_register_report.sales_register_report.download_pdf'
				+ '?filters=' + encodeURIComponent(JSON.stringify(filters))
				+ '&orientation=' + encodeURIComponent(orientation)
				+ '&selected_columns=' + encodeURIComponent(JSON.stringify(sr_selected_columns(print_settings)))
				+ '&view=1';  // Print → view inline in a new tab (no download)
			window.open(url);
		};

		if (!frappe.ui.get_print_settings._pick_columns_patched) {
			const _orig = frappe.ui.get_print_settings;
			const _our_reports = ['Sales Register Report', 'Purchase Register Report'];
			const _patched = function (pdf, callback, letter_head, pick_columns, has_filters) {
				const report_name = frappe.query_report && frappe.query_report.report_name;
				if (_our_reports.indexOf(report_name) === -1) {
					return _orig(pdf, callback, letter_head, pick_columns, has_filters);
				}
				const _wrappedCb = function (data) {
					if (data.pick_columns && !(data.columns && data.columns.length)) {
						frappe.msgprint({ message: __('Please choose the columns you want to include'), indicator: 'orange' });
						setTimeout(function () {
							frappe.ui.get_print_settings(pdf, callback, letter_head, pick_columns, has_filters);
						}, 150);
						return;
					}
					callback(data);
				};
				const d = _orig(pdf, _wrappedCb, letter_head, pick_columns, has_filters);
				if (d && pick_columns && pick_columns.length) {
					setTimeout(function () { d.set_value('pick_columns', 1); }, 100);
				}
				return d;
			};
			_patched._pick_columns_patched = true;
			frappe.ui.get_print_settings = _patched;
		}
	},

	formatter: function (value, row, column, data, default_formatter) {
		if (!data) return default_formatter(value, row, column, data);

		// बीजक नम्बर shows custom_branch_name (or the SI name) but links by the real
		// SI name (si_name) — get_form_link URL-encodes it, so a name containing "/"
		// (e.g. NGG000007/83-84) resolves instead of 404ing.
		if (column.fieldname === "bill_no" && value && !data.bold) {
			return frappe.utils.get_form_link("Sales Invoice", data.si_name || value, true, value);
		}

		value = default_formatter(value, row, column, data);
		if (data.bold) {
			value = `<strong>${value}</strong>`;
		}
		return value;
	},
};
