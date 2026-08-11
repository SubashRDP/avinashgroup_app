# Reconcile Sales Invoice against the records that are supposed to accompany
# it: CBMS Bill / CBMS Bill Return, Sales Invoice Print Count, Sales Invoice
# Print Log.
#
#   WHAT "MISSING" ACTUALLY MEANS HERE
#   The three companions are NOT created uniformly, so a raw count comparison
#   always looks alarming. Read the rules before reading the numbers:
#
#   CBMS Bill / CBMS Bill Return
#       Created in CBMS.sales_invoice_hooks.on_submit, but ONLY when the
#       company has an enabled CBMS Config AND
#       posting_date >= config.enable_from_date. Anything submitted while
#       enable_from_date sits in the future gets nothing, whatever its
#       posting date. CBMS.backfill obeys the same cutoff, so parking the
#       date also blinds the repair tool.
#
#   Print Count / Print Log
#       Created only by an ACTUAL print event -- the Print button, a PDF
#       download, or raw/server printing (SalesInvoice.print_count). Never on
#       submit. An invoice that was imported and never printed correctly has
#       no rows, and that is not a defect. Historical rows come from the
#       legacy register import, not from this path.
#
#   So the questions worth asking are the ones below: which gaps break a rule
#   rather than follow one, and which rows point at nothing.
#
# HOW TO RUN
#   bench --site ng-group.raindropinc.com console
#   >>> from avinashgroup_app.scripts import audit_sales_invoice_records as a
#   >>> a.run()
#
#   Or one section at a time:
#   >>> a.config(); a.summary(); a.cbms_gaps(); a.print_gaps(); a.orphans()
#
# Every statement is a SELECT. This script never writes.
#
# Imports sit inside the functions so the file also works via
# exec(open(...).read(), globals()) in the bench console, where globals and
# locals are separate namespaces.


def _table(rows, headers, aligns=None):
    """Print a list of tuples as a fixed-width table.

    MySQL SUM() comes back as Decimal, which renders as "2683.0"; whole
    numbers are shown as integers.
    """
    def cell(c):
        if c is None:
            return ""
        if isinstance(c, float) and c.is_integer():
            return str(int(c))
        try:
            if c == int(c) and not isinstance(c, (bool, str)):
                return str(int(c))
        except (TypeError, ValueError):
            pass
        return str(c)

    rows = [tuple(cell(c) for c in r) for r in rows]
    widths = [len(h) for h in headers]
    for r in rows:
        for i, c in enumerate(r):
            widths[i] = max(widths[i], len(c))
    aligns = aligns or ["<"] + [">"] * (len(headers) - 1)
    # printf has no "<": left-align is the "-" flag, right-align is no flag.
    line = "  ".join(
        "%%%s%ds" % ("-" if aligns[i] == "<" else "", widths[i])
        for i in range(len(headers))
    )
    print(line % tuple(headers))
    print("  ".join("-" * w for w in widths))
    for r in rows:
        print(line % r)


def config():
    """CBMS Config per company, and whether the cutoff is currently blocking.

    A enable_from_date in the future means in_cbms_scope() is False for every
    invoice, so neither on_submit nor backfill will create anything.
    """
    import frappe

    print("=" * 78)
    print("CBMS CONFIG")
    print("=" * 78)

    today = frappe.utils.today()
    rows = frappe.db.sql(
        """
        SELECT company, enable_cbms, enable_from_date
        FROM `tabCBMS Config`
        ORDER BY company
        """
    )

    out = []
    blocking = 0
    for company, enabled, from_date in rows:
        if not enabled:
            note = "disabled"
        elif not from_date:
            note = "NO CUTOFF SET -- nothing in scope"
            blocking += 1
        elif str(from_date) > today:
            note = "CUTOFF IN THE FUTURE -- blocks everything"
            blocking += 1
        else:
            note = "ok"
        out.append((company, enabled, from_date, note))

    _table(out, ["company", "enabled", "enable_from_date", "state"],
           ["<", ">", ">", "<"])

    companies = frappe.db.sql_list(
        "SELECT name FROM `tabCompany` ORDER BY name"
    )
    configured = {r[0] for r in rows}
    for c in companies:
        if c not in configured:
            print("no CBMS Config at all: %s" % c)

    print("")
    if blocking:
        print("%d compan%s cannot create CBMS records right now."
              % (blocking, "y" if blocking == 1 else "ies"))
    return out


