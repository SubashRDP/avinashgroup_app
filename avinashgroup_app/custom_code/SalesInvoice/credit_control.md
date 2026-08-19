# Sales Invoice Credit Control

## Purpose

Blocks a Sales Invoice at save/submit time when the customer has drifted past one of
three credit limits: **too many unpaid bills**, **an unpaid bill that is too old**, or
**too much money outstanding**. Advances the customer has already deposited are netted
off first, so a customer who has paid ahead is not blocked by bills that money already
covers.

- **Module:** `avinashgroup_app/custom_code/SalesInvoice/credit_control.py`
- **Wired in:** `avinashgroup_app/hooks.py` — `doc_events["Sales Invoice"]["validate"]`
- **Read-only twin:** `get_credit_position()` in the same file, consumed by the form
  banner in `avinashgroup_app/public/js/sales_invoice.js`

---

## 1. Where the limits come from

Three custom fields on **Customer**. All three are optional; a blank or zero field
means that check is switched off for that customer.

| Field | Type | Meaning |
| --- | --- | --- |
| `custom_bill_count` | Int | Maximum number of unpaid bills the customer may carry |
| `custom_days_limit` | Int | Maximum age, in days, of the oldest unpaid bill |
| `custom_amount_limit` | Currency | Maximum total exposure, including the invoice being saved |

A customer with none of the three set is never blocked — the function exits at the
`if not (bill_limit or days_limit or amount_limit)` guard before touching the database
again.

> The fields are flat on Customer, **not** ERPNext's per-company `credit_limits` child
> table. See §7 — the limits are group-wide, not per company.

---

## 2. Hook position, and why it is last

```python
# hooks.py
"validate": [
    "...salesinvoice_taxes.before_save_salesinvoice",
    "...salesinvoice_taxes.validate_salesinvoice",
    "...credit_control.validate_sales_invoice",     # <-- last
],
```

The amount check reads `doc.grand_total`. That value is only final after the tax
pipeline ahead of it has built the taxes table and rolled up the totals, so credit
control must run **after** both tax hooks. Moving it earlier makes the amount check
test a pre-VAT figure, which under-reports exposure by the VAT amount on every invoice.

`validate` (not `before_save`) is deliberate and matches the rest of this app: desk
Save on a draft is escalated to Submit, and Frappe runs `before_submit` rather than
`before_save` on that path. A `before_save` hook here would silently never fire for
desk-created invoices.

---

## 3. Early exits

The function bails out, in this order, before doing any real work:

| Condition | Why |
| --- | --- |
| `doc.docstatus == 2` | Cancelled — nothing to enforce |
| `doc.is_return` | Credit notes reduce exposure; they are never blocked |
| `grand_total <= 0` | A zero-value invoice consumes no credit |
| Customer row missing | Nothing to read limits from |
| No limits configured | Customer is unrestricted |
| No unpaid invoices | Nothing outstanding to measure against |
| Advances cover every bill | `unpaid_list` empty — customer is square |

The last one is worth noting: if the advance pool covers **all** outstanding bills, the
function returns before *any* of the three checks run. A customer sitting on a large
advance cannot be blocked by the days check either, even if an old bill is technically
still open.

---

## 4. The advance pool

Two sources feed one pool.

### 4a. Payment Entry advances

```sql
SELECT IFNULL(SUM(unallocated_amount), 0)
FROM `tabPayment Entry`
WHERE party_type = 'Customer' AND party = %s AND docstatus = 1
  AND unallocated_amount > 0.01
  AND payment_type IN ('Receive', 'Internal Transfer')
```

Only the **unallocated** portion counts. Money already applied to an invoice is
reflected in that invoice's `outstanding_amount`, so counting it here would credit it
twice.

### 4b. Unlinked Journal Entry rows

