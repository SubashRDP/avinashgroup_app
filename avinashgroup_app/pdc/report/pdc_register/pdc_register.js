frappe.query_reports["PDC Register"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company", default: frappe.defaults.get_user_default("Company") },
		{ fieldname: "cheque_type", label: __("Type"), fieldtype: "Select", options: "\nReceived\nIssued" },
		{
			fieldname: "status",
			label: __("Status"),
			fieldtype: "Select",
			options: "\nIn Hand\nIssued\nDeposited\nCleared\nBounced\nReturned\nReplaced\nCancelled",
		},
		{ fieldname: "party_type", label: __("Party Type"), fieldtype: "Select", options: "\nCustomer\nSupplier" },
		{ fieldname: "party", label: __("Party"), fieldtype: "Dynamic Link", options: "party_type" },
		{ fieldname: "from_date", label: __("Cheque Date From"), fieldtype: "Date", default: frappe.datetime.add_months(frappe.datetime.get_today(), -1) },
		{ fieldname: "to_date", label: __("Cheque Date To"), fieldtype: "Date", default: frappe.datetime.add_months(frappe.datetime.get_today(), 2) },
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "status" && data) {
			const colour = { Cleared: "green", Bounced: "red", Deposited: "blue" }[data.status];
			if (colour) value = `<span class="indicator-pill ${colour}">${value}</span>`;
		}
		return value;
	},
};
