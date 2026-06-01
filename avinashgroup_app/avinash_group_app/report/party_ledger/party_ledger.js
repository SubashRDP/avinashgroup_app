// Copyright (c) 2026, Raindrop and contributors
// For license information, please see license.txt

frappe.query_reports["Party Ledger"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
			reqd: 1,
		},
		{
			fieldname: "party_type",
			label: __("Party Type"),
			fieldtype: "Select",
			options: "\nCustomer\nSupplier",
			default: "Customer",
			on_change: function () {
				frappe.query_report.set_filter_value("party", []);
			},
		},
		{
			fieldname: "party",
			label: __("Party"),
			fieldtype: "MultiSelectList",
			options: "party_type",
			get_data: function (txt) {
				if (!frappe.query_report.filters) return;
				let party_type = frappe.query_report.get_filter_value("party_type") || "Customer";
				let company = frappe.query_report.get_filter_value("company");
				if (!company) {
					return frappe.db.get_link_options(party_type, txt);
				}
				return frappe
					.call({
						method: "avinashgroup_app.avinash_group_app.report.party_ledger.party_ledger.get_company_parties",
						args: { party_type, company, txt },
					})
					.then((r) => r.message || []);
			},
		},
		{
			fieldname: "account",
			label: __("Account"),
			fieldtype: "MultiSelectList",
			options: "Account",
			get_data: function (txt) {
				const company = frappe.query_report.get_filter_value("company");
				const filters = { is_group: 0 };
				if (company) filters.company = company;
				return frappe.db.get_link_options("Account", txt, filters);
			},
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.month_start(),
			reqd: 1,
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.now_date(),
			reqd: 1,
		},
		{
			fieldname: "voucher_no",
			label: __("Voucher No"),
			fieldtype: "Data",
		},
		{
			fieldname: "show_remarks",
			label: __("Show Remarks"),
			fieldtype: "Check",
			default: 0,
			on_change: function () {
				frappe.query_report.refresh();
			},
		},
		{
			fieldname: "detailed_mapping",
			label: __("Detailed Mapping"),
			fieldtype: "Check",
			default: 0,
			on_change: function () {
				frappe.query_report.refresh();
			},
		},
		{
			fieldname: "fit_columns",
			label: __("Fit Columns"),
			fieldtype: "Check",
			default: 0,
			on_change: function () {
				frappe.query_report.refresh();
			},
		},
	],

	get_datatable_options(options) {
		return Object.assign(options, { layout: "fixed", serialNoColumn: false, freezeColumnsTo: 4 });
	},

	after_datatable_render: function (dt) {
		const fit = frappe.query_report.get_filter_value("fit_columns");
		if (fit) {
			setTimeout(() => this.autoFitColumns(dt), 100);
		}
		this._initDragScroll(dt);
	},

	_initDragScroll: function (dt) {
		const scrollable = dt.bodyScrollable;
		if (!scrollable || scrollable._dragScrollBound) return;
		scrollable._dragScrollBound = true;

		let isDragging = false;
		let startX, startY, scrollLeft, scrollTop;

		scrollable.addEventListener("mousedown", (e) => {
			if (e.button !== 0) return;
			if (e.target.closest("a, button, input, select")) return;
			isDragging = true;
			startX = e.pageX - scrollable.offsetLeft;
			startY = e.pageY - scrollable.offsetTop;
			scrollLeft = scrollable.scrollLeft;
			scrollTop = scrollable.scrollTop;
			scrollable.style.cursor = "grabbing";
			scrollable.style.userSelect = "none";
			e.preventDefault();
		});

		document.addEventListener("mousemove", (e) => {
			if (!isDragging) return;
			const dx = e.pageX - scrollable.offsetLeft - startX;
			const dy = e.pageY - scrollable.offsetTop - startY;
			scrollable.scrollLeft = scrollLeft - dx;
			scrollable.scrollTop = scrollTop - dy;
		});

		document.addEventListener("mouseup", () => {
			if (!isDragging) return;
			isDragging = false;
			scrollable.style.cursor = "grab";
			scrollable.style.userSelect = "";
		});

		scrollable.style.cursor = "grab";
	},

	autoFitColumns: function (dt) {
		const datatableWrapper = dt.datatableWrapper;
		if (!datatableWrapper) return;

		const columns = dt.datamanager.getColumns(true);
		if (!columns.length) return;

		columns.forEach((col) => {
			let maxWidth = Math.max(col.width || 60, 60);

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

			let finalWidth = Math.min(maxWidth, 400);
			if (col.id === "sr_no")       finalWidth = Math.min(finalWidth, 52);
			if (col.id === "date")        finalWidth = Math.min(finalWidth, 110);
			if (col.id === "miti")        finalWidth = Math.min(finalWidth, 110);
			if (col.id === "description") finalWidth = Math.max(finalWidth, 420);
			if (col.id === "remarks")     finalWidth = Math.min(finalWidth, 150);
			dt.datamanager.updateColumn(col.colIndex, { width: finalWidth });
			dt.columnmanager.setColumnHeaderWidth(col.colIndex);
			dt.columnmanager.setColumnWidth(col.colIndex);
		});
	},

	onload: function (_report) {
		_report.page.add_inner_button(__('Download PDF'), function () {
			const filters = frappe.query_report.get_filter_values(true);
			if (!filters.company || !filters.from_date || !filters.to_date) {
				frappe.msgprint(__('Please set Company, From Date and To Date'));
				return;
			}
			const url = '/api/method/avinashgroup_app.avinash_group_app.report.party_ledger.party_ledger.download_pdf'
				+ '?filters=' + encodeURIComponent(JSON.stringify(filters));
			window.open(url);
		});
	},

	formatter: function (value, row, column, data, default_formatter) {
		if (!data) return default_formatter(value, row, column, data);
		if (["detail_qty","detail_rate","detail_amount"].includes(column.fieldname) && !data.is_detail) {
			return "";
		}
		if (column.fieldname === "voucher_no" && data.voucher_type && value) {
			const route = frappe.router.slug(data.voucher_type);
			return `<a href="/app/${route}/${value}" target="_blank">${value}</a>`;
		}
		return default_formatter(value, row, column, data);
	},
};
