// Salary Tax and SSF Deposit — the month's SSF, SST and remuneration tax to deposit.
// Defaults to LAST BS month: deposits are made in the month after the salary.

const BS_MONTHS = [
	"Baisakh", "Jestha", "Ashadh", "Shrawan", "Bhadra", "Ashwin",
	"Kartik", "Mangsir", "Poush", "Magh", "Falgun", "Chaitra",
];

frappe.query_reports["Salary Tax and SSF Deposit"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
			reqd: 1,
		},
		{
			fieldname: "bs_year",
			label: __("BS Year"),
			fieldtype: "Int",
			reqd: 1,
		},
		{
			fieldname: "bs_month",
			label: __("Salary Month"),
			fieldtype: "Select",
			options: BS_MONTHS.map((m, i) => `${String(i + 1).padStart(2, "0")} - ${m}`).join("\n"),
			reqd: 1,
		},
		{
			fieldname: "docstatus",
			label: __("Slips"),
			fieldtype: "Select",
			options: ["1 - Submitted", "0 - Draft"].join("\n"),
			default: "1 - Submitted",
			reqd: 1,
		},
	],
	onload: salary_deposit_set_default_period,
};

// Default to the last finished BS month, from the server's calendar
// (hr/bs_calendar.py) so it agrees with the payroll it reports on.
function salary_deposit_set_default_period(report) {
	frappe.call({
		method: "avinashgroup_app.hr.bs_calendar.get_default_month",
		args: { company: report.get_filter_value("company") },
		callback: (r) => {
			if (!r.message) return;
			report.set_filter_value({ bs_year: r.message.bs_year, bs_month: r.message.bs_month });
		},
	});
}
