# import frappe
# from frappe.utils import getdate, nowdate

# def validate_sales_invoice(doc, method):
#     """
#     Validates a Sales Invoice against customer-specific limits:
#     1. Maximum unpaid invoice count
#     2. Maximum days allowed for unpaid invoices
#     3. Maximum cumulative amount allowed

#     """

#     today = getdate(doc.posting_date or nowdate())
#     customer = doc.customer

#     # 1. Fetch customer-specific limits
#     custom_bill_count = frappe.db.get_value("Customer", customer, "custom_bill_count") or 0
#     custom_days_limit = frappe.db.get_value("Customer", customer, "custom_days_limit") or 0
#     custom_amount_limit = frappe.db.get_value("Customer", customer, "custom_amount_limit") or 0

#     # 2. BILL COUNT CHECK
#     unpaid_count = frappe.db.count(
#         "Sales Invoice",
#         filters={
#             "customer": customer,
#             "docstatus": 1,
#             "outstanding_amount": [">", 0],
#             "is_return": 0,
#             "is_internal_customer": 0
#         }
#     )

#     if custom_bill_count and unpaid_count >= custom_bill_count:
#         frappe.throw(
#             f"Cannot create Sales Invoice.<br>"
#             f"Customer <b>{customer}</b> has <b>{unpaid_count}</b> unpaid invoices, "
#             f"which exceeds the allowed bill count limit of <b>{custom_bill_count}</b>."
#         )

#     # 3. DAYS LIMIT CHECK
#     if custom_days_limit:
#         oldest_posting_date = frappe.db.get_value(
#             "Sales Invoice",
#             filters={
#                 "customer": customer,
#                 "docstatus": 1,
#                 "outstanding_amount": [">", 0],
#                 "is_return": 0,
#                 "is_internal_customer": 0
#             },
#             fieldname="posting_date",
#             order_by="posting_date asc"
#         )

#         if oldest_posting_date:
#             days_passed = (today - getdate(oldest_posting_date)).days
#             if days_passed >= custom_days_limit:
#                 frappe.throw(
#                     f"Cannot create Sales Invoice.<br>"
#                     f"Customer has unpaid invoices since <b>{oldest_posting_date}</b> "
#                     f"(<b>{days_passed}</b> days), exceeding the allowed limit of "
#                     f"<b>{custom_days_limit}</b> days."
#                 )

#     # 4. AMOUNT LIMIT CHECK - ONLY OUTSTANDING FROM UNPAID INVOICES
#     if custom_amount_limit:
#         total_outstanding = frappe.db.sql("""
#             SELECT SUM(outstanding_amount)
#             FROM `tabSales Invoice`
#             WHERE customer = %s
#             AND docstatus = 1
#             AND outstanding_amount > 0
#             AND is_return = 0
#             AND is_internal_customer = 0
#             AND posting_date <= %s
#             AND name != %s
#         """, (customer, today, doc.name or ""))[0][0] or 0

#         new_invoice_amount = doc.grand_total or 0
#         final_exposure = total_outstanding + new_invoice_amount

        
#         if final_exposure > custom_amount_limit:
#             frappe.throw(
#                 f"Cannot create Sales Invoice.<br>"
#                 f"Customer balance after this invoice will be <b>{final_exposure}</b>, "
#                 f"which exceeds the allowed amount limit of <b>{custom_amount_limit}</b>."
#             )


# import frappe
# from frappe.utils import getdate, nowdate

# def validate_sales_invoice(doc, method):
#     today = getdate(doc.posting_date or nowdate())
#     customer = doc.customer

#     # 1. Customer limits
#     custom_bill_count = frappe.db.get_value("Customer", customer, "custom_bill_count") or 0
#     custom_days_limit = frappe.db.get_value("Customer", customer, "custom_days_limit") or 0
#     custom_amount_limit = frappe.db.get_value("Customer", customer, "custom_amount_limit") or 0

