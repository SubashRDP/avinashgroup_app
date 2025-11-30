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
            fieldname: "vehicle_no",
            label: __("Vehicle No"),
            fieldtype: "Link",
            options: "Sub-Ledger Category",
            get_query: function () {
                return {
                    filters: {
                        parent_sub_ledger_category: "Vehicle"
                    }
                };
            }
        },
        {
            fieldname: "fiscal_year",
            label: __("Fiscal Year"),
            fieldtype: "Link",
            options: "Fiscal Year",
            reqd: 0,
        },
        {
            fieldname: "department",
            label: __("Department"),
            fieldtype: "Link",
            options: "Department",
            reqd: 0,
            get_query: function () {
                let company = frappe.query_report.get_filter_value("company");
                if (company) {
                    return {
                        filters: {
                            company: company
                        }
                    };
                }
            }
        },
        {
            fieldname: "period_start_date",
            label: __("Start Date"),
            fieldtype: "Date",
            reqd: 0
        },
        {
            fieldname: "period_end_date",
            label: __("End Date"),
            fieldtype: "Date",
            reqd: 0
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
        // Set up company filter change handler
        report.page.fields_dict.company.df.onchange = function() {
            let company = report.get_filter_value("company");
            
            // Clear department when company changes
            if (company) {
                report.set_filter_value("department", "");
                
                // Refresh department field to apply new query
                let dept_field = report.page.fields_dict.department;
                if (dept_field) {
                    dept_field.refresh();
                }
            }
        };
    }
};