```sql
SELECT IFNULL(SUM(jea.debit - jea.credit), 0)
FROM `tabJournal Entry Account` jea
INNER JOIN `tabJournal Entry` je ON je.name = jea.parent
WHERE je.docstatus = 1
  AND jea.party_type = 'Customer' AND jea.party = %s
  AND IFNULL(jea.reference_name, '') = ''
  AND jea.account IN (SELECT name FROM `tabAccount` WHERE account_name IN (
      'Debtors A/c - Domestic', 'Advance Received', 'Advance From Customer'))
```

`reference_name = ''` restricts this to rows **not** pointed at a specific invoice —
again, a referenced row's effect is already inside that invoice's outstanding amount.

`_advance_pool()` returns the breakdown, not a single figure, because the banner
has to show where the money came from — an "advance 79,232,897" with no
provenance is unauditable from the form:

| Key | Meaning |
| --- | --- |
| `pe_advance` | Unallocated Payment Entry receipts |
| `je_credit` | Journal net credit — folded into the pool, retires bills FIFO |
| `je_debit` | Journal net debit — added to exposure only |
| `advance` | `pe_advance + je_credit`, the figure the FIFO walk consumes |

`je_credit` and `je_debit` are mutually exclusive. The signed net splits two ways:

```python
je_debit = 0.0
if je_net < 0:          # net CREDIT — customer deposited money
    advance += -je_net  #   joins the advance pool, nets against oldest bills
else:                   # net DEBIT — extra debt with no bill behind it
    je_debit = je_net   #   cannot net anything; only lands in the amount check
```

This asymmetry is intentional. A net credit behaves exactly like a Payment Entry
advance and can retire old bills, which affects the count and days checks. A net debit
is a bare receivable with no invoice attached — there is no bill for it to age and no
bill for it to be counted as, so it can only be added to the money total.

---

## 5. FIFO application

Unpaid invoices are fetched oldest-first:

```sql
WHERE customer = %s AND docstatus = 1
  AND outstanding_amount > 0.01
  AND is_return = 0 AND is_internal_customer = 0
  AND name != %s
ORDER BY posting_date ASC, name ASC
```

The `name != %s` exclusion is defensive — the current document is a draft
(`docstatus = 0`) and would not match the filter anyway.

The walk happens **in SQL** (`_unpaid_after_advance`), not in Python. A running
total `cum` acts as the FIFO cursor: a bill whose cumulative total stays within the
advance is fully covered and drops out via `cum > advance`; the first bill past the
advance is partially covered and contributes `cum - advance`; every bill after it
contributes in full.

```sql
SUM(outstanding_amount) OVER (ORDER BY posting_date, name) AS cum
...
WHERE cum > %(advance)s
```

No invoice rows cross the wire, so a customer with 10,000 open bills costs what one
with three costs. Verified against the old Python loop on the 40 busiest customers on
avinas1 — identical count, total, oldest date and oldest invoice in every case,
including the partial-coverage branch.

Three values come out and drive the three checks:

| Value | Feeds |
| --- | --- |
| `unpaid_count` | Bill count check |
| `oldest_date` | Days check (oldest bill not covered by advance) |
| `total_unpaid` | Amount check |

---

## 6. The three checks

All three throw; the first one to trip wins and the rest never run.

| # | Trips when | Notes |
| --- | --- | --- |
| 1 | `len(unpaid_list) >= bill_limit` | Advance-adjusted count, not raw invoice count |
| 2 | `(today - oldest_date).days >= days_limit` | `today` = **`doc.posting_date`**, not the wall clock |
| 3 | `total_unpaid + je_debit + grand_total > amount_limit` | The only check that includes the invoice being saved |

Two boundary details that surprise people:

- Checks 1 and 2 use `>=`, so a `custom_bill_count` of **5 permits only 4** unpaid
  bills — the 5th save is blocked. Likewise a 30-day limit blocks on day 30, not 31.
- Check 3 uses `>`, so landing exactly on the amount limit is allowed.

### Worked example

Customer limits: bill = 5, days = 90, amount = 500,000.