#     # 2. Total unallocated advance
#     total_advance = frappe.db.sql("""
#         SELECT IFNULL(SUM(unallocated_amount), 0)
#         FROM `tabPayment Entry`
#         WHERE party_type = 'Customer'
#         AND party = %s
#         AND docstatus = 1
#         AND unallocated_amount > 0
#         AND payment_type IN ('Receive', 'Internal Transfer')
#     """, (customer,))[0][0] or 0

#     # 3. Outstanding invoices after advance
#     result = frappe.db.sql("""
#         SELECT 
#             name,
#             posting_date,
#             outstanding_amount,
#             cumulative_outstanding,
#             previous_cumulative,
#             CASE 
#                 WHEN previous_cumulative >= %(advance)s THEN outstanding_amount
#                 WHEN cumulative_outstanding > %(advance)s THEN cumulative_outstanding - %(advance)s
#                 ELSE 0
#             END AS remaining_outstanding_for_this_invoice
#         FROM (
#             SELECT 
#                 name,
#                 posting_date,
#                 outstanding_amount,
#                 SUM(outstanding_amount) OVER (
#                     ORDER BY posting_date ASC, name ASC
#                     ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
#                 ) AS cumulative_outstanding,
#                 COALESCE(
#                     SUM(outstanding_amount) OVER (
#                         ORDER BY posting_date ASC, name ASC
#                         ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
#                     ), 0
#                 ) AS previous_cumulative
#             FROM `tabSales Invoice`
#             WHERE customer = %(customer)s
#             AND docstatus = 1
#             AND outstanding_amount > 0
#             AND is_return = 0
#             AND is_internal_customer = 0
#             AND name != %(current_doc)s
#         ) inv
#         WHERE cumulative_outstanding > %(advance)s
#         ORDER BY posting_date ASC, name ASC
#     """, {
#         "customer": customer,
#         "current_doc": doc.name or "",
#         "advance": total_advance
#     }, as_dict=1)

#     if not result:
#         return

#     # 4. Metrics
#     first_unpaid = result[0]
#     unpaid_count = len(result)
#     total_outstanding = sum(
#         r.remaining_outstanding_for_this_invoice for r in result
#     )

#     # 5. Bill count check
#     if custom_bill_count and unpaid_count >= custom_bill_count:
#         frappe.throw(
#             f"Cannot create Sales Invoice.<br>"
#             f"Customer <b>{customer}</b> has <b>{unpaid_count}</b> unpaid invoices "
#             f"(after applying advance of <b>{total_advance:,.2f}</b>), "
#             f"exceeding allowed limit of <b>{custom_bill_count}</b>."
#         )

#     # 6. Days limit check
#     if custom_days_limit:
#         days_passed = (today - getdate(first_unpaid.posting_date)).days
#         if days_passed >= custom_days_limit:
#             frappe.throw(
#                 f"Cannot create Sales Invoice.<br>"
#                 f"Oldest unpaid invoice <b>{first_unpaid.name}</b> dated "
#                 f"<b>{first_unpaid.posting_date}</b> "
#                 f"({days_passed} days old) exceeds allowed limit of "
#                 f"<b>{custom_days_limit}</b> days."
#             )

#     # 7. Amount limit check
#     if custom_amount_limit:
#         new_amount = doc.grand_total or 0
#         final_exposure = total_outstanding + new_amount
#         if final_exposure > custom_amount_limit:
#             frappe.throw(
#                 f"Cannot create Sales Invoice.<br>"
#                 f"Customer exposure will be <b>{final_exposure:,.2f}</b> "
#                 f"(limit: <b>{custom_amount_limit:,.2f}</b>).<br>"
#                 f"Outstanding: <b>{total_outstanding:,.2f}</b><br>"
#                 f"New invoice: <b>{new_amount:,.2f}</b>"
#             )




import frappe
from frappe.utils import getdate, nowdate, flt, fmt_money


