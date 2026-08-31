# Credit control

What stops a sale to a customer who owes too much, for too long, or on too many
bills — and, just as importantly, what it deliberately does not stop.

- Enforcement: `avinashgroup_app/custom_code/SalesInvoice/credit_control.py`
- Banner: `avinashgroup_app/public/js/sales_invoice.js`
- Registered as the last handler in `sales_invoice_specific_events["validate"]`

Figures throughout are from the live site on **2026-08-31**.

---

## The three limits

All three live on **Customer**. A limit of 0 means "not set" and that check never runs.

| Field | Label | Fires when | Boundary |
|---|---|---|---|
| `custom_bill_count` | Bill Count | unpaid bills `>=` limit | a limit of 5 blocks the 5th |
| `custom_days_limit` | Days Limit | oldest uncovered bill `>=` limit days | a limit of 7 blocks on day 7 |
| `custom_amount_limit` | Amount Limit | exposure + this invoice `>` limit | landing exactly on the limit is allowed |

Count and days use `>=`; amount uses `>`. That asymmetry is deliberate — a customer
may spend up to their limit exactly, but the *n*th bill is the one too many.

**Precedence is count, then days, then amount.** The server throws on the first
breach only, so that is the only message the user ever sees. The banner marks
every breached limit, because a customer can be over two at once and showing the
days tile unmarked while it is 2,000 days overdue is how this was wrong before.

### What is actually configured

```
1998  amount only            337  count only
 921  count + amount         115  all three
 171  days + amount           17  count + days
                               2  days only
```

3,561 of 4,018 customers carry at least one limit. **282 (7.9%) are blocked right
now**: 184 on amount, 98 on days, **0 on count**.

Two things follow from that, and neither is a bug:

**The count check cannot currently fire.** 1,390 customers have one, set to 1000
(1,011 of them) or 100 (378). The largest real position is 90 unpaid bills. It is
dormant by configuration — either deliberately parked, or those were meant to be
meaningful numbers and never revisited.

**Amount blocking is mostly the advance-only policy.** 2,491 customers have
`custom_amount_limit = 1`, which means "may only buy against money already
deposited". 1,353 of them are currently in credit. `1` rather than `0` because 0
disables the check entirely and would let them bill anything. So "blocked on
amount" here usually reads *this customer must prepay*, not *this customer is
over their credit* — worth separating before handing the list to sales.

---

## What counts as the customer's money

`_advance_pool()` returns the components separately, because a banner showing
"advance 79,232,897" is unauditable unless it can say where that came from.

| Component | Source |
|---|---|
| `pe_advance` | unallocated Payment Entry receipts (`Receive` / `Internal Transfer`) |
| `cn_credit` | unsettled credit notes — returns carry a negative `outstanding_amount` until set against a bill |
| `je_credit` | journal net **credit** on the debtor/advance accounts, unlinked rows only |
| `je_debit` | journal net **debit** — extra debt with no invoice behind it |

```
advance = pe_advance + cn_credit + je_credit
```

`je_credit` and `je_debit` are mutually exclusive — a customer's journal rows net
one way or the other.

**`je_debit` is not in the advance pool and never ages.** It has no invoice, so it
cannot be an "oldest bill"; it only ever lands in the amount check. This is what
blocks NGI Counter Sales: a 1,346.83 debit from a 795-row opening-balance journal
posted the day after the account was squared.

Only **unlinked** journal rows count. A row referenced against an invoice has
already moved that invoice's `outstanding_amount`; counting it here would
double it.

Credit notes join the pool rather than merely offsetting the amount check, so
they retire bills FIFO like any other credit — which means they relieve the bill
*count* too, not just the money.

---

## How the position is computed

`_unpaid_after_advance()` applies the advance to unpaid bills oldest-first, in
SQL. A running total is the FIFO cursor:

```
bills ordered by (posting_date, name), cum = running sum of outstanding

  cum <= advance                    bill fully covered      -> drops out
  cum > advance, cum - amt < advance bill part-paid          -> contributes cum - advance
  cum - amt >= advance              advance never reached it -> contributes in full
```

Done as one window function so no invoice rows cross the wire: a customer with
three open bills costs the same as one with three thousand.

### The amount check

```
leftover_advance = max(0, advance - gross_outstanding)
exposure         = total_unpaid + je_debit - leftover_advance
available_credit = amount_limit - exposure
blocked when       exposure + new_invoice > amount_limit
```

`leftover_advance` and `total_unpaid` are never both non-zero — if any bill is
uncovered then FIFO consumed the whole advance. So this collapses to plain
"outstanding + this invoice" whenever the customer actually owes money, and only
changes the prepaid case.

