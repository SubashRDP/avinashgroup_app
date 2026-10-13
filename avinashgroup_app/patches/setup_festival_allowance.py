"""Festival allowance rules on Salary Component; Dashain Allowance set up to use them.

payroll/festival_allowance.py reads every rule from the component, so HR can
change them in the desk without a developer. This patch:

  1. adds the Festival Allowance section to Salary Component (shown for a
     Yearly allowance): Festival Allowance tick, Pay Month (BS), Minimum
     Service Days, Prorate for Under a Year, Include Daily-Wage Staff,
     Include Staff Leaving Before the Cut-off;
  2. makes `Dashain Allowance` the festival allowance — Earning, taxable, not
     prorated by payment days, kind Yearly — with the defaults below, only
     when it is not ticked yet (HR's later choices survive a re-run);
  3. gives `Dashain Allowance` and `Leave Encashment` an Accounts row for every
     company where Basic has one, copied from Basic's (O/O, S/D, F/P), so the
     payroll journal can book them. A row already there is left alone.

The amount itself is not a setting: one month's basic × service factor, capped
at 100 % (user decision, 2026-10-13).
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

COMPONENT = "Dashain Allowance"
#: Defaults chosen 2026-10-13 where the policy minutes are silent — listed for
#: the client to confirm (docs/user-guide/08-raises-advances-bonuses-year-end.md 8.4).
DEFAULTS = {
	"custom_is_festival_allowance": 1,
	"custom_festival_pay_month": "06 - Ashwin",  # Dashain falls in Ashwin/Kartik; paid with Ashwin's salary
	"custom_festival_min_service_days": 0,  # anyone who joined before the cut-off
	"custom_festival_prorate": 1,  # user rule: under a year → service ÷ year
	"custom_festival_include_daily_wage": 0,  # daily wage is paid in cash, outside payroll (2026-10-08)
	"custom_festival_include_leavers": 0,  # someone leaving before the cut-off is not paid
}
SHOW = "eval:doc.custom_is_festival_allowance"


def bs_month_options() -> str:
	return frappe.get_meta("Payroll Entry").get_field("custom_bs_month").options if frappe.get_meta(
		"Payroll Entry"
	).get_field("custom_bs_month") else ""


def execute():
	create_custom_fields(
		{
			"Salary Component": [
				{
					"fieldname": "custom_festival_section",
					"fieldtype": "Section Break",
					"label": "Festival Allowance",
					"insert_after": "custom_allowance_kind",
					"depends_on": "eval:doc.custom_allowance_kind=='Yearly'",
					"collapsible": 0,
				},
				{
					"fieldname": "custom_is_festival_allowance",
					"fieldtype": "Check",
					"label": "Festival Allowance",
					"insert_after": "custom_festival_section",
					"description": "Paid by the Payroll Entry's Dashain Allowance button: one month's basic × service factor (full year = 100 %)",
				},
				{
					"fieldname": "custom_festival_pay_month",
					"fieldtype": "Select",
					"label": "Pay Month",
					"options": bs_month_options(),
					"insert_after": "custom_is_festival_allowance",
					"depends_on": SHOW,
					"description": "The BS month whose Payroll Entry pays it. Blank: any month",
				},
				{
					"fieldname": "custom_festival_min_service_days",
					"fieldtype": "Int",
					"label": "Minimum Service Days",
					"insert_after": "custom_festival_pay_month",
					"depends_on": SHOW,
					"description": "Days from joining to the cut-off below which nothing is paid. 0: none",
				},
				{
					"fieldname": "custom_festival_cb",
					"fieldtype": "Column Break",
					"insert_after": "custom_festival_min_service_days",
				},
				{
					"fieldname": "custom_festival_prorate",
					"fieldtype": "Check",
					"label": "Prorate for Under a Year",
					"insert_after": "custom_festival_cb",
					"depends_on": SHOW,
					"description": "On: under a year's service is paid service days ÷ days in the year. Off: any service pays one month",
				},
				{
					"fieldname": "custom_festival_include_daily_wage",
					"fieldtype": "Check",
					"label": "Include Daily-Wage Staff",
					"insert_after": "custom_festival_prorate",
					"depends_on": SHOW,
					"description": "A day's wage × the BS month's days counts as their month",
				},
				{
					"fieldname": "custom_festival_include_leavers",
					"fieldtype": "Check",
					"label": "Include Staff Leaving Before the Cut-off",
					"insert_after": "custom_festival_include_daily_wage",
					"depends_on": SHOW,
				},
			]
		},
		update=True,
	)

	if frappe.db.exists("Salary Component", COMPONENT):
		values = {
			"type": "Earning",
			"is_tax_applicable": 1,
			"depends_on_payment_days": 0,
			"custom_is_allowance": 1,
			"custom_allowance_kind": "Yearly",
		}
		if not frappe.db.get_value("Salary Component", COMPONENT, "custom_is_festival_allowance"):
			values.update(DEFAULTS)
		frappe.db.set_value("Salary Component", COMPONENT, values, update_modified=False)

	for component in (COMPONENT, "Leave Encashment"):
		copy_accounts_from_basic(component)


def copy_accounts_from_basic(component: str) -> int:
	"""Give the component Basic's account row for each company it lacks one for."""
	if not frappe.db.exists("Salary Component", component):
		return 0
	doc = frappe.get_doc("Salary Component", component)
	have = {row.company for row in doc.accounts}
	added = 0
	for row in frappe.get_all(
		"Salary Component Account",
		filters={"parent": "Basic", "parenttype": "Salary Component"},
		fields=["company", "account", "custom_account_marketing", "custom_account_plant"],
	):
		if row.company in have:
			continue
		doc.append("accounts", row)
		added += 1
	if added:
		doc.flags.ignore_permissions = True
		doc.save()
	return added