# ══════════════════════════════════════════════════════════════════════════════
# SHARED CORE
# ══════════════════════════════════════════════════════════════════════════════
# validate_sales_invoice (enforcement) and get_credit_position (the form banner)
# must agree exactly — a banner reading "within limit" on an invoice the save
# then rejects is worse than no banner at all. Both therefore take their numbers
# AND their verdict from _credit_state() below, and neither computes anything of
# its own. Anything that changes about credit rules changes there, once.

# Debtor and customer-advance accounts, matched by account_name so that a single
# list covers every company. Verified against avinas1 on 2026-08-20: all seven
# companies carry "Debtors A/c - Domestic" (143101); GEPL, GLMI and SGU use
# "Advance Received" (347959), while NGI, NGG, NGN and NGK use "Advance From
# Customer" (347959). NGK spells its account "Advance from Customer" — that
# still matches, because account_name collates utf8mb4_unicode_ci.
CREDIT_ACCOUNT_NAMES = (
    "Debtors A/c - Domestic",
    "Advance Received",
    "Advance From Customer",
)


def _money(value, currency=None):
    """Format for display. The books are NPR — never hardcode a symbol here."""
    return fmt_money(
        flt(value),
        currency=currency or frappe.db.get_default("currency") or "NPR",
    )


def _advance_pool(customer):
    """The customer's deposited-but-unapplied money, broken down by source.

    Returns a dict, not a single figure, because the banner has to SHOW where
    the money came from: a customer looking at "advance 79,232,897" needs to
    see which part is Payment Entries and which part is journal vouchers, or
    the number is unauditable from the form.

        pe_advance  unallocated Payment Entry receipts
        je_credit   journal net credit — deposits posted by voucher, folded
                    into the pool and retiring bills FIFO exactly like a PE
        je_debit    journal net debit — extra debt with no invoice behind it,
                    so it cannot age and cannot be counted as a bill; it only
                    ever lands in the amount check
        advance     pe_advance + je_credit, the figure the FIFO walk consumes

    je_credit and je_debit are mutually exclusive: a customer's journal rows
    net to one direction or the other, never both.
    """
    advance = flt(frappe.db.sql("""
        SELECT IFNULL(SUM(unallocated_amount), 0)
        FROM `tabPayment Entry`
        WHERE party_type = 'Customer'
          AND party = %s
          AND docstatus = 1
          AND unallocated_amount > 0.01
          AND payment_type IN ('Receive', 'Internal Transfer')
    """, customer)[0][0])

    # Unlinked Journal Entry rows only. A row referenced against an invoice has
    # already moved that invoice's outstanding_amount, so counting it again here
    # would double it.
    je_net = flt(frappe.db.sql("""
        SELECT IFNULL(SUM(jea.debit - jea.credit), 0)
        FROM `tabJournal Entry Account` jea
        INNER JOIN `tabJournal Entry` je ON je.name = jea.parent
        WHERE je.docstatus = 1
          AND jea.party_type = 'Customer'
          AND jea.party = %s
          AND IFNULL(jea.reference_name, '') = ''
          AND jea.account IN (
              SELECT name FROM `tabAccount` WHERE account_name IN %s
          )
    """, (customer, CREDIT_ACCOUNT_NAMES))[0][0])

    je_credit = -je_net if je_net < 0 else 0.0
    je_debit = je_net if je_net > 0 else 0.0

    return {
        "pe_advance": advance,
        "je_net": je_net,
        "je_credit": je_credit,
        "je_debit": je_debit,
        "advance": advance + je_credit,
    }


