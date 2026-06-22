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
            fieldname: "date_filter_type",
            label: __("Filter By"),
            fieldtype: "Select",
            options: ["Fiscal Year", "Date Range"],
            default: "Fiscal Year",
            reqd: 1,
        },
        {
            fieldname: "fiscal_year",
            label: __("Fiscal Year"),
            fieldtype: "Link",
            options: "Fiscal Year",
            reqd: 0,
            depends_on: "eval:doc.date_filter_type=='Fiscal Year'"
        },
        {
            fieldname: "period_start_date",
            label: __("Start Date"),
            fieldtype: "Date",
            reqd: 0,
            depends_on: "eval:doc.date_filter_type=='Date Range'"
        },
        {
            fieldname: "period_end_date",
            label: __("End Date"),
            fieldtype: "Date",
            reqd: 0,
            depends_on: "eval:doc.date_filter_type=='Date Range'"
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
        // Set up date filter type change handler
        report.page.fields_dict.date_filter_type.df.onchange = function() {
            let filter_type = report.get_filter_value("date_filter_type");
            
            if (filter_type === "Fiscal Year") {
                // Clear date range fields
                report.set_filter_value("period_start_date", "");
                report.set_filter_value("period_end_date", "");
                
                // Show fiscal year, hide date range
                report.page.fields_dict.fiscal_year.df.hidden = 0;
                report.page.fields_dict.period_start_date.df.hidden = 1;
                report.page.fields_dict.period_end_date.df.hidden = 1;
            } else if (filter_type === "Date Range") {
                // Clear fiscal year field
                report.set_filter_value("fiscal_year", "");
                
                // Show date range, hide fiscal year
                report.page.fields_dict.fiscal_year.df.hidden = 1;
                report.page.fields_dict.period_start_date.df.hidden = 0;
                report.page.fields_dict.period_end_date.df.hidden = 0;
            }
            
            // Refresh all affected fields
            report.page.fields_dict.fiscal_year.refresh();
            report.page.fields_dict.period_start_date.refresh();
            report.page.fields_dict.period_end_date.refresh();
        };
        
        // Initialize visibility based on default selection
        let initial_filter_type = report.get_filter_value("date_filter_type") || "Fiscal Year";
        if (initial_filter_type === "Date Range") {
            report.page.fields_dict.fiscal_year.df.hidden = 1;
            report.page.fields_dict.period_start_date.df.hidden = 0;
            report.page.fields_dict.period_end_date.df.hidden = 0;
        } else {
            report.page.fields_dict.fiscal_year.df.hidden = 0;
            report.page.fields_dict.period_start_date.df.hidden = 1;
            report.page.fields_dict.period_end_date.df.hidden = 1;
        }
        
        // Refresh fields to apply initial visibility
        report.page.fields_dict.fiscal_year.refresh();
        report.page.fields_dict.period_start_date.refresh();
        report.page.fields_dict.period_end_date.refresh();
    }
};