| Bill | Date | Outstanding |
| --- | --- | --- |
| SI-001 | 2026-06-01 | 80,000 |
| SI-002 | 2026-06-20 | 120,000 |
| SI-003 | 2026-07-10 | 150,000 |
| SI-004 | 2026-08-01 | 200,000 |

Unallocated Payment Entry 100,000; Journal Entry net −50,000 (a net credit, so it joins
the pool) → **advance = 150,000**.

FIFO walk: SI-001 fully covered (70,000 left over); SI-002 partially covered, 50,000
remains and it becomes the head of the list; SI-003 and SI-004 count in full.

- `unpaid_list` = SI-002 (50,000), SI-003 (150,000), SI-004 (200,000)
- `total_unpaid` = 400,000, count = 3, oldest = SI-002 @ 2026-06-20

New invoice dated 2026-08-20 for 120,000:

1. Count: 3 >= 5 → no.
2. Days: 61 >= 90 → no.
3. Amount: 400,000 + 0 + 120,000 = **520,000 > 500,000 → blocked**, with 100,000 shown
   as available credit.

---

## 7. Known limitations

**No company scoping.** None of the queries filter on `company`. On `avinas1`, a
customer trading with several of the seven companies has a single shared credit pool
across all of them, and an advance deposited with one company retires bills raised by
another. If limits are meant to be per company, all three checks are wrong today.

**Unallocated credit notes are invisible.** `is_return = 0` plus
`outstanding_amount > 0.01` excludes them from the unpaid query, and returns exit at
the top of `validate_sales_invoice`. A customer holding an unreconciled credit note
shows a higher exposure than they actually have.

**The amount limit does not apply to a clean ledger.** `checks_active` is 0 when
advances cover every bill, and `validate_sales_invoice` returns before any check —
so a customer with nothing outstanding can be issued an invoice of any size, whatever
`custom_amount_limit` says. The banner mirrors this and says *"no bills outstanding —
limits not applied"* rather than warning about a save that will succeed. This is
current behaviour, kept deliberately; changing it would start blocking invoices that
pass today.

**Cross-account journal netting.** `je_net` sums `debit - credit` across all three
account names at once, so a debit on *Advance From Customer* nets against a credit on
*Debtors A/c - Domestic* for the same customer. Correct if those debits are advances
being applied; wrong if they are separate receivables. Unconfirmed with accounts.

### Resolved

- ~~JE account names hardcoded~~ — verified against avinas1 on 2026-08-20. All seven
  companies carry `Debtors A/c - Domestic`; GEPL/GLMI/SGU use `Advance Received` and
  NGI/NGG/NGN/NGK use `Advance From Customer`. NGK spells its account
  `Advance from Customer`, which still matches under `utf8mb4_unicode_ci`. In practice
  only Debtors (5 companies) and NGI's Advance From Customer carry any rows today.
- ~~Days basis differs from the banner~~ — `get_credit_position` now takes
  `posting_date` and the form refetches when the date changes.
- ~~`₹` hardcoded~~ — messages use `fmt_money` with the document currency.
- ~~The math exists twice~~ — both entry points call `_credit_state`.

## 8. Performance

Measured on avinas1, worst case (NGN-CUS-00048, 3,706 unpaid bills):

| Query | Cost |
| --- | --- |
| Payment Entry advance | 12 ms |
| Journal Entry net | 25 ms |
| Unpaid window function | 265 ms |

- Four round trips total, all after the early exits.
- The window query dominates and scales with the customer's open-bill count. It is the
  same work the old Python loop did, minus transferring a row per bill.
- `avinashgroup_app/patches/add_payment_entry_party_index.py` adds an index on
  `Payment Entry.party` for the advance aggregate. It is listed in `patches.txt` but
  had **not** run on avinas1 as of 2026-08-20.
- `tabJournal Entry Account.party` has no index; the JE query plan shows a full scan of
  `tabJournal Entry`. Cheap today (4,097 rows), worth watching.
- `avinas1` reads from the replica on `:3307`, so all four reads are replica hits while
  the invoice write goes to the master.
