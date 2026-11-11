# CEO Dashboard

Route: `/app/ceo-dashboard` (desk page). Built and checked on
**demo-nggroup.raindropinc.com**, 2026-11-08 (version 2 the same day;
version 3 on 2026-11-09: the brief on top, and the Money section).

## How it works, in one picture

```
Sales Invoice (+ Items) ─┐  one SQL pass, three fiscal years,  ┌─ sales [slot, company, customer, segment,
Payment Entry (Receive) ─┼─▶ cached 30 min                      ┤         kg, gas Rs, net Rs, bills]
Customer / Customer Group┘  (ceo_dashboard/api.py)             └─ coll  [slot, company, customer, Rs]
                                       │
                                       ▼  ~1.8 MB JSON, once
                      browser filters in memory on every click
                      (public/js/ceo_dashboard.js)

GL Entry (cash/bank, party balances) ┐  second call, cached 30 min   ┌─ balances at each month end
Purchase Invoice items in Kg         ┴▶ (ceo_dashboard/money.py)   ─┤   and on the data-through day
                                                                     └─ gas bought [month, company, kg, Rs]
```

The page draws the brief from the first call at once and fills the money
tiles when the second arrives (~5 s cold).

`slot` is a half-month on one timeline (24 per fiscal year, Shrawan first).
The second half of a month only holds days after the "data through" day in the
"data through" month. That makes every period a slot range ending at "data
through", and "the same period last year" is the same range minus 24: like for
like, even inside a part month.

## What is on the screen

**Look (2026-11-09, the CEO's call): figures only.** No change badges, no
"a year earlier" lines, ticks or columns, no Falling / Rising / New / Lost
customer tabs, no Price alerts card, no card subtitles, tooltip notes or page
footnote. All of it is behind one switch, `SHOW_COMPARISON` in
`public/js/ceo_dashboard.js` (the comparison data is still computed). Tiles are
label, figure and 24-month sparkline. Colours moved off blue: deep teal accent,
amber second series (collected, purchase price), segments teal / amber / plum,
limit-use ramp in teal; all validated with the dataviz validator in light and
dark. Parts of the description below (badges, subtitles, comparisons) apply
only with the switch on.

**Zones (2026-11-10).** The page is five tinted panels so each part is found
at a glance: Sales (mint), Buying (pink: gas margin / purchase price, we owe
suppliers), Money (sand: cash and bank, customers owe us), Credit and dues
(lilac), Customers (sky). Cards stay on the normal card surface inside each
panel; the six top tiles take their panel's tint, in the same order (Sales,
Buying, Money). Tokens: `[data-zone=…]` in `ceo_dashboard.css`.

**Gas margin off (2026-11-10, the CEO's call).** Five top tiles; Buying holds
only "We owe suppliers". Most companies have no gas purchase bills, so the
margin covered ~23% of 83/84's volume. Code kept behind `SHOW_MARGIN` in
`ceo_dashboard.js` (money.py still sends the purchase rows).

**Polish pass (2026-11-11).** Tiles: the unit (MT, Rs, Cr) set small beside a
large figure, one line of facts under it (customers and bills; collected;
cash/bank split; advances; bank loans). Bar charts: wide bars with the value
printed on top when there are 14 or fewer (`BAR_LABELS_MAX`), no legend for a
single series. Line charts: soft area under a lone line, marker only on the
latest point, a short axis title on short charts. Scorecard: Share, Bills and
data bars in cells, "Collected %" as a mini bar; Rs/kg hidden (`SHOW_RATE`,
follows `SHOW_PRICE_CHART`); segment rows show net sales (or volume) in its
place. By company shows full names under the abbreviation. Suppliers: bars
first, month-end line after. A section strip (Sales · Buying · Money · Credit
· Customers) in the sticky bar jumps down the page; Credit is omitted for a
past year. The "Average price per kg" card is off (`SHOW_PRICE_CHART`).

**Chart options behind a funnel button (2026-11-11).** Every time chart
(trend, billed and collected, cash and bank, customers owe us, we owe
suppliers) has a funnel button beside Table that opens a small panel.
All of them: **Shape** Bars / Line. The trend chart also has **Show by**
(follow the period, half-year, quarter, month, half-month, week = 7-day
blocks from 1 Shrawan, day), **Add** (Purchases = Purchase Invoices,
Collected = Payment Entries, Expenses = GL root type Expense as booked; in
MT only Purchases), and **Compare with** (up to two other fiscal years,
dashed lines, every line in its own colour: teal, amber, plum, rose,
blue, olive in order, `--ceo-k0..5`, validated in both modes). In Bars shape
only the first series of the chosen year is
bars; everything it is compared with is a line over the bars (the CEO's
call, 2026-11-11). With any of those set the trend chart is drawn
from `ceo_dashboard/series.py` `get_series`: every day of the timeline per
company (sales and collections also per segment and inter-company; ~400 KB,
~12 s cold, cached 30 min, fetched the first time it is needed), bucketed in
the browser (`cmpBuckets`), so a switch is instant. With nothing set it is the
original period chart. Company, segment and inter-company selections apply; a
customer selection does not. State in the URL: `sh=` (shapes), `cg=`, `cs=`,
`cy=`.

**Fiscal years added together:** the Fiscal year box is a tick list. One
year ticked = that year, with the period buttons. Several ticked (up to 6) =
those years added together: the period buttons are replaced by "Whole years
added together", every figure, list and table sums the picked years (the
latest only up to "data through"), and each year is compared with the year
before it (82/83 + 83/84 vs 81/82 + 82/83). The main charts run month by month
across all picked years; a month bar opens that month day by day. The server
sends every picked year plus one before the earliest (`years_back` on
`get_dashboard`, `get_money`, `get_daily`; at most `api.MAX_YEARS_BACK`), so a
wide span is a bigger first load (4 years ≈ 2.4 MB, ~4 s cold, then cached).
Checked 2026-11-09: 82/83 + 83/84 = 42,425 + 6,366 = 48,791 MT.