The limit is **headroom on top of leftover advance**, which is why available
credit can exceed the limit itself. A customer with `amount_limit = 1` holding
36,576.31 unused shows "can still bill 36,577.31". That is correct, and it is
what the counter sees.

### The days clock

The clock starts at **the oldest bill the advance did not reach at all** — not
the oldest bill it could not *fully* cover.

Those differ on exactly one bill: the one the FIFO cursor lands inside. That bill
is part-paid, and a bill the customer's money is actively paying must not age.
Getting this wrong produced, on GEPL-CUS-00339:

```
51 unpaid bills, gross   2,495,190
advance pool             2,493,150
                         ─────────
residual                     2,040   -> lands on the 51st bill, dated 2026-04-01
```

2026-04-01 was that customer's **newest** invoice. The clock read 152 days and
refused every sale to a customer holding 2.49m in advance who had simply not
bought since April — and it was self-sustaining, because being blocked meant no
newer bill ever arrived to move the clock. Correcting the rule released 27
customers and held the 103 who genuinely owe.

`DAYS_MATERIALITY_FLOOR = 100.0` is a second, separate guard: an uncovered
balance below it reads as 0 days. It exists for GEPL-CUS-00713, where an
unallocated journal credit of 34,174.93 against bills of 34,175.00 left **seven
paisa** uncovered and refused that customer for 124 days. It is a fairness dial,
not a volume dial — the group-wide block count barely moves across floors of
1 / 100 / 1,000 / 5,000.

The two guards catch different things. The floor catches *small absolutely*; the
clock rule catches *small relative to the advance*. 2,040 is material on its own
and trivial against 2.49m, which is why the floor could never have caught it.

**The invoice named in the days message is the oldest bill the customer's credits
could not pay**, which for anyone holding an advance is newer than their oldest
bill. The message says so outright, because an operator checking the ledger will
see older bills than the one quoted and otherwise has no way to know that is
correct.

---

## When it does not run

`validate_sales_invoice()` returns early for:

- **cancelled documents** — enforce nothing
- **returns / credit notes** — they reduce exposure rather than consume it
- **zero-value invoices** — consume no credit

Everything else is checked on every save and every submit.

**There is no override.** Not a role, not a checkbox, not a permission. If a
customer is blocked, the way through is to collect payment, allocate an existing
credit, or change their limit. That is deliberate: the check exists because the
failure is invisible, and an override would make it invisible again.

### Why it runs last

The amount check reads `doc.grand_total`, which is only final once the tax
pipeline ahead of it has built the taxes table. Moving this earlier would test a
pre-VAT figure and let invoices through that should not be.

---

## The banner

`get_credit_position()` is a read-only whitelisted call returning the same state
the validator computes, so the strip and the save always agree.

The five tiles are the labels of the system this one replaced, kept verbatim —
the staff reading them have decades on those words:

```
Delivery Order + Outstanding = Total,   blocked when Total > Credit Limit
```

- **Delivery Order** — this invoice, the sale being rung up now
- **Outstanding** — `exposure`, shown signed; negative for a customer in credit
- **Total** — the two added, what the limit is tested against
- **Credit Limit** — the limit, with remaining headroom underneath
- **Days Limit** — the limit, with the clock underneath

`new_amount` is 0 in the server payload on purpose: the client recomputes the
amount verdict as the operator types, so keystrokes do not each cost a round
trip. Count and days are decided server-side.

The invoice amount comes from `custom_expected_grand_total`, **not**
`grand_total`. Before save, the VAT and excise rows exist only after the server
builds them, so `grand_total` is 0 — reading it priced the sale at zero and made
the strip print "Credit OK" for an invoice the save then refused.

The strip is decoration; the form is not. `render_credit_banner` catches its own
exceptions, because on the `grand_total` trigger it is the only statement — an
exception escaping would interrupt the trigger and take ERPNext's own handlers
down with it while a clerk is mid-invoice. A failure degrades to a placeholder
row that says in words the figures are missing, which is safer than a strip of
stale numbers.

---

## Gotchas found the hard way

**A ledger check will not reproduce the days figure.** The clock runs from the
oldest bill the *credits could not reach*, not the customer's oldest bill.

**`gross_outstanding` excludes credit notes** (`is_return = 0`), so it must never
be shown as what a customer owes — it would overstate anyone who returned goods.
The banner shows `exposure`.

**The days limit is effectively GEPL-only.** 300 of the 305 customers carrying one
are Grishma; NGI and NGK have none, so no NGI or NGK customer can ever be blocked
on age however old the debt gets. 297 of the 305 are on **7 days**, which is what
produces almost the entire block list — and hospitality does not pay in 7 days.
Whether 7 is right is a business decision nobody has made.

**Blocked-on-amount is not one thing.** 184 blocked on amount, but the large
majority are the `limit = 1` prepay policy rather than customers over a real
credit line.
