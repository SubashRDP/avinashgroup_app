# Stock Ledger — How It Works
### Plain-language guide for non-technical people

---

## What is the Stock Ledger?

Think of the Stock Ledger as a **bank statement for your warehouse**. Just like a bank records every deposit and withdrawal with a running balance, the Stock Ledger records every item movement — purchases in, sales out, transfers between warehouses — with a running balance of how much stock you have and what it is worth.

Every single stock movement in ERPNext creates a **Stock Ledger Entry (SLE)**. There are two files that make this work:

| File | What it does |
|------|-------------|
| `stock_ledger.py` (Engine) | The brain — creates entries, calculates prices, validates stock |
| `stock_ledger.py` (Report) | The eyes — shows you all the entries in a readable format |

---

## Part 1: The Engine (`erpnext/stock/stock_ledger.py`)

### The Big Picture

When you submit any stock-related document (Purchase Invoice, Sales Invoice, Stock Entry, etc.), the engine:

1. **Records the movement** — writes a new line in the stock ledger
2. **Calculates the value** — figures out what the stock is worth using FIFO or Moving Average
3. **Updates the balance** — recalculates running totals for this item in this warehouse
4. **Validates** — makes sure you're not selling more than you have (if negative stock is not allowed)
5. **Updates the future** — if the entry is backdated, replays all future entries to keep everything correct

---

### How Prices Are Calculated (Valuation Methods)

ERPNext supports two main ways to decide "what does this stock cost?":

#### FIFO — First In, First Out
Imagine a stack of boxes. When you sell, you sell from the bottom (oldest stock first). The cost of what you sell is the cost of those oldest boxes.

- Example: You buy 10 units at Rs. 90, then 10 more at Rs. 100.
- When you sell 10 units → cost = Rs. 90 each (the first ones in)
- Remaining 10 units are still valued at Rs. 100 each

ERPNext keeps a **queue** of `[quantity, rate]` pairs and peels from the front when stock goes out.

#### Moving Average
Every time you receive stock, the system calculates a new average cost across everything you have.

- Example: You have 10 units at Rs. 90 (value = Rs. 900). You receive 10 more at Rs. 100 (value = Rs. 1000).
- New average = (900 + 1000) / 20 = Rs. 95 per unit

---

### The Journey of a Stock Entry

Here is what happens step by step when you submit a document:

```
You submit a Purchase Invoice
        ↓
1. VALIDATE — Check if cancellation is safe, check serial numbers
        ↓
2. RECORD — Write the Stock Ledger Entry to the database
        ↓
3. CALCULATE VALUE — Run FIFO or Moving Average to find the rate
        ↓
4. UPDATE BALANCE — Update qty_after_transaction and stock value
        ↓
5. UPDATE BIN — Update the quick-lookup Bin table (used for availability checks)
        ↓
6. VALIDATE FUTURE — If backdated, check if future entries go negative
        ↓
7. REPOST FUTURE — If backdated, replay all future entries to fix their valuations
```

---

### Key Concepts Explained Simply

#### Stock Queue
The engine keeps a mental "queue" of stock layers for FIFO. Each layer is `[how many, at what price]`. When stock goes out, it takes from the front. When stock comes in, it adds to the back.

```
Queue before sale: [[100 units @ Rs.90], [50 units @ Rs.100]]
You sell 120 units:
  → Take all 100 from first layer (Rs.90 each)
  → Take 20 from second layer (Rs.100 each)
Queue after sale: [[30 units @ Rs.100]]
```

#### Valuation Rate = 0 (The Problem We Fixed)
When the stock balance goes **negative** (more sold than received), ERPNext cannot calculate a FIFO rate — there is nothing in the queue. So it records `valuation_rate = 0`. This means the cost of those sales is recorded as zero, which makes profit look artificially high. This was the exact problem with `NGK-ITEM-00008`.

#### Backdated Entries & Reposting
If you submit a Purchase Invoice dated in the past:
- The engine inserts the entry at that past date
- It then has to **replay** (repost) all entries that came after, because their balances were calculated without this purchase
- This replay is called **Repost Item Valuation**
- If `allow_negative_stock = 0` and the replay hits a negative point, it stops (Skipped/Failed)
- If `allow_negative_stock = 1`, the replay continues through negative points

#### Negative Stock Validation
The function `validate_negative_qty_in_future_sle()` scans all future entries after the current transaction and checks: "does the balance go below zero at any point?"
- If yes and negative stock is not allowed → error is thrown
- If yes and negative stock is allowed → allowed to proceed

#### The Bin Table
The `Bin` is a summary table — one row per item per warehouse — storing the current quantity and value. It's updated after every transaction for fast availability lookups. Think of it as the "current balance" while the SLE is the full "statement history."

