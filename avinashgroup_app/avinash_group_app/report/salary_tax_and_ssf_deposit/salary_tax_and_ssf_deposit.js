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
			default: salary_deposit_default_period().year,
			reqd: 1,
		},
		{
			fieldname: "bs_month",
			label: __("Salary Month"),
			fieldtype: "Select",
			options: BS_MONTHS.map((m, i) => `${String(i + 1).padStart(2, "0")} - ${m}`).join("\n"),
			default: salary_deposit_default_period().month,
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
};

// Approximate BS "last month" from today's AD date. BS months start around the
// 14th-17th of an AD month; the user can always change the filter.
function salary_deposit_default_period() {
	const today = new Date();
	const m = today.getMonth() + 1;
	const d = today.getDate();
	// AD month → BS month that begins in it (Baisakh starts mid-April).
	let bs = ((m + 8) % 12) + 1;
	if (d < 16) bs = bs === 1 ? 12 : bs - 1; // still in the previous BS month
	let year = today.getFullYear() + (m > 4 || (m === 4 && d >= 14) ? 57 : 56);
	// step back one month: the salary being deposited
	bs = bs === 1 ? 12 : bs - 1;
	if (bs === 12) year -= 1;
	return { year, month: `${String(bs).padStart(2, "0")} - ${BS_MONTHS[bs - 1]}` };
}