def summary():
    """One row per company: invoices vs each companion record.

    'covered' columns count DISTINCT invoices that have at least one companion
    row, not companion rows -- a print event writes one Print Log row per
    sheet, so raw row counts overstate coverage.
    """
    import frappe

    print("")
    print("=" * 78)
    print("COVERAGE BY COMPANY (submitted invoices only)")
    print("=" * 78)

    rows = frappe.db.sql(
        """
        SELECT
            si.company,
            -- COUNT(DISTINCT si.name), not SUM: the Print Log join fans out
            -- one row per printed SHEET, and SUM would count an invoice once
            -- per sheet.
            COUNT(DISTINCT CASE WHEN si.is_return = 0
                                THEN si.name END)                AS bills,
            COUNT(DISTINCT CASE WHEN si.is_return = 1
                                THEN si.name END)                AS returns,
            COUNT(DISTINCT CASE WHEN si.is_return = 0
                                THEN cb.sales_invoice END)       AS cbms_bill,
            COUNT(DISTINCT CASE WHEN si.is_return = 1
                                THEN cr.sales_invoice END)       AS cbms_ret,
            COUNT(DISTINCT pc.sales_invoice)                     AS pcount,
            COUNT(DISTINCT pl.sales_invoice)                     AS plog
        FROM `tabSales Invoice` si
        LEFT JOIN `tabCBMS Bill` cb
               ON cb.sales_invoice = si.name
        LEFT JOIN `tabCBMS Bill Return` cr
               ON cr.sales_invoice = si.name
        LEFT JOIN `tabSales Invoice Print Count` pc
               ON pc.sales_invoice = si.name
        LEFT JOIN `tabSales Invoice Print Log` pl
               ON pl.sales_invoice = si.name
        WHERE si.docstatus = 1
        GROUP BY si.company
        ORDER BY si.company
        """
    )

    out = []
    for company, bills, rets, cbms, cret, pcount, plog in rows:
        out.append((
            company, bills, cbms, int(bills) - int(cbms),
            rets, cret, int(rets) - int(cret),
            pcount, plog,
        ))
    _table(
        out,
        ["company", "bills", "cbms", "gap",
         "returns", "cbmsret", "gap", "printcnt", "printlog"],
    )
    print("")
    print("printcnt/printlog have no 'gap' column on purpose -- an unprinted")
    print("invoice is supposed to have neither. See print_gaps().")
    return rows