---

### Special Cases

#### Serial Numbers
Some items are tracked individually (each unit has its own serial number, like a gas cylinder). The engine validates that:
- A serial number isn't sold before it's purchased
- The same serial number isn't used in two transactions at the same time

#### Batch Numbers
Some items are grouped in batches (a production batch of medicine, for example). Valuation can be done per-batch — each batch has its own cost.

#### Stock Reconciliation
When you do a physical count and the system count doesn't match, you submit a Stock Reconciliation. This is a special entry that **sets** the balance to a specific number, rather than adding/subtracting. The engine treats this as a hard reset point.

#### Landed Costs
When additional costs arrive after a purchase (freight, customs, etc.), a Landed Cost Voucher is submitted. This triggers a repost that updates the `valuation_rate` on all existing SLEs for that purchase — so the true total cost is reflected in the stock value.

---

### What Can Go Wrong

| Problem | Cause | Fix |
|---------|-------|-----|
| `valuation_rate = 0` on sales | Stock was negative when sale happened | Create stock transfers so warehouse has stock before selling |
| Repost jobs Skipped | `allow_negative_stock = 0` blocks replay | Enable `allow_negative_stock` |
| NegativeStockError on submit | Selling more than available | Either add stock or enable negative stock |
| Repost takes very long | Large number of future SLEs to replay | Runs in background worker; check Repost Item Valuation status |

---

## Part 2: The Report (`stock/report/stock_ledger/stock_ledger.py`)

### What It Does

The Stock Ledger Report is the **view** of all stock movements. It reads from the SLEs written by the engine and presents them in a table showing:

- Date and time of each movement
- Item name and details
- How much came in (In Qty) and went out (Out Qty)
- Running balance after each movement
- The valuation rate and total value at each point
- Which document caused the movement (Purchase Invoice, Sales Invoice, Stock Entry, etc.)

---

### How the Report is Built

```
You click "Run" on the Stock Ledger report
        ↓
1. FILTER ITEMS — Which items to show? (by item, brand, item group)
        ↓
2. CALCULATE OPENING BALANCE — What was the balance just before the report start date?
        ↓
3. FETCH ENTRIES — Get all SLEs in the date range matching your filters
        ↓
4. EXPAND BUNDLES — If serial/batch bundles exist, break them into individual rows
        ↓
5. BUILD ROWS — For each SLE, calculate running balance and format the row
        ↓
6. DISPLAY — Show the final table with all columns
```

---

### Opening Balance
The report does not start from zero. It first finds the **last entry before your report start date** and uses that as the starting balance. So if you run the report from 2024-01-01, it will show what the balance was on 2023-12-31 as the first line, then all movements from January onward.

---

### Key Columns Explained

| Column | What it means |
|--------|--------------|
| **In Qty** | Stock that came IN (purchases, transfers in, returns from customer) |
| **Out Qty** | Stock that went OUT (sales, transfers out, returns to supplier) |
| **Balance Qty** | Running total after each movement |
| **Incoming Rate** | The price per unit at which this stock was received |
| **Avg Rate (Balance Stock)** | The weighted average cost of ALL stock currently in the warehouse |
| **Valuation Rate** | The rate used to value this specific transaction |
| **Balance Value** | Balance Qty × Avg Rate = total value of stock in warehouse |
| **Value Change** | How much the total stock value changed from this one transaction |
| **Voucher Type** | What kind of document created this entry (Sales Invoice, Purchase Invoice, etc.) |
| **Voucher #** | The specific document number you can click to open |

---

### Warehouse Hierarchy
If you have parent and child warehouses (e.g., "All Warehouses > Nepal Gas > Gas Purchase/Stock"), the report supports filtering at any level. Selecting a parent warehouse shows entries from ALL child warehouses beneath it.

---

### Item Group Hierarchy
Similarly, item groups are hierarchical. Filtering by "Gas Items" shows all items in that group and all sub-groups beneath it.

---

## Summary: How the Two Files Work Together

```
SUBMIT TRANSACTION
      ↓
ENGINE writes SLE → calculates FIFO/avg rate → updates Bin → validates negative stock
      ↓
                    (background worker)
ENGINE reposts future SLEs if backdated → fixes valuation rates on all affected entries
      ↓
REPORT reads all SLEs → applies filters → calculates opening balance → displays table
```

The engine writes the data. The report reads it. Every number you see in the Stock Ledger Report was calculated and stored by the engine when the original transaction was submitted (or reposted).

---

*Document covers: `erpnext/stock/stock_ledger.py` (engine) and `erpnext/stock/report/stock_ledger/stock_ledger.py` (report)*