def _unpaid_after_advance(customer, advance, exclude_invoice=None):
    """Apply `advance` to the customer's unpaid bills oldest-first, in SQL.

    The running total `cum` is the FIFO cursor: a bill whose cumulative total
    stays within the advance is fully covered and drops out via `cum > advance`;
    the first bill past the advance is partially covered and contributes
    `cum - advance`; every bill after it contributes in full.

    This is the same walk validate_sales_invoice used to do in Python, moved
    into SQL so no invoice rows cross the wire — a customer with thousands of
    open bills costs the same as one with three.

    `gross_outstanding` is the pre-advance total over every unpaid bill. It is
    what lets the caller work out how much advance is LEFT once the bills are
    covered — the headroom a prepaid customer can still bill against.
    """
    row = frappe.db.sql("""
        SELECT
            -- `cum > advance` is applied per-aggregate rather than as an outer
            -- WHERE, so the same pass also yields gross_outstanding over ALL
            -- unpaid rows. That gross figure is what tells us how much advance
            -- is left over once the bills are covered.
            IFNULL(SUM(CASE WHEN cum > %(advance)s THEN 1 ELSE 0 END), 0)
                AS unpaid_count,
            IFNULL(SUM(CASE WHEN cum > %(advance)s
                            THEN CASE WHEN cum - outstanding_amount >= %(advance)s
                                      THEN outstanding_amount
                                      ELSE cum - %(advance)s END
                            ELSE 0 END), 0) AS total_unpaid,
            MIN(CASE WHEN cum > %(advance)s THEN posting_date END) AS oldest_date,
            -- Cheapest way to carry the oldest row's NAME out of an aggregate:
            -- posting_date renders fixed-width YYYY-MM-DD, so MIN over the
            -- concatenation orders by date then name, exactly like the window's
            -- ORDER BY. Constant memory, no second round trip.
            MIN(CASE WHEN cum > %(advance)s
                     THEN CONCAT(posting_date, '|', name) END) AS oldest_key,
            IFNULL(SUM(outstanding_amount), 0) AS gross_outstanding
        FROM (
            SELECT name, posting_date, outstanding_amount,
                   SUM(outstanding_amount) OVER (ORDER BY posting_date, name) AS cum
            FROM `tabSales Invoice`
            WHERE customer = %(customer)s
              AND docstatus = 1
              AND outstanding_amount > 0.01
              AND is_return = 0
              AND is_internal_customer = 0
              AND name != %(exclude)s
        ) unpaid
    """, {
        "customer": customer,
        "advance": advance,
        "exclude": exclude_invoice or "",
    }, as_dict=True)[0]

    oldest_invoice = None
    if row.oldest_key:
        oldest_invoice = row.oldest_key.split("|", 1)[1]

    return {
        "unpaid_count": int(row.unpaid_count or 0),
        "total_unpaid": flt(row.total_unpaid),
        "gross_outstanding": flt(row.gross_outstanding),
        "oldest_date": row.oldest_date,
        "oldest_invoice": oldest_invoice,
    }


