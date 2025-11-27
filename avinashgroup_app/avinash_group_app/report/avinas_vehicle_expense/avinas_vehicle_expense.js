function get_filters() {
    let filters = [
        {
            fieldname: "company",
            label: __("Company"),
            fieldtype: "Link",
            options: "Company",
            default: frappe.defaults.get_user_default("Company"),
            reqd: 1,
        },
        {
            fieldname: "department",
            label: __("Department"),
            fieldtype: "Link",
            options: "Department",
            reqd: 0,
        },
        {
            fieldname: "period_start_date",
            label: __("Start Date"),
            fieldtype: "Date",
            hidden: 0,
            reqd: 0,
        },
        {
            fieldname: "period_end_date",
            label: __("End Date"),
            fieldtype: "Date",
            hidden: 0,
            reqd: 0,
        },
    ];
    return filters;
}

frappe.query_reports["Avinas Vehicle Expense"] = {
    filters: get_filters(),
    formatter: function (value, row, column, data, default_formatter) {
        return default_formatter(value, row, column, data);
    },
    onload: function (report) {
        let fiscal_year = erpnext.utils.get_fiscal_year(frappe.datetime.get_today());
        frappe.model.with_doc("Fiscal Year", fiscal_year, function (r) {
            let fy = frappe.model.get_doc("Fiscal Year", fiscal_year);
            
            // Set default date range from fiscal year
            if (fy.year_start_date && fy.year_end_date) {
                frappe.query_report.set_filter_value({
                    "period_start_date": fy.year_start_date,
                    "period_end_date": fy.year_end_date
                });
            }
        });

        // Filter department based on selected company
        frappe.query_report.filter_area.get("company").on("change", function (e) {
            let company = frappe.query_report.get_filter_value("company");
            if (company) {
                frappe.query_report.filter_area.get("department").df.query = {
                    filters: {
                        "company": company
                    }
                };
                frappe.query_report.filter_area.get("department").refresh();
                frappe.query_report.set_filter_value("department", "");
            }
        });
    },
};