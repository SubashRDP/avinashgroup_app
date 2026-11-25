# Inventory Report Standard

How stock is reported across the seven companies, and exactly what each column of
the **Inventory Report** (`/app/query-report/Inventory Report`) means. Written
November 2026, based on the four standard inventory reports in common use (value, performance,
forecasting, stock summary — see the ShipBob guide
<https://www.shipbob.com/blog/inventory-report/>) and adapted to how stock is
actually posted here.

Code: `avinashgroup_app/avinash_group_app/report/inventory_report/`.
The Material In Out Report is unchanged and stays for the sales view (branch,
price list, selling UOM).

## Rules

1. **Count stock in the stock UOM, from the Stock Ledger.** Gas is bought in Kg
   / MT and sold in 14.2 KG / 7.1 KG cylinders; only the Stock Ledger Entry has
   both in Kg. Reading invoices directly (as Material In Out does) cannot give
   stock on hand.
2. **One row per company + item** by default. Choose *Group By = Warehouse* for
   one row per warehouse. Branch and price list are sales dimensions, not places
   where stock is kept, so they are not columns here.
3. **Never hide negative stock.** A negative Closing is shown in red with status
   *Negative Stock*. It means a purchase, an opening entry or a transfer is
   missing from the books. Fix the books, not the report.
4. **A blank ratio means "cannot be worked out"**, never zero. Example: Days of
   Cover is blank when nothing was sold or Closing ≤ 0.
5. **Use the same period for every comparison.** Turnover and averages depend on
   the period length; compare months with months, not months with quarters.

## Columns

Period = From Date … To Date, both included. *Days* = number of days in the period.

### In / Out (stock summary)

| Column | Formula |
| --- | --- |
| Opening | Sum of all stock movements before From Date |
| In (Purchased) | Purchase Receipt + Purchase Invoice (update stock) in the period; purchase returns net out |
| Out (Sold) | Delivery Note + Sales Invoice (update stock) in the period; sales returns net out |
| Transfer / Adjust | Everything else (Stock Entry, Stock Reconciliation). Transfers cancel out in the item view |
| Closing | Opening + In − Out + Transfer / Adjust |

### Value

| Column | Formula |
| --- | --- |
| Rate | Last purchase rate (per stock UOM) for the company + item on or before To Date |
| Closing Value | Closing × Rate, or 0 when Closing ≤ 0 |

Rate is the **last purchase rate**, not ERPNext's moving average. The "(Sales)"
warehouses run negative, so ERPNext values them at 0. Book valuation for the
accounts stays with the stock Stock Balance report.

### Performance

| Column | Formula | How to read it |
| --- | --- | --- |
| Avg Daily Out | Out ÷ Days | Daily sales speed |
| Days of Cover | Closing ÷ Avg Daily Out | Days the current stock lasts at this speed |
| Turnover | Out ÷ ((Opening + Closing) ÷ 2) | How many times the stock was sold through in the period; higher is better |
| Sell-Through % | Out ÷ (Opening + In) × 100 | Share of the stock you had that was sold |
| Last In / Last Out | Latest purchase / sale date, ever, up to To Date | |
| Days Since Out | To Date − Last Out | |
| Movement | see below | |

**Movement** (*N* = filter "Non-moving After (Days)", default 90):

- **New** — no sale in the last *N* days, but bought in the last *N* days.
- **Non-moving** — no sale and no purchase in the last *N* days.
- **Slow** — sold recently, but Days of Cover > *N*.
- **Fast** — everything else.

### Forecast / reorder

| Column | Formula |
| --- | --- |
| Next-Period Need | Avg Daily Out × Forecast Days (filter, default 30) |
| Suggested Purchase | Next-Period Need − Closing (positive stock only), never below 0 |

**Status**, checked in this order:

| Status | Rule | Action |
| --- | --- | --- |
| Negative Stock | Closing < 0 | Find the missing purchase / opening / transfer |
| Dead Stock | Non-moving and Closing > 0 | Sell, transfer or write off |
| Out of Stock | Closing = 0 and there is demand | Buy now |
| Reorder | Closing < Next-Period Need | Buy Suggested Purchase |
| Overstock | Days of Cover > *N* | Stop buying |
| OK | otherwise | |

## How often to run it

- **Weekly** for gas (fast-moving, high value): Group By Item, last 30 days.
- **Monthly** for everything else, the BS month as the period.
- **At fiscal year close** (mid-July): one full-year run per company as the
  year-end stock statement.

## Known gaps (Nov 2026, seen on the avinasdemo copy)

- LP Gas shows large negative closing for NGI, NGN, NGG and NGK. Stock is bought
  into "Gas Purchase / Stock" and sold from "Gas Purchase / Stock (Sales)", with
  no transfer between them, and the company totals are negative too. Purchases or
  opening stock appear to be missing.
- Consumption of consumables (Material Issue) counts as Transfer / Adjust, not
  Out, so those items read as New or Non-moving.
- Forecast is a straight average of the period. It ignores seasonality (winter
  gas demand); run a same-period-last-year comparison by hand until a seasonal
  forecast is built.
