// Copyright (c) 2026, Raindrop and contributors
// For license information, please see license.txt

frappe.query_reports["Receipt Register"] = {
	filters: [
		{
			fieldname: "view",
			label: __("View"),
			fieldtype: "Select",
			options: ["Customer - Date Wise", "Customer - Customer Wise", "Customer Wise Summary"].join("\n"),
			default: "Customer - Date Wise",
			reqd: 1,
			on_change: function () {
				frappe.query_report.refresh();
			},
		},
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
			reqd: 1,
			on_change: function () {
				frappe.query_report.set_filter_value("customer", []);
				frappe.query_report.set_filter_value("bank", []);
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
			fieldname: "customer",
			label: __("Customer"),
			fieldtype: "MultiSelectList",
			get_data: function (txt) {
				const company = frappe.query_report.get_filter_value("company");
				return frappe
					.call({
						method: "avinashgroup_app.avinash_group_app.report.receipt_register.receipt_register.get_company_customers",
						args: { company: company, txt: txt },
					})
					.then((r) => r.message || []);
			},
		},
		{
			fieldname: "bank",
			label: __("Bank / Cash Account"),
			fieldtype: "MultiSelectList",
			get_data: function (txt) {
				const company = frappe.query_report.get_filter_value("company");
				return frappe
					.call({
						method: "avinashgroup_app.avinash_group_app.report.receipt_register.receipt_register.get_company_bank_accounts",
						args: { company: company, txt: txt },
					})
					.then((r) => r.message || []);
			},
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

	onload: function () {
		// Inject the customer-header banner CSS once. The first data cell's content is
		// allowed to overflow across the row (other header cells are empty + same shade),
		// giving a merged-row look without touching column widths.
		if (document.getElementById("rr-cust-header-style")) return;
		const style = document.createElement("style");
		style.id = "rr-cust-header-style";
		style.textContent = `
			.rr-cust-header-row .dt-cell { background: #f2f2f2 !important; overflow: visible !important; }
			.rr-cust-header-row .dt-cell__content { overflow: visible !important; }
			.rr-cust-header-row .dt-cell__content--col-1 { white-space: nowrap; font-weight: bold; position: relative; z-index: 10; }
		`;
		document.head.appendChild(style);
	},

	get_datatable_options(options) {
		// We render our own S.N. column, so drop the datatable's auto serial-number column.
		return Object.assign(options, { serialNoColumn: false });
	},

	after_datatable_render: function (dt) {
		const me = this;
		const fit = frappe.query_report.get_filter_value("fit_columns");
		// Auto-fit FIRST (resizes columns), then merge the customer-header rows so the
		// banner spans the fitted widths.
		setTimeout(function () {
			if (fit) me.autoFitColumns(dt);
			me.mergeCustomerHeaders(dt);
		}, 100);
	},

	autoFitColumns: function (dt) {
		const wrapper = dt.datatableWrapper;
		if (!wrapper) return;
		const columns = dt.datamanager.getColumns(true);
		if (!columns.length) return;

		columns.forEach((col) => {
			let maxWidth = 60;
			const header = wrapper.querySelector(`.dt-cell__content--header-${col.colIndex}`);
			if (header) maxWidth = Math.max(maxWidth, header.scrollWidth + 20);
			const cells = wrapper.querySelectorAll(`.dt-cell__content--col-${col.colIndex}`);
			const sample = Math.min(100, cells.length);
			for (let i = 0; i < sample; i++) maxWidth = Math.max(maxWidth, cells[i].scrollWidth + 20);

			let finalWidth = Math.min(maxWidth, 400);
			if (col.id === "sn") finalWidth = Math.min(finalWidth, 50);
			dt.datamanager.updateColumn(col.colIndex, { width: finalWidth });
			dt.columnmanager.setColumnHeaderWidth(col.colIndex);
			dt.columnmanager.setColumnWidth(col.colIndex);
		});
	},

	mergeCustomerHeaders: function (dt) {
		// Customer Wise: tag each customer-header row so CSS can render it as a full-width
		// banner. We DON'T resize or hide cells (that fought Fit Columns and mangled the
		// Net Amount column) — instead the combined "Code — Name" in the first data cell is
		// allowed to spill across the (uniformly shaded, empty) cells to its right.
		const data = frappe.query_report.data || [];
		const container = dt && dt.bodyScrollable;
		if (!container) return;
		data.forEach(function (row, i) {
			if (!row || !row.is_customer_header) return;
			const rowEl = container.querySelector(".dt-row-" + i);
			if (rowEl) rowEl.classList.add("rr-cust-header-row");
		});
	},

	formatter: function (value, row, column, data, default_formatter) {
		// Customer Wise: Code in the Date column, Name in the Miti column (left identifiers).
		if (data && data.is_customer_header) {
			if (column.fieldname === "sn") return `<b>${frappe.utils.escape_html(String(data.sn || ""))}</b>`;
			// Combined Code — Name goes in the first data cell; after_datatable_render then
			// stretches that cell across the whole row (a full-width merged banner).
			if (column.fieldname === "date") return `<b>${frappe.utils.escape_html(data.cust_combined || "")}</b>`;
			return "";
		}
		// Voucher Number shows custom_name but links to the real Payment Entry.
		if (column.fieldname === "voucher_no" && data && data.voucher_link && value) {
			return `<a href="/app/payment-entry/${encodeURIComponent(data.voucher_link)}" target="_blank">${value}</a>`;
		}
		// Cheque/Remarks sub-line — muted; no amount (don't render Rs 0.00).
		if (data && data.is_sub) {
			if (column.fieldname === "net_amount") return "";
			return `<span style="color:#777;">${default_formatter(value, row, column, data)}</span>`;
		}
		value = default_formatter(value, row, column, data);
		// Total / Grand Total — bold.
		if (data && data.bold) value = `<b>${value}</b>`;
		return value;
	},
};