def _credit_state(customer, as_of=None, new_amount=0, exclude_invoice=None, currency=None):
    """Full credit position of `customer`, plus the verdict on an invoice of
    `new_amount` dated `as_of`.

    `blocked_by` is None, "count", "days" or "amount" — evaluated in that order,
    because that is the order validate_sales_invoice throws in and only the
    first one to trip is ever seen by the user.

    The amount limit is headroom ON TOP of whatever advance the customer has
    left after their bills are covered:

        leftover_advance = max(0, advance - gross_outstanding)
        exposure         = total_unpaid + je_debit - leftover_advance
        available_credit = amount_limit - exposure
        blocked when       exposure + new_amount > amount_limit

    leftover_advance and total_unpaid are never both non-zero — if any bill is
    uncovered then FIFO consumed the whole advance — so this collapses to plain
    "outstanding + new invoice" whenever the customer actually owes money, and
    only changes the prepaid case.
    """
    state = {
        "has_limits": 0,
        "checks_active": 0,
        "blocked_by": None,
        "message": None,
        "title": None,
        "advance": 0.0,
        "pe_advance": 0.0,
        "je_credit": 0.0,
        "je_net": 0.0,
        "je_debit": 0.0,
        "unpaid_count": 0,
        "total_unpaid": 0.0,
        "gross_outstanding": 0.0,
        "leftover_advance": 0.0,
        "outstanding": 0.0,
        "exposure": 0.0,
        "available_credit": 0.0,
        "oldest_date": None,
        "oldest_invoice": None,
        "days_used": 0,
        "count_exceeded": 0,
        "days_exceeded": 0,
        "amount_exceeded": 0,
    }

    if not customer:
        return state

    limits = frappe.db.get_value(
        "Customer",
        customer,
        ["custom_bill_count", "custom_days_limit", "custom_amount_limit"],
        as_dict=True,
    )
    if not limits:
        return state

    bill_limit = flt(limits.get("custom_bill_count"))
    days_limit = flt(limits.get("custom_days_limit"))
    amount_limit = flt(limits.get("custom_amount_limit"))

    state.update({
        "bill_limit": int(bill_limit),
        "days_limit": int(days_limit),
        "amount_limit": amount_limit,
    })

    if not (bill_limit or days_limit or amount_limit):
        return state
    state["has_limits"] = 1

    today = getdate(as_of or nowdate())
    new_amount = flt(new_amount)

    pool = _advance_pool(customer)
    advance = pool["advance"]
    je_debit = pool["je_debit"]
    unpaid = _unpaid_after_advance(customer, advance, exclude_invoice)

    days_used = 0
    if unpaid["oldest_date"]:
        days_used = (today - getdate(unpaid["oldest_date"])).days

    # Advance the bills did not consume. FIFO leaves this at 0 whenever any
    # bill is still uncovered, so it is only ever positive for a prepaid
    # customer -- which is exactly the case the old early exit skipped.
    leftover_advance = max(0.0, advance - unpaid["gross_outstanding"])

    outstanding = unpaid["total_unpaid"] + je_debit
    exposure = outstanding - leftover_advance
    available_credit = (amount_limit - exposure) if amount_limit else 0

    state.update({
        "advance": advance,
        "pe_advance": pool["pe_advance"],
        "je_credit": pool["je_credit"],
        "je_net": pool["je_net"],
        "je_debit": je_debit,
        "unpaid_count": unpaid["unpaid_count"],
        "total_unpaid": unpaid["total_unpaid"],
        "gross_outstanding": unpaid["gross_outstanding"],
        "leftover_advance": leftover_advance,
        "outstanding": outstanding,
        "exposure": exposure,
        "available_credit": available_credit,
        "oldest_date": str(unpaid["oldest_date"]) if unpaid["oldest_date"] else None,
        "oldest_invoice": unpaid["oldest_invoice"],
        "days_used": days_used,
        "remaining_amount": available_credit,
    })

    # The amount check now runs even with nothing uncovered -- a prepaid
    # customer has finite headroom (their leftover advance plus the limit) and
    # used to be able to bill any figure at all. The count and days checks stay
    # quiet on their own at zero unpaid: 0 >= bill_limit is false, and
    # days_used is 0 with no oldest bill.
    state["checks_active"] = 1

    # CHECK 1 — bill count. Note `>=`: a limit of 5 blocks the 5th unpaid bill.
    if bill_limit and unpaid["unpaid_count"] >= bill_limit:
        state["count_exceeded"] = 1
        state["blocked_by"] = "count"
        state["title"] = "Credit Limit Exceeded"
        state["message"] = (
            f"<b>Credit Limit: Bill Count Exceeded</b><br><br>"
            f"Customer: <b>{customer}</b><br>"
            f"Unpaid Bills: <b>{unpaid['unpaid_count']}</b> "
            f"(after applying {_money(advance, currency)} advance)<br>"
            f"Maximum Allowed: <b>{int(bill_limit)}</b><br><br>"
            f"<i>Please clear existing invoices before creating new ones.</i>"
        )
        return state

    # CHECK 2 — age of the oldest bill advances did not cover. Also `>=`.
    if days_limit and days_used >= days_limit:
        state["days_exceeded"] = 1
        state["blocked_by"] = "days"
        state["title"] = "Credit Days Exceeded"
        state["message"] = (
            f"<b>Credit Limit: Days Exceeded</b><br><br>"
            f"Customer: <b>{customer}</b><br>"
            f"Oldest Unpaid Invoice: <b>{unpaid['oldest_invoice']}</b><br>"
            f"Date: <b>{unpaid['oldest_date']}</b> ({days_used} days ago)<br>"
            f"Maximum Days Allowed: <b>{int(days_limit)}</b><br><br>"
            f"<i>Payment is overdue. Please collect payment before new sales.</i>"
        )
        return state

    # CHECK 3 — total exposure, the only check that includes the new invoice.
    # Note `>`: landing exactly on the limit is allowed.
    if amount_limit:
        final_exposure = exposure + new_amount
        if final_exposure > amount_limit:
            state["amount_exceeded"] = 1
            state["blocked_by"] = "amount"
            state["title"] = "Credit Amount Exceeded"
            state["message"] = (
                f"<b>Credit Limit: Amount Exceeded</b><br><br>"
                f"Customer: <b>{customer}</b><br>"
                f"Current Outstanding: <b>{_money(unpaid['total_unpaid'], currency)}</b><br>"
                f"Journal Debit Adjustment: <b>{_money(je_debit, currency)}</b><br>"
                f"Advance Left Over: <b>{_money(leftover_advance, currency)}</b><br>"
                f"Amount Limit: <b>{_money(amount_limit, currency)}</b><br>"
                f"Available Credit: <b>{_money(available_credit, currency)}</b><br>"
                f"New Invoice Amount: <b>{_money(new_amount, currency)}</b><br><br>"
                f"<i>This invoice needs {_money(new_amount - available_credit, currency)} "
                f"more credit than the customer has. Advance applied: "
                f"{_money(advance, currency)}.</i>"
            )

    return state


