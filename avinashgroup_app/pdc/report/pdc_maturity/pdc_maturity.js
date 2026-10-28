frappe.query_reports["PDC Maturity"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company", default: frappe.defaults.get_user_default("Company") },
		{ fieldname: "cheque_type", label: __("Type"), fieldtype: "Select", options: "Received\nIssued", default: "Received", reqd: 1 },
		{ fieldname: "as_on", label: __("As On"), fieldtype: "Date", default: frappe.datetime.get_today(), reqd: 1 },
		{ fieldname: "group_by", label: __("Show"), fieldtype: "Select", options: "Cheque\nParty", default: "Cheque" },
		{ fieldname: "party", label: __("Party"), fieldtype: "Data" },
	],
};
