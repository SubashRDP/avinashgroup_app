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

**District map, branch sales, sales and returns** (Sales panel, 2026-11-11):
- **By district**: a choropleth of Nepal's 77 districts (five steps of one
  colour on a square-root scale, because Kathmandu is several times any other
  district), the five largest named on the map, and the ten largest listed
  beside it with their customers. A bill's city (`custom_citytown`) is the
  district name in practice; each customer is placed in the district on most
  of their bills (only 11 customers ever have two), so the map is summed in
  the browser from the sales rows and follows every filter. Spellings and
  towns are mapped in `sales_breakdowns.CITY_ALIASES`; what matches nothing is
  "No district on the bill". Outlines: `public/js/ceo_nepal_districts.json`,
  built by `scripts/make_ceo_district_map.py`. **It is the official 2020
  political map (the "chuchche" map, with Limpiyadhura, Lipulekh and Kalapani
  in Darchula)**: the clients are Nepali, so the pre-2020 outline is not
  acceptable (the CEO's call, 2026-11-11; the first version used
  mesaugat/geoJSON-Nepal, which stops Darchula at 30.25 N). Source: the Survey
  Department's district boundaries from the National GeoPortal of Nepal, as
  GeoJSON in github.com/manishacharya60/nepal-geojson (that repo states no
  licence; the underlying data is the government's published boundary set).
  23 MB simplified to 60 KB. Check for any future source: Darchula must reach
  about 30.47 N.
  Kathmandu, Bhaktapur and Lalitpur are the biggest market and the smallest
  districts (Bhaktapur is ~20 px wide and sat under the "Kathmandu" label), so
  they are drawn again, enlarged and named, in a **Kathmandu Valley inset** in
  the map's empty top-right corner, with a marker on the main map.
- **Sales and returns**: billed, returned, net, return rate and return bills
  for the period; returned amount over time (follows the period); and why it
  came back (the hand-typed reason folded into Gas leakage, Empty cylinder
  shortage, Order cancelled, Full return, Other or not stated).
- **By branch**: sales of bills that carry a branch (`custom_branch`), by
  branch name. Only GEPL puts a branch on every bill; for a company that
  uses branches on some bills the rest shows as "No branch on the bill";
  companies that never use branches are not listed.
The CEO turned down a tax-office (CBMS) sync card as not worth showing.

**Districts are a filter** (2026-11-11): click a district on the map, in the
Kathmandu Valley inset or in the list beside it and the page narrows to it
(Ctrl/Shift adds more; click again or the chip to clear; kept in the link as
`di=Kathmandu,Lalitpur`). The map itself keeps every district drawn and
highlights the pick. It works through the customer: each customer has one
district, so sales, collections, customers, credit and customer balances
filter in the browser. Returns and branch rows carry the customer's district;
day-by-day charts ask the server for the picked districts' customers
(`charts.get_daily(districts=...)`). Not split by district: buying, cash and
bank, supplier balances, the month-end receivable trend and the compare chart.

**"Show by" fits the period** (2026-11-11, the CEO's call):
- With nothing chosen the main chart uses the unit just below the period: a
  year or 12 months by month, a **quarter by month** (it was day by day), a
  month and a week by day. The option reads "Follow the period (Month)".
- A unit as large as the period or larger is greyed out: Quarter leaves
  Month, Week and Day; Month leaves Week and Day; Week leaves Day. (Units:
  Half-year, Quarter, Month, Week, Day. Half-month was removed 2026-11-11:
  not how the business is read in practice.) A saved choice that no longer fits falls back to
  "Follow the period".
- A chosen unit applies **inside the period**: Quarter + Week draws that
  quarter's weeks, counting only the quarter's days (before, it redrew the
  whole fiscal year). For Year to date and 12 months it still covers the
  fiscal year. Compared years show the same days of their own year.

**Money for a week, month or quarter** (2026-11-11, the CEO's call): no
month-end chart and no closing figure. Each of cash and bank, customers owe
us and we owe suppliers shows the **opening** balance on the period's first
day and **what happened in the period**: came in / went out (cash), billed /
received (customers), billed to us / paid (suppliers), and the net change,
plus the same three columns per company. The three top figures show the
opening balance with the movement under it, without a sparkline. Year to
date, 12 months and added years keep the opening-plus-month-ends chart.
Data: `period_balances.get_period_balances(fiscal_year, from_date, to_date)`
reads the ledger for the exact dates (~2 s, cached 30 min per period).
On demo-nggroup, Baisakh to Ashadh 2083 shows "went out Rs 0": the ledger
has no cash or bank payments in those months (a gap in the data copy).

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

Fixed assets; profit (a P&L). Expenses by head are shown since 2026-11-13, see the end of this file. Targets / "vs plan" are deliberately out: the
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

## Review fixes (2026-11-13)

Two read-only reviews (code and page) were run; these findings were fixed.

- **Stale answers.** `load()` bumps `st.gen`; every loader (dashboard, money,
  buying, breakdowns, series, week) drops an answer to an older request. The
  week loader also checks that the answer is for the week on screen.
- **Selection by code.** A picked customer is carried across reloads by
  customer code (`st.custWant`, `resolveCust()`), companies by abbreviation.
  Indexes into the customer list shift whenever the list is rebuilt.
- **Came in / went out** (week, month, quarter) leaves out money moved between
  a company's own cash and bank accounts (`period_balances` → `transfers`).
- **Group Collected %** is blank when companies with no receipts recorded hold
  more than `COLL_GAP_MAX` (1%) of the billing. Same rule in the tile and the
  scorecard total.
- **Scorecard** lists every company with bills, so its bill total equals the
  tile. No total row when only one company is shown.
- **Customers list** counts customers with sales in the period (as the tile).
- **Compare options** (Show by, Add, Compare with) are not split by customer or
  district: with one picked, the chart stays the period chart and the options
  panel says so.
- **Charts.** Negative values draw as bars below the zero line. Only a month in
  progress is faded. Ashwin and Ashadh are abbreviated "Asoj" and "Asar". A y
  title longer than the axis is cut to its first words.
- **Ink.** Change and Net change are plain ink with a sign; red stays for
  negative balances.
- **Short-period tiles** are labelled "· opening <day>".
- **Expenses series** excludes Period Closing Vouchers.
- **Access.** `api._companies()` reads with `get_all` and applies Company User
  Permissions itself, so a user holding only a dashboard role gets the page.
  `credit_snapshot.refresh` is POST only.

Not done, known: no automated tests; a cold open can occupy all web workers;
cache keys lack the data-through day; `force` is open to every viewer; the slot
rule is written in three places; switched-off features are still in the script;
phone tables lose columns.

## Fiscal year picker speed (2026-11-13)

The year picker felt slower than the company picker: a company filters rows
already in the browser, a year needs the server. Now:

- `call()` keeps each loader's answer in the page for `MEMO_MS` (10 minutes),
  keyed by method and arguments; a year already seen is redrawn without a
  request. Refresh empties it.
- `warmPrev()` fetches the previous fiscal year in the background, one request
  at a time, a few seconds after the first draw.
- `FY_APPLY_DELAY` is 120 ms (was 600).

## Layout polish and phone layout (2026-11-13, asset version 86)

Checked in headless Chrome at 1500, 1000 and 390 px, light and dark: no console errors, no page-level sideways scroll.

- **Wider bars for a short year.** A chart with `FEW_BARS` (6) bars or fewer draws them up to 76 px wide (grouped: 38 px), so four months of data no longer look like thin sticks in an empty plot.
- **District card.** The list beside the map shows `DISTRICT_ROWS` (8) districts and the map is centred against it; the blank block under the map is gone.
- **X-axis title** drops its bracketed part when the chart is too narrow for it (same rule the y title already had).
- **Phone (760 px and under):**
  - The sixth top tile takes the full width instead of sitting alone beside a gap.
  - Bar lists put name and figure on one line and the bar full width under them (the bar had about 10 px before).
  - Small tiles use a 21 px figure so "Rs 80.59 Cr" is not cut.
  - Tables show only the columns that fit. Hidden on a phone: scorecard Share, Collected, Customers, Bills, 24 months and the cell bars; credit list Company, Advance, Oldest bill, Unpaid bills, Limit used, Usual; customers Company, Last bill; cash table Cash in hand and Bank. The credit list becomes one block per customer with the hold reason under the name. The columns are hidden by position (`nth-child`), so a column added to one of these tables needs the phone rules at the end of `ceo_dashboard.css` updated.
  - The scorecard has no › column on a phone (the By company card above it has the same drill), so no table scrolls sideways at 390 px. Checked in dark mode too (asset version 88).

## Pack sizes and expenses by head (2026-11-13, asset version 91)

Two cards added after looking at what the books hold that the page did not show. Stock was looked at and left out: the LP Gas bins on demo-nggroup are negative (about -97,000 MT at NGI), so a stock figure would be wrong.

- **LP Gas sold by pack size** (Sales, beside Billed and collected). LP Gas is one item billed in several units of measure (14.2 KG, 5 KG, 7.1 KG, 19 KG, 47.5 KG, 50 KG, 425 KG, 450 KG, 1 MT, Kg). The card shows cylinders sold, tonnes in bulk, and one bar per unit with its count, bills, MT or rupees and share. Net of returns.
  - Data: `sales_breakdowns.get_breakdowns` returns `packs` ([unit, kg in one unit]) and `pack_rows` (per day x company x unit x segment x inter-company x district). Payload `version: 2`, cache key `breakdowns:v3`. `pack_rows` is about 1.2 MB of JSON for three years.
  - Kg in one unit is read from the unit's name (`_pack_kg`), because some bill lines carry another unit's conversion factor.
  - A unit of up to `PACK_CYLINDER_MAX_KG` (50) kg counts as a cylinder; larger units and loose kg are "in bulk".
  - Follows period, company, inter-company, segment and district. With a customer picked it says pack sizes are not kept per customer (same as branch and returns).
  - Check: the pack rows for 83/84 add up to 6,382 MT, the same as the LP Gas volume tile.
- **Expenses by head** (Buying, above We owe suppliers). GL entries on Expense accounts, grouped by the parent account with its number and company suffix removed, so a head adds up across companies. Left: the `EXPENSE_HEADS_MAX` (8) largest heads, the rest as "Other heads". Right: expenses in the chart's buckets (month by month, or day by day for a week or month).
  - Data: `buying.get_buying` returns `expense_heads` and `expenses` (per day x company x head). Payload `version: 2`, cache key `buying:v2`. Period Closing Vouchers are left out.
  - Follows period and company. The inter-company switch does not apply.
  - A head whose total is negative (more credited back than booked; Raw Material Consumption on demo-nggroup, -Rs 1.62 Cr in 83/84) keeps its own row at the end with no share. Shares are of the heads above zero. The total at the top is the net figure as booked.
  - This is expenses as booked, not profit: the cost of the gas sold is not booked through these accounts.
- **Billed and collected** is now half width, beside the pack-size card.
- Both modules were already imported by the web workers, so the gunicorn master was sent HUP after the change.

## Outside review fixes (2026-11-14, asset version 97)

An independent review scored the page 6/10: figures with no reference point,
too long for daily use, no navigation on a phone, and a list of small defects.
The owner asked for all of it to be fixed except the outliers (a Rs 1,130 Cr
supplier balance still flattens its chart; the books are not touched or
flagged).

- **Last-year figure.** Each top tile (volume, net sales, purchases) carries
  one quiet line, "Same period 82/83 …" ("Same week …", "12 months before …");
  the balance tiles carry "A year earlier …". The scorecard shows the same
  under volume and net sales (hidden on a phone, where it does not fit). It
  is actual data, not a target, and has no change badge: `SHOW_COMPARISON`
  stays off. Blank when the window starts in the first year loaded
  (`hasCmp`), so a missing year never reads as zero.
- **Shorter page.** Sales and Buying open short; District, Returns, Branch,
  Pack sizes and What we buy, Suppliers, Expenses sit behind one "Show more"
  per section (`MORE_CARDS`, `renderMore`; remembered in this browser's
  localStorage). Default height 9,600 → 7,060 px at 1500 wide, 19,300 →
  13,600 px at 390. Print shows every card.
- **Phone section strip.** The filter bar is too tall to pin on a phone, so
  the section buttons are repeated in their own strip that stays under the
  navbar (`.ceo-phonenav`).
- **Two advance figures.** Not a bug: the top tile is ledger balances now
  (money.py), the Credit section is credit control's position (advances,
  credit notes and journal credits netted, from the 4-hourly snapshot). The
  Credit tiles are now "Owed (credit check)" and "Advance left (credit
  check)", so one name means one number.
- **Smaller fixes.** Week-view tile labels no longer cut off (opening date
  moved to the foot) and those tiles get their 24-month line; sparklines have
  a hover (span, highest, lowest, latest month); axis ticks get the decimals
  they need (no more "2 L, 2 L"); negative bars get a label in the month
  charts and a red bar in the pack-size and expense lists; "Customers" ×2 →
  "Customer dues" and "Top customers"; scorecard drops companies with nothing
  this period or last; Collected % header explains >100% on hover; gone quiet
  ranked by usual month (average of months bought in, last 12 months before
  the last bill); district names hidden on a phone; Rs/kg off in the company
  drawer; "Updated HH:MM" in the filter bar; bars and lines inside Buying,
  Money, Credit and Customers wear that section's colour; returns grey, not
  the status orange.
- **Not changed.** The volume and sales sparklines on demo-nggroup still drop
  at the end: the books there stop in Bhadra, so Asoj is a real zero. The
  month in progress was already left off.

## Glass look and compact layout (2026-11-14, asset version 99)

Asked for a frosted-glass ("drop glass") theme while keeping the page small.
A soft fixed wash of the five section colours sits behind the page
(`.ceo-host::before`); the filter bar, top tiles and section panels are
translucent and blur it; cards inside a panel are lighter glass with no blur
of their own, so scrolling stays smooth. Tooltips, the drawer and pop-ups keep
the opaque card colour so their text stays readable. Falls back to solid cards
where blur is unsupported or the viewer asks for reduced transparency; print is
plain white. Compact: tighter padding and gaps, smaller tile figures, and
shorter charts (timeAxis default 200–260 px, expenses 300). Default height at
1500 px went 7,060 → 6,216 px; at 390 px 13,600 → 12,340 px. All in the last
block of ceo_dashboard.css, so it can be removed in one go.

**Revised the same day (asset version 100).** The owner found the full glass
look did not read well, and research agreed (NN/g on glass and text contrast;
Few on decoration in dashboards). The colour wash and glass cards were
removed; frosted glass now sits only on the sticky filter bar and the phone
section strip, the two places content scrolls under. Every card, tile, chart
and table is solid again. The compact spacing and shorter charts stay.

## Colour by meaning (2026-11-14, asset version 101)

The five tinted section panels (mint, pink, sand, lilac, sky) are gone: five
competing hues that said which section you were in, not what a figure means
(an outside review flagged it). Surfaces are neutral, like Frappe's widgets,
and colour has fixed jobs: teal = the figure (any single series, every
section), amber = a second series beside it, red = a negative value (dark
mode pink-red #e45f93 so it stays apart from amber), grey = other / returns;
segments and the ageing / limit ramps unchanged. Section colour survives only
as the small key on the heading, the section strip and the tile label.
Validated with the dataviz validator in light and dark. CSS: the last block
of ceo_dashboard.css; JS bar fills now use var(--ceo-cur) / var(--ceo-negbar).

## Frosted chart marks, compact segments (2026-11-14, asset version 102)

- Chart bars are frosted: a see-through body with a solid cap at the end
  (timeAxis draws the cap as a second path, class `cap`; bar lists use
  `.ceo-barfill::after`). Text, axes and cards stay solid.
- Customer segment was a full-width card with a ring for three figures. It is
  now a third-width card beside Billed and collected: one share bar and one
  line per segment (name, customers, figure, share); per customer and the other
  measure are on hover. The ring (`segDonut`) is gone. Pack sizes is full width
  when shown. Default height at 1500 px: 6,216 → 5,921 px.

## Customer dropdown (2026-11-14, asset version 103)

The "Find customer" box in Top customers only filtered that table. It is now
a dropdown like the Company picker (`custPicker`): it lists this period's
buyers largest first (figure beside each), typing searches every customer by
name or code, at most 60 rows (`CUST_DD_MAX`). Picking one shows only that
customer across the page, the same as clicking their row; "All customers"
clears it.

## Map screen (2026-11-14, asset version 107)

The district map is no longer on the dashboard. "Map" in the section strip
opens it as a screen of its own (URL `v=map`, measure `mb=`), with
"← Dashboard" to go back; the section buttons also go back and scroll. A row
of buttons picks what each district shows (`MAP_BY`): LP Gas sold, Net
sales, Buying customers, Collected (period figures, following the period),
Owed (credit check) and Customers on hold (positions from the credit
snapshot; hidden for a past year, and while the snapshot loads the map shows
volume without losing the choice). The filter bar applies as everywhere;
clicking a district picks it. Districts come from the customer's district
(sales_breakdowns), so collections and credit are mapped by the customer,
not the bill. Beside the map: the ten largest districts. `renderDistrict`
became `renderMapScreen`; the "District" card left Show more.

### Microsoft look (asset version 108)

The page now follows Fluent 2 / Power BI: a light grey canvas (#f3f2f1)
with white cards on a soft shadow and an 8px radius, Segoe UI first in the
font stack (Windows machines get it; others keep the desk font). Brand blue
#0F6CBD is the figure, Power BI orange #E66C37 the second series, purple
#744EC2 the third segment; companies, compared lines and the blue map /
limit-use ramp were re-stepped and re-validated (light and dark). Each
section has an Office colour as a key only (Sales blue, Buying orange-red,
Money green, Credit purple, Customers teal) on its heading rule, section
button and top-tile edge. The first top tile is a solid blue card. Chosen
buttons are filled blue; table headers sit on a grey band. All of it is one
CSS block at the end of `ceo_dashboard.css` ("Microsoft look"); no JS change.

### Sky glass (asset version 110)

The solid Microsoft blue felt heavy, so a lighter layer sits on top of it
("sky glass" block at the end of `ceo_dashboard.css`). The page sits on a
pale sky gradient with two soft glows, navy in dark mode. Cards are frosted
white glass, 86% opaque, so figures still read as if on a solid card. The
first tile is light blue glass with navy figures. Chosen buttons are light
blue with blue text. Section rules and tile edges fade out instead of ending
in a hard band. Series blue #2F8FDF (light) was validated.

### Banner design (asset version 113)

"Still boring", so a bolder layer went on top of sky glass:
- A deep blue banner (navy to azure, two soft glows and a light streak)
  sits behind the page title, the filter bar and the top half of the top
  tiles. The filter bar and tiles float on it as white cards, in the
  hero-banner style of the Azure and Microsoft 365 admin pages. The banner is
  a background layer on `.page-container[data-page-route="ceo-dashboard"]`
  (`--band-h` 330px, or 470px on phones).
- Every top tile (`data-ico`, set in renderKpis) and every section heading
  has a white line-icon badge on a gradient in its section colour. The icons
  are inline SVG data URIs in the CSS.
- The first tile is a white card whose figure has a blue-to-cyan gradient.
- Bars, line areas and sparkline areas use vertical gradients. These are
  shared `<linearGradient>`s in `.ceo-defs`, created once in `mount()`;
  CSS fills with `url(#ceo-g-cur)` and similar. Bar-list fills fade from
  left to right.
- Tile figures count up from zero when the figure changes (`countUp`). This
  is skipped for reduced motion, and the final text is always the formatted
  figure.

### Gear on the trend chart (asset version 118)

"Show by" left the chart-options panel and became a drive-mode strip in the
trend chart's header, like the gear selector in an electric car: Quarterly ·
Monthly · Weekly · Daily. A thumb springs to the chosen notch. It moves by
click, by dragging the thumb, by mouse wheel (one notch per flick,
`GEAR_WHEEL_GAP`) or by arrow keys. Units as large as the period or larger
are dimmed. Half-year is gone from the units. Year to date stays the default
period.

With Year to date and no other year compared, the weekly and daily axes now
stop at "data through" instead of running to Ashadh. The title reads like the
period chart ("LP Gas sold · Week by week · 83/84"). The code is
`renderGear` / `setGear` / `stepGear` in the JS and the "gear" block in the
CSS.

### Period gear for the whole dashboard (asset version 119)

The Period dropdown is gone, and the fiscal year picker is the base. The
gear moved from the trend chart into the filter bar and now sets the period
for the whole dashboard: **Year · Quarterly · Monthly · Weekly · Daily**.
Every notch can always be chosen.

- **Down** opens the latest unit inside the one on screen: Year → latest
  quarter → its last month → that month's last week → that week's last day.
- **Up** opens the unit that contains the one on screen: day → its week →
  the month the week starts in → its quarter → Year.
- Jumping several notches goes one level at a time (`zoomTo`, `zoomDown`,
  `zoomUp`).
- Beside the gear, ‹ › step to the previous or next quarter, month, week or
  day (`stepPeriod`). The label between the arrows opens the list of quarters,
  months, weeks or days.

**Daily** is a new period (`st.period = "day"`, URL `p=day&pd=YYYY-MM-DD`).
It uses the week's machinery: `periods.get_days` for that one date, laid on
the week slot, compared with the same weekday 52 weeks earlier. The chart
shows the day's week with the other days dimmed. Clicking a day bar in a
month or week chart opens that day; clicking a month bar opens that month, as
before.

Also:
- The chart unit follows the period (the unit below it). "Show by" and the
  `cg` URL key are retired.
- "12 months" is no longer offered.

### A gear on each time chart (asset version 121)

This replaces the period gear of version 119, at the user's request ("make
it simple").

- **Top bar:** only the Fiscal year. The whole dashboard shows that year:
  `st.period` is always `ytd`, and the URL `p` key is ignored.
- **A gear on each of the four time charts:** LP Gas sold / Net sales, Billed
  and collected, Purchases, and Expenses (the chart inside "Expenses by
  head"). Each card has its own, held in `st.grain`, and each starts on
  Monthly.
  - **Year:** one bar per fiscal year of the timeline. The current year runs
    up to "data through" and is labelled so.
  - **Quarterly, Monthly, Weekly, Daily:** each quarter, month, week or day
    of the picked fiscal year, up to "data through".
- **Where the data comes from:** all four charts read `series.get_series`
  day rows and are bucketed in the browser, so switching is instant. The code
  is `GEAR_CHART`, `gearBuckets`, `gearValues`, `renderGearChart` and
  `gearInto`. The gear moves by click, drag, mouse wheel or arrow keys
  (`setGear(name, unit)`, `stepGear(name, dir)`).
- **With a customer or district picked:** the series rows are not split by
  those, so the sales and billed/collected charts fall back to the old
  period chart and their gear is hidden. Purchases and expenses keep their
  gears.
- **What's gone:** the chart funnel's "Add" and "Compare with" sections no
  longer apply to the trend chart, because the Year notch is the year
  comparison.

### Drill-down and pie on the gear charts (asset version 124)

- **Drill-down:** clicking a bar (or a pie slice, or its row in the pie list)
  opens that period one unit down. A year opens its quarters, a quarter its
  months, and a month or a week its days. Each card keeps its own path
  (`st.drill[name]`). A "‹ Back" button and clickable crumbs above the chart
  step back out. Moving the gear, or changing the fiscal year, starts again
  from the whole year. When a period is open, its gear lights the unit shown.
  The code is `gearDrill`, `gearBack`, `gearCtx` and `GEAR_CHILD`, and
  `gearBuckets` takes the opened range (it counts only those days, using
  `offs`).
- **Pie:** the chart funnel's Shape offers Bars, Line and Pie on the four
  gear charts. A pie is a donut per series, with one slice per period in time
  order. The series colour steps from light to full, so a pie never needs
  more than one hue. A list beside it names each slice with its figure and
  share. A pie has at most 12 slices (`PIE_MAX`); with more, the card asks
  for Year, Quarterly or Monthly, or for a period to be opened first.
  Billed and collected shows two donuts.

### Show more removed, plain scorecard (asset version 126)

- **Show more is gone, with every card that was behind it:** Sales and
  returns, Sales by branch, LP Gas sold by pack size, What we buy, Top
  suppliers, and Expenses by head. Their renderers (`renderReturns`,
  `renderBranch`, `renderPack`, the buying sub-cards, `renderMore`,
  `datedBuckets`) and the remembered Show more choice (`ceo-dashboard:more`)
  were removed. The server endpoints still return that data; the page no
  longer reads it.
- **The gear charts are now three:** sales, billed and collected, and
  purchases.
- **The Company scorecard is figures only.** The 24-month line column and the
  bars over Volume and Net sales were removed because the table looked
  cluttered. The small Collected % bar stays, since it is what flags a low
  rate in red.
