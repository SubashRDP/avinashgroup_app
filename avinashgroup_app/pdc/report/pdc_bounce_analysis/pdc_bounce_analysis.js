frappe.query_reports["PDC Bounce Analysis"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company", default: frappe.defaults.get_user_default("Company") },
		{ fieldname: "cheque_type", label: __("Type"), fieldtype: "Select", options: "Received\nIssued", default: "Received" },
		{ fieldname: "from_date", label: __("From"), fieldtype: "Date", default: frappe.datetime.add_months(frappe.datetime.get_today(), -12), reqd: 1 },
		{ fieldname: "to_date", label: __("To"), fieldtype: "Date", default: frappe.datetime.get_today(), reqd: 1 },
		{ fieldname: "show_all", label: __("Include Parties With No Bounce"), fieldtype: "Check" },
	],
};
