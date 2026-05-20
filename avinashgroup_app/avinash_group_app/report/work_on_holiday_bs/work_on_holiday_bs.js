frappe.query_reports["Work On Holiday BS"] = {
	filters: [
		{
			fieldname: "fiscal_year",
			label: __("Fiscal Year"),
			fieldtype: "Link",
			options: "Fiscal Year",
			reqd: 1,
			default: frappe.defaults.get_user_default("fiscal_year"),
			description: __("BS fiscal year, e.g. 82/83 covering Shrawan 2082 to Ashad 2083."),
		},
		{
			fieldname: "ot_eligibility",
			label: __("OT Eligibility"),
			fieldtype: "Select",
			options: "All\nNo\nYes",
			default: "All",
			description: __("Defaults to All to mirror the source Excel sheet, which lists every staff member regardless of OT eligibility. Pick 'No' to limit to staff whose holiday work is tracked for compensatory accounting."),
		},
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
		},
		{
			fieldname: "department",
			label: __("Department"),
			fieldtype: "Link",
			options: "Department",
		},
		{
			fieldname: "branch",
			label: __("Branch"),
			fieldtype: "Link",
			options: "Branch",
		},
		{
			fieldname: "employee",
			label: __("Employee"),
			fieldtype: "Link",
			options: "Employee",
		},
		{
			fieldname: "status",
			label: __("Employee Status"),
			fieldtype: "Select",
			options: "\nActive\nInactive\nLeft",
			default: "Active",
		},
	],
};
