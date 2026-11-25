// Copyright (c) 2026, Raindrop and contributors
// For license information, please see license.txt

const GAS_STOCK_LEDGER = "Gas Stock Ledger";
const GSL_METHOD =
	"avinashgroup_app.avinash_group_app.report.gas_stock_ledger.gas_stock_ledger.";
const GSL_PRINT_METHOD =
	"avinashgroup_app.avinash_group_app.report.gas_stock_ledger.gas_stock_ledger_print.download_pdf";
const GSL_BS_FORMAT = "YYYY-MM-DD";
// The Nepali months, as Period lists them (fiscal-year order). A Period that is
// one of these is that month of the selected Fiscal Year.
const GSL_BS_MONTHS = [
	"Shrawan",
	"Bhadra",
	"Ashwin",
	"Kartik",
	"Mangsir",
	"Poush",
	"Magh",
	"Falgun",
	"Chaitra",
	"Baisakh",
	"Jestha",
	"Ashadh",
];

// Text colour per movement type, so a long ledger scans by eye.
const GSL_TYPE_COLOURS = {
	purchase: "var(--green-600)",
	purchase_return: "var(--orange-600)",
	sale: "var(--blue-600)",
	sale_return: "var(--orange-600)",
	other: "var(--gray-600)",
};

frappe.query_reports[GAS_STOCK_LEDGER] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			reqd: 1,
			default: frappe.defaults.get_user_default("Company"),
			on_change: function (report) {
				// item and warehouses belong to a company; carry-overs would empty the report
				report.set_filter_value("warehouse", []);
				frappe.query_reports[GAS_STOCK_LEDGER].set_default_item(report, true);
			},
		},
		{
			fieldname: "item_code",
			label: __("Item"),
			fieldtype: "Link",
			options: "Item",
			reqd: 1,
			get_query: function () {
				return {
					filters: {
						is_stock_item: 1,
						disabled: 0,
						custom_company: frappe.query_report.get_filter_value("company"),
					},
				};
			},
			on_change: function (report) {
				// each item has its own UOMs; offer those before running
				frappe.query_reports[GAS_STOCK_LEDGER].load_units(report).then(() => report.refresh());
			},
		},
		{
			fieldname: "view",
			label: __("View"),
			fieldtype: "Select",
			reqd: 1,
			options: [
				"Detail",
				"Daily Summary",
				"Monthly Summary (BS)",
				"Stock Book (मौज्दात खाता)",
				"Refinery Summary",
			].join("\n"),
			default: "Detail",
		},
		{
			// What each block of Detail (and the printed Posting Detail) is
			// headed by, as General Ledger Posting Detail's Group By. The
			// warehouses are one stock kept apart only for the accounts, so Item
			// pools them; Warehouse shows that accounting split.
			fieldname: "group_by",
			label: __("Group By"),
			fieldtype: "Select",
			options: ["Item", "Warehouse", "Party", "Refinery", "Movement"].join("\n"),
			default: "Item",
		},
		{
			// Filled per item from its UOMs (load_units): Transaction UOM, MT, Kg,
			// 5 KG ... 450 KG. Transaction UOM shows each movement in the UOM its
			// voucher was booked in; totals and the balance stay in MT.
			fieldname: "unit",
			label: __("Show Quantity In"),
			fieldtype: "Select",
			options: "Transaction UOM\nMT\nKg",
			default: "Transaction UOM",
		},
		{
			fieldname: "period_preset",
			label: __("Period"),
			fieldtype: "Select",
			reqd: 1,
			// Replaced on load by get_period_options, which adds the year to each
			// month ("Kartik 2083") and says which month This / Last Month is.
			options: [
				"Fiscal Year",
				"Last Fiscal Year",
				"This Fiscal Quarter",
				"Last Fiscal Quarter",
				"This Month",
				"Last Month",
			]
				.concat(GSL_BS_MONTHS)
				.concat(["Today", "Yesterday", "Custom Dates"])
				.join("\n"),
			default: "This Month",
			on_change: function (report) {
				frappe.query_reports[GAS_STOCK_LEDGER].apply_period(report);
			},
		},
		{
			fieldname: "fiscal_year",
			label: __("Fiscal Year"),
			fieldtype: "Link",
			options: "Fiscal Year",
			default: erpnext.utils.get_fiscal_year(frappe.datetime.get_today()),
			on_change: function (report) {
				const me = frappe.query_reports[GAS_STOCK_LEDGER];
				// the months listed are this year's: relabel them, and re-resolve
				// a period that depends on the year
				me.load_periods(report);
				const preset = report.get_filter_value("period_preset");
				if (preset === "Fiscal Year" || GSL_BS_MONTHS.includes(preset)) {
					me.apply_period(report);
				}
			},
		},
		{
			// The period is picked in BS. Each Miti keeps its AD date in step;
			// the AD dates are what the server reads.
			fieldname: "from_miti",
			label: __("From Miti"),
			fieldtype: "Data",
			on_change: function (report) {
				frappe.query_reports[GAS_STOCK_LEDGER].miti_changed(report, "from_miti", "from_date");
			},
		},
		{
			fieldname: "to_miti",
			label: __("To Miti"),
			fieldtype: "Data",
			on_change: function (report) {
				frappe.query_reports[GAS_STOCK_LEDGER].miti_changed(report, "to_miti", "to_date");
			},
		},
		{
			fieldname: "from_date",
			label: __("From Date (AD)"),
			fieldtype: "Date",
			reqd: 1,
			default: frappe.datetime.month_start(),
		},
		{
			fieldname: "to_date",
			label: __("To Date (AD)"),
			fieldtype: "Date",
			reqd: 1,
			default: frappe.datetime.get_today(),
		},
		{
			fieldname: "warehouse",
			label: __("Only Warehouses"),
			fieldtype: "MultiSelectList",
			get_data: function (txt) {
				return frappe.db.get_link_options("Warehouse", txt, {
					company: frappe.query_report.get_filter_value("company"),
					is_group: 0,
				});
			},
		},
		{
			// display filters: they choose the rows shown, the Balance stays the true stock
			fieldname: "voucher_category",
			label: __("Movement"),
			fieldtype: "Select",
			options: [
				"",
				"Purchase",
				"Purchase Return",
				"Sale",
				"Sale Return",
				"Transfer / Adjustment",
			].join("\n"),
		},
		{
			// options come from the Purchase Invoice field (load_refineries)
			fieldname: "refinery",
			label: __("Refinery"),
			fieldtype: "Select",
			options: "",
		},
		{
			fieldname: "customer",
			label: __("Customer"),
			fieldtype: "Link",
			options: "Customer",
		},
		{
			fieldname: "supplier",
			label: __("Supplier"),
			fieldtype: "Link",
			options: "Supplier",
		},
		{
			fieldname: "branch",
			label: __("Branch"),
			fieldtype: "Link",
			options: "Branch",
		},
		{
			fieldname: "show_cylinders",
			label: __("Cylinder Columns"),
			fieldtype: "Check",
			default: 1,
		},
		{
			fieldname: "show_value",
			label: __("Show Value"),
			fieldtype: "Check",
			default: 1,
		},
		{
			// the remark written on each voucher (Sales / Purchase Invoice
			// remarks), on screen and in both prints
			fieldname: "show_narration",
			label: __("Show Narration"),
			fieldtype: "Check",
			default: 1,
		},
	],

	formatter: function (value, row, column, data, default_formatter) {
		if (!data) return default_formatter(value, row, column, data);

		// Detail, laid out as General Ledger Posting Detail's screen. The
		// sub-line and the narration sit whole in the Voucher Type cell and
		// spill right across the empty cells (the datatable has no colspan);
		// absolutely positioned so Fit Columns does not size a column by them.
		if (data._narration || data._subline) {
			if (column.fieldname === "voucher_type") {
				const italic = data._narration ? "font-style:italic;" : "";
				return `<span style="position:absolute;left:8px;top:50%;transform:translateY(-50%);
					white-space:nowrap;color:#6b7280;${italic}pointer-events:none;">${frappe.utils.escape_html(
					data.voucher_type || ""
				)}</span>`;
			}
			return "";
		}
		if (data._spacer) return "";
		if (data._section) {
			return column.fieldname === "party_name"
				? `<b>${frappe.utils.escape_html(data.party_name || "")}</b>`
				: "";
		}
		// a band carries only the figures it means; a missing one is blank,
		// not a 0.000 that reads as a real zero
		if (data._band && (value === undefined || value === null) && column.fieldname !== "party_name") {
			return "";
		}
		if (["in_qty", "out_qty"].includes(column.fieldname) && !data._band && !value) {
			return "";
		}

		if (["in_qty", "out_qty"].includes(column.fieldname) && data.qty_precision !== undefined) {
			// Transaction UOM: a cylinder count reads 120, a weight 18.000
			column = Object.assign({}, column, { precision: data.qty_precision });
		}
		value = default_formatter(value, row, column, data);

		if (data.is_heading) {
			return `<b style="color: var(--heading-color)">${value}</b>`;
		}
		if (["type", "voucher_type"].includes(column.fieldname) && data.category && value) {
			value = `<span style="color:${GSL_TYPE_COLOURS[data.category]};font-weight:500">${value}</span>`;
		}
		if (
			["balance", "balance_qty", "closing_qty", "opening_qty", "balance_value", "closing_value"].includes(
				column.fieldname
			) &&
			data[column.fieldname] < 0
		) {
			value = `<span style="color: var(--red-600)">${value}</span>`;
		}
		if (data.bold || data._bold) {
			value = `<b>${value}</b>`;
		}
		return value;
	},

	// Sizes columns to their content, leaving the spill-over lines out of the
	// measure (they are meant to overflow), and gives the slack to Party
	// Name/Description -- General Ledger Posting Detail's own Fit Columns.
	// Defining autoFitColumns makes rdp_common_app's shared control step aside.
	autoFitColumns: function (dt) {
		const wrapper = dt && dt.datatableWrapper;
		const report = frappe.query_report;
		if (!wrapper || !report || report.get_filter_value("view") !== "Detail") return;

		const columns = dt.datamanager.getColumns(true) || [];
		const data = report.data || [];
		const spill = new Set();
		data.forEach((row, i) => {
			if (row && (row._narration || row._subline)) spill.add(i);
		});

		const FLOOR = { in_qty: 100, out_qty: 100, balance: 120, value: 130 };
		const widths = {};
		columns.forEach((col) => {
			let width = FLOOR[col.fieldname] || 80;
			const header = wrapper.querySelector(".dt-cell__content--header-" + col.colIndex);
			if (header) width = Math.max(width, header.scrollWidth + 20);
			const cells = wrapper.querySelectorAll(".dt-cell__content--col-" + col.colIndex);
			for (let i = 0; i < Math.min(100, cells.length); i++) {
				const rowEl = cells[i].closest("[class*='dt-row-']");
				const match = rowEl && /dt-row-(\d+)/.exec(rowEl.className);
				if (match && spill.has(parseInt(match[1], 10))) continue;
				width = Math.max(width, cells[i].scrollWidth + 20);
			}
			widths[col.colIndex] = Math.min(width, 340);
		});

		const available = (dt.bodyScrollable && dt.bodyScrollable.clientWidth) || 0;
		const used = Object.values(widths).reduce((a, b) => a + b, 0);
		const description = columns.find((c) => c.fieldname === "party_name");
		if (description && available && used < available - 24) {
			widths[description.colIndex] += available - used - 24;
		}
		columns.forEach((col) => {
			dt.datamanager.updateColumn(col.colIndex, { width: widths[col.colIndex] });
			dt.columnmanager.setColumnHeaderWidth(col.colIndex);
			dt.columnmanager.setColumnWidth(col.colIndex);
		});
		if (dt.style && dt.style.setBodyStyle) dt.style.setBodyStyle();
	},

	// Lift overflow on the spill-over rows so their line can run across.
	tagSpillRows: function (dt) {
		const data = (frappe.query_report && frappe.query_report.data) || [];
		const container = dt && dt.bodyScrollable;
		if (!container) return;
		data.forEach((row, i) => {
			if (!row || !(row._narration || row._subline)) return;
			const rowEl = container.querySelector(".dt-row-" + i);
			if (rowEl) rowEl.classList.add("gsl-spill-row");
		});
	},

	after_datatable_render: function (dt) {
		const me = frappe.query_reports[GAS_STOCK_LEDGER];
		me.tagSpillRows(dt);
		// after the datatable's own sizing pass, or these widths are overwritten
		window.requestAnimationFrame(() => setTimeout(() => me.autoFitColumns(dt), 150));
		// rows are virtualised: scrolling recreates them without the class
		const container = dt && dt.bodyScrollable;
		if (!container || container._gslBound) return;
		container._gslBound = true;
		let scheduled = false;
		container.addEventListener("scroll", () => {
			if (scheduled) return;
			scheduled = true;
			window.requestAnimationFrame(() => {
				scheduled = false;
				me.tagSpillRows(dt);
			});
		});
	},

	// Show only the date fields the chosen Period needs, and resolve its dates
	// (BS month and quarter boundaries, same presets as Custom Ledger).
	apply_period: function (report) {
		const me = frappe.query_reports[GAS_STOCK_LEDGER];
		const preset = report.get_filter_value("period_preset") || "This Month";
		const by_year = preset === "Fiscal Year";
		const custom = preset === "Custom Dates";
		// Without the Nepali calendar the Miti pickers cannot work; fall back
		// to the AD dates rather than leave Custom Dates with no way in.
		const bs = me.has_bs();

		const named_month = GSL_BS_MONTHS.includes(preset);
		const by_month = named_month || preset === "This Month" || preset === "Last Month";

		// a named month belongs to a fiscal year, so its year stays in view
		report.get_filter("fiscal_year").toggle(by_year || named_month);
		report.get_filter("from_miti").toggle(custom && bs);
		report.get_filter("to_miti").toggle(custom && bs);
		report.get_filter("from_date").toggle(custom && !bs);
		report.get_filter("to_date").toggle(custom && !bs);

		if (custom) {
			report.refresh();
			return;
		}

		if (by_year) {
			const fy =
				report.get_filter_value("fiscal_year") ||
				erpnext.utils.get_fiscal_year(frappe.datetime.get_today());
			frappe.model.with_doc("Fiscal Year", fy, function () {
				const doc = frappe.model.get_doc("Fiscal Year", fy);
				if (!doc) return;
				me.set_period(report, doc.year_start_date, doc.year_end_date, { fiscal_year: fy });
			});
			return;
		}

		if (by_month) {
			frappe
				.call({
					method: GSL_METHOD + "get_bs_month_period",
					args: { preset: preset, fiscal_year: report.get_filter_value("fiscal_year") },
				})
				.then((r) => {
					if (r.message) me.set_period(report, r.message.from_date, r.message.to_date);
				});
			return;
		}

		frappe
			.call({
				method:
					"avinashgroup_app.avinash_group_app.report.custom_ledger.custom_ledger.get_period",
				args: { preset: preset, company: report.get_filter_value("company") },
			})
			.then((r) => {
				if (r.message && r.message.from_date) {
					me.set_period(report, r.message.from_date, r.message.to_date);
				}
			});
	},

	// Period's choices with their years: "This Month (Mangsir 2083)",
	// "Shrawan 2083" ... "Ashadh 2084" for the selected fiscal year. Values stay
	// the plain names, so the chosen period survives the relabel.
	load_periods: function (report) {
		return frappe
			.call({
				method: GSL_METHOD + "get_period_options",
				args: { fiscal_year: report.get_filter_value("fiscal_year") },
			})
			.then((r) => {
				if (!r.message || !r.message.length) return;
				const filter = report.get_filter("period_preset");
				filter.df.options = r.message;
				filter.refresh();
			});
	},

	has_bs: function () {
		return !!(window.NepaliFunctions && window.NepaliFunctions.AD2BS);
	},

	to_bs: function (ad) {
		if (!ad || !this.has_bs()) return "";
		try {
			return window.NepaliFunctions.AD2BS(ad, GSL_BS_FORMAT);
		} catch (e) {
			return "";
		}
	},

	to_ad: function (bs) {
		if (!bs || !this.has_bs()) return "";
		try {
			return window.NepaliFunctions.BS2AD(bs, GSL_BS_FORMAT);
		} catch (e) {
			return "";
		}
	},

	// A preset sets both calendars at once; the AD dates go last so the one
	// refresh runs with the period complete.
	set_period: function (report, from_date, to_date, extra) {
		report.set_filter_value(
			Object.assign({}, extra || {}, {
				from_miti: this.to_bs(from_date),
				to_miti: this.to_bs(to_date),
				from_date: from_date,
				to_date: to_date,
			})
		);
	},

	// A Miti typed or picked moves its AD date, which re-runs the report. A
	// Miti that already matches its AD date is a preset's echo: nothing to do.
	miti_changed: function (report, miti_field, date_field) {
		const bs = report.get_filter_value(miti_field);
		const ad = this.to_ad(bs);
		if (!ad) {
			if (bs) frappe.show_alert({ message: __("{0} is not a valid Miti", [bs]), indicator: "orange" });
			return;
		}
		if (ad !== report.get_filter_value(date_field)) {
			report.set_filter_value(date_field, ad);
		}
	},

	// Opens the Nepali calendar on a Miti filter. The picker writes into the
	// input without telling Frappe, so the value is pushed in by hand
	// (same as Debtors Summary).
	attach_bs_picker: function (report, fieldname) {
		const filter = report.get_filter(fieldname);
		const input = filter && filter.$input && filter.$input[0];
		if (!input || typeof input.NepaliDatePicker !== "function" || input._gsl_picker) return;
		input._gsl_picker = true;
		input.NepaliDatePicker({
			ndpYear: true,
			ndpMonth: true,
			dateFormat: GSL_BS_FORMAT,
			onSelect: function () {
				report.set_filter_value(fieldname, input.value);
			},
		});
	},

	// The units the chosen item can be read in. Keeps the current unit when
	// the new item has it, else falls back to the first (Transaction UOM).
	load_units: function (report) {
		const item = report.get_filter_value("item_code");
		if (!item) return Promise.resolve();
		return frappe.call({ method: GSL_METHOD + "get_units", args: { item_code: item } }).then((r) => {
			const units = r.message || [];
			if (!units.length) return;
			const filter = report.get_filter("unit");
			filter.df.options = units.join("\n");
			filter.refresh();
			const current = report.get_filter_value("unit");
			if (!units.includes(current)) {
				filter.set_input(units[0]);
			}
		});
	},

	load_refineries: function (report) {
		return frappe.call({ method: GSL_METHOD + "get_refineries" }).then((r) => {
			const filter = report.get_filter("refinery");
			filter.df.options = [""].concat(r.message || []).join("\n");
			filter.refresh();
		});
	},

	// Open on the company's LP Gas item -- it is what everyone asks about.
	set_default_item: function (report, replace) {
		const company = report.get_filter_value("company");
		if (!company || (!replace && report.get_filter_value("item_code"))) return;
		frappe
			.call({ method: GSL_METHOD + "get_default_item", args: { company: company } })
			.then((r) => report.set_filter_value("item_code", r.message || ""));
	},

	onload: function (report) {
		const me = frappe.query_reports[GAS_STOCK_LEDGER];
		if (!document.getElementById("gsl-spill-style")) {
			const style = document.createElement("style");
			style.id = "gsl-spill-style";
			style.textContent = `
				.gsl-spill-row .dt-cell { overflow: visible !important; }
				.gsl-spill-row .dt-cell__content {
					overflow: visible !important; white-space: nowrap; position: relative; z-index: 5;
				}`;
			document.head.appendChild(style);
		}
		me.attach_bs_picker(report, "from_miti");
		me.attach_bs_picker(report, "to_miti");
		me.load_refineries(report);
		me.load_periods(report);
		me.load_units(report);
		me.apply_period(report);
		me.set_default_item(report, false);

		// Every way to print gives the legacy Posting Detail page (company, period,
		// item, blocks, Report Parameters), as General Ledger Posting Detail
		// prints. The desk's own Menu > Print / PDF would dump the bare table with
		// no company and no filters, so both are pointed here too.
		const open_print = function (style) {
			const filters = report.get_values();
			if (!filters || !filters.company || !filters.item_code) {
				frappe.msgprint(__("Please select a Company and an Item."));
				return;
			}
			window.open(
				"/api/method/" + GSL_PRINT_METHOD +
					"?filters=" + encodeURIComponent(JSON.stringify(filters)) +
					"&style=" + (style || "standard")
			);
		};
		report.print_report = () => open_print("standard");
		report.pdf_report = () => open_print("standard");
		report.page.add_inner_button(__("Print"), () => open_print("standard"));
		report.page.add_inner_button(__("Standard"), () => open_print("standard"), __("Download PDF"));
		report.page.add_inner_button(
			__("Legacy Posting Detail"),
			() => open_print("legacy"),
			__("Download PDF")
		);
	},
};
