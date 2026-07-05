"""Server-side enforcement of vehicle tagging on vehicle-expense accounts.

Journal Entry Account and Purchase Invoice Item carry a custom_subtype field
(label "Vehicle", Link -> Vehicle). Rows posted against a vehicle-expense
account must have it set, across all companies. Account matching uses the same
name patterns as the Avinas Vehicle Expense report.

The matching UI behaviour (red asterisk) comes from mandatory_depends_on
property setters created by patches.vehicle_mandatory_property_setters —
Frappe does not enforce mandatory_depends_on server-side, hence these hooks.
"""

import frappe
from frappe import _

VEHICLE_ACCOUNT_PATTERNS = ("Fuel Expenses", "R & M - Vehicles", "Other Vehicle Expenses")


def account_requires_vehicle(account):
    return bool(account) and any(pattern in account for pattern in VEHICLE_ACCOUNT_PATTERNS)


def validate_journal_entry(doc, method=None):
    _throw_if_vehicle_missing(doc.get("accounts") or [], account_field="account")


def validate_purchase_invoice(doc, method=None):
    _throw_if_vehicle_missing(doc.get("items") or [], account_field="expense_account")


def _throw_if_vehicle_missing(rows, account_field):
    missing = [
        row
        for row in rows
        if account_requires_vehicle(row.get(account_field)) and not row.get("custom_subtype")
    ]
    if not missing:
        return

    lines = [
        _("Row #{0}: Vehicle is mandatory for account {1}").format(
            row.idx, frappe.bold(row.get(account_field))
        )
        for row in missing
    ]

    accounts_without_options = sorted(
        {
            account
            for account in {row.get(account_field) for row in missing}
            if not _account_has_vehicle_options(account)
        }
    )
    if accounts_without_options:
        lines.append(
            _("No vehicles are configured for {0} — add the allowed vehicles in the Vehicle List table on the Account first.").format(
                ", ".join(frappe.bold(a) for a in accounts_without_options)
            )
        )

    frappe.throw("<br>".join(lines), title=_("Vehicle Required"))


def _account_has_vehicle_options(account):
    try:
        return bool(frappe.get_cached_doc("Account", account).get("custom_sub_type_list"))
    except Exception:
        return False
