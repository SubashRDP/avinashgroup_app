// Accounts table: every account column (O/O `account`, S/D
// `custom_account_marketing`, F/P `custom_account_plant`) lists only ledger
// accounts of that row's company. HRMS filters the stock `account` only; our
// two section columns had no filter and listed all seven companies' accounts.
// Earnings also narrow to Expense accounts; deductions stay open (they post to
// liabilities, staff advances or back to the expense). The server checks the
// company again (payroll/allowance.py validate_salary_component).
const SALARY_COMPONENT_ACCOUNT_FIELDS = ["account", "custom_account_marketing", "custom_account_plant"];

frappe.ui.form.on("Salary Component", {
	setup(frm) {
		for (const fieldname of SALARY_COMPONENT_ACCOUNT_FIELDS) {
			frm.set_query(fieldname, "accounts", (doc, cdt, cdn) => {
				const row = locals[cdt][cdn];
				if (!row.company) {
					frappe.throw(__("Select the Company on row {0} first", [row.idx]));
				}
				const filters = { company: row.company, is_group: 0 };
				if (doc.type === "Earning") filters.root_type = "Expense";
				return { filters };
			});
		}
	},
});
