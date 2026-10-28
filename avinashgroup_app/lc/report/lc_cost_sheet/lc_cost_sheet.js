frappe.query_reports["LC Cost Sheet"] = {
	filters: [
		{ fieldname: "letter_of_credit", label: __("Letter of Credit"), fieldtype: "Link", options: "Letter of Credit", reqd: 1,
			get_query: () => ({ filters: { docstatus: 1 } }) },
	],
};
