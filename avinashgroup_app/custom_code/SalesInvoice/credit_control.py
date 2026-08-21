



import frappe
from frappe.utils import getdate, nowdate, flt, fmt_money



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
        cn_credit   unsettled credit notes — goods returned but not yet set
                    against a bill; real credit the customer holds
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

    # Credit notes the customer still holds. A return carries a NEGATIVE
    # outstanding_amount until it is set against a bill, so `< -0.01` picks up
    # exactly the unsettled ones — a fully applied credit note sits at 0 and is
    # ignored. These were previously invisible: the unpaid query filters
    # `is_return = 0`, so a customer who had returned goods was told they owed
    # more than they did. Verified against the Party Ledger for NGI-CUS-00739 —
    # advance pool + credit notes reproduces the closing balance to the paisa.
    cn_credit = flt(frappe.db.sql("""
        SELECT IFNULL(-SUM(outstanding_amount), 0)
        FROM `tabSales Invoice`
        WHERE customer = %s
          AND docstatus = 1
          AND is_return = 1
          AND is_internal_customer = 0
          AND outstanding_amount < -0.01
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
        "cn_credit": cn_credit,
        "je_net": je_net,
        "je_credit": je_credit,
        "je_debit": je_debit,
        # Credit notes join the pool rather than only offsetting the amount
        # check, so they retire bills FIFO like any other credit -- which means
        # they relieve the bill-count check too, not just the money.
        "advance": advance + cn_credit + je_credit,
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
        "cn_credit": 0.0,
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

    # DAYS CHECK PARKED 2026-08-20 — see the commented block further down.
    # days_limit is left out of this test on purpose: a customer carrying ONLY
    # a days limit must count as unrestricted while the check is off.
    # To restore: put `days_limit or` back here and uncomment the block below.
    if not (bill_limit or amount_limit):   # or days_limit
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
        "cn_credit": pool["cn_credit"],
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

    # ------------------------------------------------------------------
    # Evaluate all three limits INDEPENDENTLY. The server throws on only the
    # first one by precedence, but the banner has to be able to mark every
    # limit that is actually breached — returning early here left
    # days_exceeded at 0 for a customer who was 2,000 days overdue simply
    # because the bill count tripped first, so the banner drew the days
    # segment unmarked, as though it were fine.
    # ------------------------------------------------------------------
    # Count and days use `>=`: a limit of 5 blocks the 5th unpaid bill.
    count_exceeded = bool(bill_limit and unpaid["unpaid_count"] >= bill_limit)
    # PARKED — days check off. days_used and oldest_date are still computed
    # above and still returned, so the banner can show the age as information.
    # days_exceeded = bool(days_limit and days_used >= days_limit)
    days_exceeded = False
    # Amount uses `>`: landing exactly on the limit is allowed.
    final_exposure = exposure + new_amount
    amount_exceeded = bool(amount_limit and final_exposure > amount_limit)

    state["count_exceeded"] = int(count_exceeded)
    state["days_exceeded"] = int(days_exceeded)   # PARKED — always 0
    state["amount_exceeded"] = int(amount_exceeded)

    # Precedence — count, then days, then amount. This is the order
    # validate_sales_invoice throws in, so only the first is ever seen.
    if count_exceeded:
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
    # ---- PARKED 2026-08-20: days check -------------------------------------
    # Switched off at Sijan's request; kept verbatim so it can be brought back.
    # To restore: uncomment this branch, restore the days_exceeded assignment
    # above, and put `days_limit or` back in the "no limits configured" test.
    #
    # Known open question if it is revived: the clock runs on the oldest bill
    # the advance did NOT cover, so a customer holding a large advance that
    # falls a little short still ages. On ng-group, GEPL-CUS-00212 had
    # 2,024,831 of advance, was 9,079 short, and showed 142 days.
    #
    # elif days_exceeded:
    #     state["blocked_by"] = "days"
    #     state["title"] = "Credit Days Exceeded"
    #     state["message"] = (
    #         f"<b>Credit Limit: Days Exceeded</b><br><br>"
    #         f"Customer: <b>{customer}</b><br>"
    #         f"Oldest Unpaid Invoice: <b>{unpaid['oldest_invoice']}</b><br>"
    #         f"Date: <b>{unpaid['oldest_date']}</b> ({days_used} days ago)<br>"
    #         f"Maximum Days Allowed: <b>{int(days_limit)}</b><br><br>"
    #         f"<i>Payment is overdue. Please collect payment before new sales.</i>"
    #     )
    # ------------------------------------------------------------------------
    elif amount_exceeded:
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