Inside the page, the period window marks each half-month slot with two flags
(1 = in the period, 2 = in the comparison), because with years added together a
year can be both (82/83 is in the period and is 83/84's comparison).

**Filter bar layout** (2026-11-11): the filters on one line, ending with the
exact date range of the period on screen ("1 Shrawan 2083 – 11 Bhadra 2083";
it replaced "Data through", which is still in its tooltip); the section buttons
(Sales · Buying · Money · Credit and dues · Customers) on their own line below.

**Filters (one sticky row):** fiscal year (tick list, see above) · period (Week, Month, Quarter,
Year to date, 12 months) with a second dropdown for Week / Month / Quarter:
which week (Sunday to Saturday, week 1 = 1 Shrawan to the first Saturday,
latest first), which month (Shrawan to Ashadh; months after "data through"
listed but greyed), which quarter (Q1 Shrawan–Ashwin … Q4 Baisakh–Ashadh) · measure (Volume MT / Sales Rs) · company picker (dropdown
with search and tick boxes) ·
inter-company on/off · "data through" date · print.

**Top figures** (the first screen): six figures, each with its change and a
24-month sparkline: LP Gas volume (large), net sales, gas margin per kg, cash
and bank, customers owe us, we owe suppliers. Balances compare with the same
day a year earlier; clicking a money figure jumps to the Money section. The
brief heading, headline sentence, "What changed" / "Needs attention" lists and
the Books check were removed at the user's request (2026-11-09): the
dashboard shows figures, not commentary.

**Where it comes from:** 24-month trend (bars, with the same month a year
earlier as a line; shaded months = the period) · by company (share bar + bars
with a comparison tick) · company scorecard (volume, sales, Rs/kg, collected,
collection %, customers, 24-month sparkline) · **customer segment, full width**
(large ring + one row per segment: volume with comparison bar, change, share,
customers, volume per customer, Rs/kg, 24-month trend) ·
Rs/kg over 24 months · billed vs collected over 24 months. Charts with a Table
button switch to the numbers.

**Credit and dues** (from the credit-control snapshot, see below): customers on
hold now and why (amount / days / bills), owed after advances, advance held,
customers near their amount limit · owed by age of the oldest unpaid bill
(plus "no bill (journal debit)") · credit by company · use of amount limit ·
customer list (On hold / Near the limit / Owe the most / Advance holders),
each with the volume they usually take a month. Follows company / segment /
customer selections; the period switch does not apply (it is a position, not
a period). A customer's drill-down panel shows their credit position too.

**Money** (ledger balances on the data-through day; see "Money figures"
below): cash and bank (month-end line against a year earlier, and per company:
cash in hand, bank, total, bank loans) · gas margin per kg (sale and purchase
price lines, per company table for the period) · customers owe us (month-end
line, per company bars) · we owe suppliers (month-end line, largest balances
with their largest open bill, linked).

**Customers and prices:** customers (Largest / Falling / Rising / New / Lost,
search) · Gone quiet (regular buyers with no bill for 30+ days) · Price alerts
(a company's Rs/kg 12%+ away from the median company that month).

**Charts follow the period** (the main trend, price per kg, billed and
collected, gas margin): Week = its 7 days (Sun–Sat, the BS date under each),
Month = day by day, Quarter = day by day across its three months (numbers on
the 1st, 8th, 15th, 22nd, 29th; month names where a month starts), Year to date = the
fiscal year month by month (Shrawan to Ashadh), 12 months = the last 12
months. The line is always the same days / weeks / months a year earlier.
Click a month bar to open that month day by day; click a day in the quarter
view to open its month. (The quarter was week by week until 2026-11-09; the
user found 14 Sunday–Saturday weeks in a 93-day quarter confusing.) Clicking several months (Ctrl) keeps the
24-month view. Still 24 months: the figure sparklines and the month-end
balance charts in Money (balances are only kept at month ends).

Every time chart says what it shows: the description names what one bar /
point / line is, the x axis is titled with what it steps through (month, day of
the month, day of the week, Sunday–Saturday week, month end) and the y axis
with its unit (metric tonnes, rupees with L = lakh and Cr = crore, rupees per
kg).

Day and week charts need day rows: `charts.get_daily(fiscal_year, from_date,
to_date, prev_from, prev_to, customer=None)` returns them per day x company x
segment x inter-company (~1 s for a quarter plus last year's quarter), or one
customer's when a customer is selected.

**Comparisons:** a past month or quarter is compared with the same month or
quarter a year earlier; the current one with the same days last year; a week
with the same weekdays 52 weeks earlier (so a Sunday–Saturday week is compared
with a Sunday–Saturday week).

**How weeks work:** the main fact table is half-month grain, so a week cannot be
cut from it. Picking a week calls `periods.get_days(fiscal_year, from_date,
to_date)` (≤ 7 days, inside the year, not past data through; ~0.2 s) and the
rows are folded into the in-memory table on two extra slots (100 = the week,
76 = a year earlier), so every chart and filter works as for a month. The
24-month charts stay monthly.

**Look:** follows Frappe's own dashboard widgets (`frappe/public/scss/desk/desktop.scss`
`.widget`, `.number-widget-box`): 1px border and no shadow on cards, the desk's
large radius, small uppercase muted labels on the figures, medium-weight card
titles with a small muted line under them, change figures as plain coloured
text with an arrow (no pills), tiny uppercase table headers, 16px between
cards. The user found the stock Dashboard cleaner (2026-11-09) and asked to
learn from it.

**Buying panel** (2026-11-11; it used to hold only "we owe suppliers"):
small figures (purchases net of discount before VAT, LP Gas bought in MT with
the average purchase Rs/kg, paid to suppliers via Payment Entry, suppliers and
bills) · purchases over time (follows the period like the sales chart, in the
panel's colour) · purchases by company · what we buy (LP Gas, Direct
expenses, Indirect expenses, Fixed assets, Other, from the Item Group name;
the group codes differ per company, the names do not) · top suppliers (click
one: their Purchase Invoices in the period) · we owe suppliers (ledger: the
largest balances and the month-end trend side by side, stacked on narrow
screens). A "Purchases" figure joins the top row. Company and inter-company
filters apply (a supplier named like one of our companies is inter-company);
segment and customer do not, purchases have neither. Data from
`buying.get_buying`, ~0.2 s and ~120 KB for three years. 82/83 on
demo-nggroup: Rs 204 Cr bought, 18,726 MT LP Gas at Rs 94.72/kg, Rs 251 Cr
paid; 83/84 has few purchase bills entered so far.

Fixed the same day: ticking fiscal years threw "applyFys is not defined" (the
auto-apply added on 2026-11-10 called a function that was never written), so
changing or adding years did nothing.

**Polish pass, 2026-11-11** (things that made the page look unfinished):
month charts stop at the current month instead of drawing the year's empty
future months; a value axis goes below zero only for a real negative (5%+ of
the largest value), not for a few returns; flow sparklines (volume, sales,
purchases, receipts) leave off the current part month, which is always low;
crowded axes print three-letter labels on every 2nd / 3rd bar instead of one
letter on each; the six top labels stay on one line so the figures share a
baseline; "Gone quiet" lists 11 rows to match the customer table beside it.

**Money balance charts follow the period** (2026-11-11): cash and bank,
customers owe us and we owe suppliers show the month ends of the chosen fiscal
year so far (Shrawan to the current month), of every picked year when years
are added together, or of the last 12 months for "12 months". Before, they
always showed the last 24 month-ends, a leftover from before the other charts
followed the period. Week / month / quarter show the fiscal year's month ends
(balances are only kept at month ends). The small sparklines in the top
figures still show 24 months.
Each balance chart starts with an **Opening** point (the month end before the
first month shown: what the period started with) and carries a line of three
figures above it: Opening · Now (Closing for a past year) · Change.

## Interaction rules

- Pick **companies** (dropdown, or click one; Ctrl/Shift adds): the page shows
  only those companies. Lists, the scorecard (total = "Picked companies"),
  credit, cash, margin and price-alert tables drop the others, and charts
  draw only the picked companies (no faint whole-group bars). User's call,
  2026-11-09: "if I choose one or two companies put them only".
- Click a **segment**: highlights. Bar charts keep the bar for all segments
  faint and draw the picked segment solid inside it; figures and tables
  narrow to it.
- Click a **month** on any 24-month chart: the period becomes that month.
- Click a **customer**: everything narrows to that customer.
- **›** on any company or customer opens a side panel: figures, 24-month
  sparkline, segment split and top customers (company), or the actual bills
  in the period (customer, read through `frappe.get_list` so permissions
  apply), and a button to open those Sales Invoices in the list view.
- The whole view is in the URL (`?p=r12&m=amt&co=NGN&seg=Bulk...`; `pm`,
  `pq`, `pw` = picked month 0-11, quarter 0-3, week number), so it can
  be bookmarked or sent. Esc closes the panel. Print / PDF has its own layout.

## Rules worth knowing

- **Built for a growing list of companies.** Nothing is laid out one-per-company
  side by side and no company owns a colour (only ~8 colours stay
  distinguishable): company bars use one accent colour and are named; the
  share bar shows the largest 6 and folds the rest into "Other"; company lists
  show the largest 8 with "Show all" (a selected company always stays visible).
  A new company appears automatically once it has bills.

- **Data through** is today (a past fiscal year: its last day), for every part
  of the page. Until 2026-11-11 it was the last day with normal sales billing
  (on demo-nggroup 27 Aug 2026 / 11 Bhadra 2083, leaving out 86 later bills);
  the CEO asked for today, because purchases, journals and payments carry on
  after sales billing stops. One helper, `api._data_through`, holds the rule.
- **Inter-company sales are hidden by default.** Customers whose name matches
  one of our companies (ignoring "Pvt. Ltd." and punctuation), or with
  `is_internal_customer` set: about Rs 10 Cr of 83/84's Rs 89.8 Cr on
  demo-nggroup. Nobody has set `is_internal_customer`; setting it on those 15
  customers would make the match exact.
- **Segments** fold the per-company Customer Group names into Dealer / Bulk /
  Other by the start of the name.
- **Volume** is the stock qty of items whose stock UOM is Kg (LP Gas).
- **Collected** shows "no comparison" when the comparison period has receipts
  for under 20% of its billing (Payment Entries start in 82/83 here).

## Money figures (money.py)

- **Cash and bank** = leaf accounts with root type Asset and account type Cash
  or Bank. Account type "Bank" is also set on term / HP / TR / OD loans (root
  type Liability) and on inter-company current accounts (account named after
  one of our companies). Loans are shown apart as "bank loans"; inter-company
  accounts are left out.
- **Customers owe us / we owe suppliers** = GL balance per party on Receivable
  / Payable accounts; positive owed, negative advance, never netted across
  parties. Inter-company parties (name matches a company) follow the
  inter-company switch. This is the ledger's view of every party; Credit and
  dues is credit control's view of customers with limits, so the two differ.
- **Gas margin per kg** = sale price minus that company's gas Purchase Invoice
  price (items in Kg) in the same fiscal month, or the month before. The stock
  ledger cannot be used: every Sales Invoice stock entry has valuation rate 0.
  Only kg in a company-month with a purchase price count; the tile says what
  share of volume that is and greys the figure under 50%. On demo-nggroup
  only NGI, NGK (to Chaitra 82/83), GEPL and GLMI have gas purchase bills, so
  83/84 margin covers about a quarter of volume.
- Selections: company applies to all money figures; segment and customer only
  to customer balances (cash, suppliers and the margin's purchase price are
  per company).

**Ledger figures that cannot be right** (seen 2026-11-09, shown as they are,
not flagged on the page): NGI-PI-76/77-00001 (Rs 1,130 Cr, nearly all of "we
owe suppliers"); NGI's 4 bank accounts below zero (−Rs 134 Cr, Global IME
10101010000310 −Rs 113 Cr); NGI cash in hand Rs 116 Cr; customers owing about
Rs 1,900 Cr group-wide until Shrawan 2083, cleared to Rs 11.7 Cr in Bhadra by
journal entries (e.g. GEPL-JE-83/84-00047 on 18 Aug 2026). The user is
handling the data.

## Credit-control snapshot

`ceo_dashboard/credit_snapshot.py` runs credit control's own `_credit_state`
for every customer with a limit and saves the result to
`sites/<site>/private/ceo_dashboard/credit_snapshot.json`. One customer at a
time costs ~4 queries; 3,507 customers took 460 s on demo-nggroup, so it cannot
run on page load.

- **Schedule:** hooks.py cron `20 */4 * * *` (every 4 hours at :20). The cron
  entry only queues `build` on the long queue (cron jobs run on the default
  queue, whose timeout is shorter than a build).
- **On demand:** the Refresh button in the section (System Manager / Accounts
  Manager) queues one; only one runs at a time.
- **New site:** the Scheduled Job Type is created by `bench migrate`; on
  demo-nggroup it was inserted by hand (`insert_single_event`) on 2026-11-08.
- "As of" is the dashboard's "data through" day, so a data copy does not age
  every bill by the gap after billing stopped.
- An amount limit of Rs 100 or less is shown as **cash only** and left out of
  the limit-use bands: 2,441 customers on demo-nggroup have Rs 1-100, and 164
  of the 169 "over amount limit" holds are such customers with any unpaid bill.

## Data problems the dashboard surfaced (not fixed)

- **NGN-SB-82/83-09937 and -09938** (2 Apr 2026, Grihalaxmi Gas Company): 710
  and 712 entered in UOM "1 MT" at Rs 1,515, a 14.2 kg cylinder price. Booked
  as 1,422 MT for Rs 21.5 L (Rs 1.52/kg); really about 1,422 cylinders
  (~20 MT). Inflates NGN Chaitra 82/83 by ~1,400 MT and shows as the Rs/kg
  dip and the top price alert.
- **NGI-PI-76/77-00001**: a Rs 1,130 Cr test Purchase Invoice (Diesel
  Generator, back-dated 2020, made 2026-11-06) with asset NGI-AST-00005 and 9
  depreciation entries (Rs 837 Cr). Distorts NGI's payables and expenses; it
  does not touch the sales figures shown here.
- **120 customers owe Rs 2.49 Cr through journal debits with no Sales Invoice
  behind them** (credit control's `je_debit`). They have no bill date, so they
  cannot age; shown as their own row in the ageing chart.
- NGI's collected % is low because most of its receipts went through Journal
  Entries, which are not counted.

## Not here yet

Fixed assets; profit beyond the gas margin (expenses, P&L). Targets / "vs plan" are deliberately out: the
dashboard shows actual data only (user's decision, 2026-11-08).

## Gotchas found the hard way

- `frappe.require` cannot load a path with `?v=` (it takes the file
  extension from the query string), and `/assets` is cached for a year. The
  page loader adds its own script/link tags. **Bump
  `CEO_DASHBOARD_ASSET_VERSION` and the Page `modified` stamp on every change**
  (the stamp makes browsers drop the cached page script from localStorage),
  then re-import the Page **and run `frappe.clear_cache()`**: each user's
  cached boot info carries the Page's old `modified`, and until it is cleared
  the browser keeps running the old page script (seen 2026-11-09).
- Gunicorn keeps an imported Python module until workers recycle
  (max-requests 500) or a bench restart. Version 2 moved the code to a new
  module (`api.py`) so running workers load it fresh; a standalone
  `get_dashboard(force=1)` refreshes the cache.
- When testing with headless Chrome, stop it by PID found from `ps`, never
  `pkill -f`/`pgrep -f` with the port string: that matches and kills the
  calling shell.

**Period dropdown (2026-11-11).** The period buttons and the week / month /
quarter select were folded into one dropdown beside the fiscal year, so the
filter bar is one line. Measure buttons read Volume / Rupees.
