frappe.query_reports["LC Cost Sheet"] = {
	filters: [
		{ fieldname: "letter_of_credit", label: __("Letter of Credit"), fieldtype: "Link", options: "Letter of Credit", reqd: 1,
			get_query: () => ({ filters: { docstatus: 1 } }) },
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (data && data.bold) value = `<b>${value}</b>`;
		return value;
	},
};