# ══════════════════════════════════════════════════════════════════════════════
# ENFORCEMENT — hooks.py doc_events["Sales Invoice"]["validate"]
# ══════════════════════════════════════════════════════════════════════════════

def validate_sales_invoice(doc, method):
    """Block the invoice if the customer has breached a credit limit.

    Runs last on the `validate` chain: the amount check reads doc.grand_total,
    which is only final once the tax pipeline ahead of it has built the taxes
    table. Moving this earlier would test a pre-VAT figure.
    """
    # Cancelled documents enforce nothing, and a credit note reduces exposure
    # rather than consuming it.
    if doc.docstatus == 2 or doc.is_return:
        return

    # A zero-value invoice consumes no credit.
    new_invoice_amount = flt(doc.grand_total)
    if new_invoice_amount <= 0:
        return

    state = _credit_state(
        doc.customer,
        as_of=doc.posting_date,
        new_amount=new_invoice_amount,
        exclude_invoice=doc.name,
        currency=doc.currency,
    )

    if state["blocked_by"]:
        frappe.throw(state["message"], title=state["title"])


# ══════════════════════════════════════════════════════════════════════════════
# BANNER FEED — public/js/sales_invoice.js
# ══════════════════════════════════════════════════════════════════════════════

@frappe.whitelist()
def get_credit_position(customer, posting_date=None, invoice=None):
    """Read-only credit position for the Sales Invoice form banner.

    Same core, same rules, same verdict as validate_sales_invoice — call it with
    the form's posting_date so the days check is measured from the same day the
    save will measure it from.

    `new_amount` is deliberately 0 here: the banner recomputes the amount verdict
    client-side as the user types, so the grand_total keystrokes do not each cost
    a server round trip. Everything the client needs for that is in the payload —
    `checks_active` gates it, exactly as it gates the server's own amount check.
    """
    if not customer:
        return {}

    state = _credit_state(
        customer,
        as_of=posting_date,
        new_amount=0,
        exclude_invoice=invoice,
    )

    if not state["has_limits"]:
        return {"has_limits": 0}

    return state
