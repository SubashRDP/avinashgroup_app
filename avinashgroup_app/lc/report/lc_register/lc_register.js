frappe.query_reports["LC Register"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company", default: frappe.defaults.get_user_default("Company") },
		{ fieldname: "supplier", label: __("Beneficiary"), fieldtype: "Link", options: "Supplier" },
		{ fieldname: "bank", label: __("Bank"), fieldtype: "Link", options: "Bank" },
		{ fieldname: "status", label: __("Status"), fieldtype: "Select", options: "\nApplied\nOpened\nPartly Settled\nSettled\nClosed\nExpired" },
		{ fieldname: "from_date", label: __("Applied From"), fieldtype: "Date" },
		{ fieldname: "to_date", label: __("Applied To"), fieldtype: "Date" },
		{ fieldname: "show_closed", label: __("Include Closed"), fieldtype: "Check" },
	],
};