def cbms_gaps(samples=5):
    """Submitted invoices in CBMS scope that have no CBMS record.

    'In scope' is the same test the hook and the backfill use, so anything
    listed here is a real gap that backfill would repair once the cutoff is
    correct. Invoices outside scope are counted separately -- they are
    excluded by design, not lost.
    """
    import frappe

    print("")
    print("=" * 78)
    print("CBMS GAPS")
    print("=" * 78)

    cfg = {
        c: d
        for c, d in frappe.db.sql(
            """
            SELECT company, enable_from_date FROM `tabCBMS Config`
            WHERE enable_cbms = 1 AND enable_from_date IS NOT NULL
            """
        )
    }
    if not cfg:
        print("no enabled CBMS Config with a cutoff -- nothing is in scope")
        return []

    out = []
    missing_names = []
    for company in sorted(cfg):
        cutoff = cfg[company]
        row = frappe.db.sql(
            """
            SELECT
                SUM(si.posting_date >= %(cutoff)s)               AS in_scope,
                SUM(si.posting_date <  %(cutoff)s)               AS out_scope,
                SUM(si.posting_date >= %(cutoff)s
                    AND si.is_return = 0
                    AND cb.sales_invoice IS NULL)                AS miss_bill,
                SUM(si.posting_date >= %(cutoff)s
                    AND si.is_return = 1
                    AND cr.sales_invoice IS NULL)                AS miss_ret
            FROM `tabSales Invoice` si
            LEFT JOIN `tabCBMS Bill` cb ON cb.sales_invoice = si.name
            LEFT JOIN `tabCBMS Bill Return` cr ON cr.sales_invoice = si.name
            WHERE si.docstatus = 1 AND si.company = %(company)s
            """,
            {"company": company, "cutoff": cutoff},
        )[0]
        in_scope, out_scope, miss_bill, miss_ret = [int(x or 0) for x in row]
        out.append((company, cutoff, in_scope, out_scope, miss_bill, miss_ret))

        if miss_bill or miss_ret:
            missing_names += frappe.db.sql(
                """
                SELECT si.name, si.posting_date, si.is_return
                FROM `tabSales Invoice` si
                LEFT JOIN `tabCBMS Bill` cb ON cb.sales_invoice = si.name
                LEFT JOIN `tabCBMS Bill Return` cr ON cr.sales_invoice = si.name
                WHERE si.docstatus = 1 AND si.company = %(company)s
                  AND si.posting_date >= %(cutoff)s
                  AND ((si.is_return = 0 AND cb.sales_invoice IS NULL)
                       OR (si.is_return = 1 AND cr.sales_invoice IS NULL))
                ORDER BY si.posting_date ASC
                LIMIT %(n)s
                """,
                {"company": company, "cutoff": cutoff, "n": samples},
            )

    _table(out, ["company", "cutoff", "in scope", "out of scope",
                 "missing bill", "missing return"])

    if missing_names:
        print("")
        print("samples:")
        for name, pdate, is_ret in missing_names:
            print("  %s  %s  %s"
                  % (name, pdate, "return" if is_ret else "bill"))
        print("")
        print("Repair: fix enable_from_date first if config() flagged it,")
        print("then  from avinashgroup_app.custom_code.CBMS import backfill")
        print("      backfill.preview()   # read-only")
        print("      backfill.run(commit=True)")
    else:
        print("")
        print("no in-scope invoice is missing its CBMS record")
    return out


def print_gaps():
    """Print Count and Print Log disagreeing with each other.

    A missing pair (no count, no log) means the invoice was never printed --
    expected, and only reported as a total. What is NOT expected is one
    without the other: a real print writes both, so a one-sided row means an
    interrupted print, a partial legacy import, or a deleted counterpart.
    """
    import frappe

    print("")
    print("=" * 78)
    print("PRINT COUNT vs PRINT LOG")
    print("=" * 78)

    rows = frappe.db.sql(
        """
        SELECT
            si.company,
            COUNT(*)                                            AS invoices,
            SUM(pc.sales_invoice IS NULL
                AND pl.sales_invoice IS NULL)                   AS never,
            SUM(pc.sales_invoice IS NOT NULL
                AND pl.sales_invoice IS NULL)                   AS count_only,
            SUM(pc.sales_invoice IS NULL
                AND pl.sales_invoice IS NOT NULL)               AS log_only
        FROM `tabSales Invoice` si
        LEFT JOIN `tabSales Invoice Print Count` pc
               ON pc.sales_invoice = si.name
        LEFT JOIN (SELECT DISTINCT sales_invoice
                   FROM `tabSales Invoice Print Log`) pl
               ON pl.sales_invoice = si.name
        WHERE si.docstatus = 1
        GROUP BY si.company
        ORDER BY si.company
        """
    )
    _table(rows, ["company", "invoices", "never printed",
                  "count, no log", "log, no count"])

    dupes = frappe.db.sql(
        """
        SELECT sales_invoice, COUNT(*) c
        FROM `tabSales Invoice Print Count`
        GROUP BY sales_invoice HAVING c > 1
        ORDER BY c DESC LIMIT 10
        """
    )
    print("")
    if dupes:
        print("DUPLICATE Print Count rows (should be one per invoice):")
        _table(dupes, ["sales_invoice", "rows"])
    else:
        print("Print Count is one row per invoice -- no duplicates")

    mismatch = frappe.db.sql(
        """
        SELECT pc.sales_invoice, pc.print_count, COUNT(pl.name) AS log_rows
        FROM `tabSales Invoice Print Count` pc
        JOIN `tabSales Invoice Print Log` pl
             ON pl.sales_invoice = pc.sales_invoice
        GROUP BY pc.sales_invoice, pc.print_count
        HAVING pc.print_count <> COUNT(pl.name)
        LIMIT 10
        """
    )
    print("")
    if mismatch:
        n = frappe.db.sql(
            """
            SELECT COUNT(*) FROM (
              SELECT pc.sales_invoice
              FROM `tabSales Invoice Print Count` pc
              JOIN `tabSales Invoice Print Log` pl
                   ON pl.sales_invoice = pc.sales_invoice
              GROUP BY pc.sales_invoice, pc.print_count
              HAVING pc.print_count <> COUNT(pl.name)
            ) x
            """
        )[0][0]
        print("%d invoices where print_count != number of Print Log rows"
              " (first 10):" % n)
        _table(mismatch, ["sales_invoice", "print_count", "log rows"])
        print("")
        print("Legacy-imported counters were written without a matching log")
        print("row per sheet, so a mismatch on pre-Frappe invoices is history,")
        print("not corruption. Check the posting dates before acting.")
    else:
        print("print_count agrees with the Print Log row count everywhere")
    return rows


def orphans():
    """Companion rows pointing at an invoice that is gone or not submitted.

    The mirror image of a missing record, and the one a delete-and-reimport
    leaves behind.
    """
    import frappe

    print("")
    print("=" * 78)
    print("ORPHANED / MISDIRECTED ROWS")
    print("=" * 78)

    checks = [
        ("CBMS Bill", "CBMS Bill"),
        ("CBMS Bill Return", "CBMS Bill Return"),
        ("Print Count", "Sales Invoice Print Count"),
        ("Print Log", "Sales Invoice Print Log"),
    ]

    out = []
    for label, doctype in checks:
        gone, cancelled, draft, blank = frappe.db.sql(
            """
            SELECT
                SUM(si.name IS NULL AND t.sales_invoice IS NOT NULL
                    AND t.sales_invoice != ''),
                SUM(si.docstatus = 2),
                SUM(si.docstatus = 0),
                SUM(t.sales_invoice IS NULL OR t.sales_invoice = '')
            FROM `tab{dt}` t
            LEFT JOIN `tabSales Invoice` si ON si.name = t.sales_invoice
            """.format(dt=doctype)
        )[0]
        out.append((label, int(gone or 0), int(cancelled or 0),
                    int(draft or 0), int(blank or 0)))

    _table(out, ["record", "invoice deleted", "invoice cancelled",
                 "invoice draft", "no link"])

    total = sum(sum(r[1:]) for r in out)
    print("")
    if total:
        print("%d rows do not point at a submitted Sales Invoice." % total)
        for label, doctype in checks:
            names = frappe.db.sql(
                """
                SELECT t.name, t.sales_invoice
                FROM `tab{dt}` t
                LEFT JOIN `tabSales Invoice` si ON si.name = t.sales_invoice
                WHERE si.name IS NULL
                LIMIT 5
                """.format(dt=doctype)
            )
            for row_name, si_name in names:
                print("  %-18s %-24s -> missing %s"
                      % (label, row_name, si_name))
    else:
        print("every companion row points at a submitted Sales Invoice")
    return out


def run():
    """Everything, in reading order."""
    config()
    summary()
    cbms_gaps()
    print_gaps()
    orphans()
    print("")
    print("=" * 78)
    print("AUDIT COMPLETE -- nothing was written")
    print("=" * 78)
