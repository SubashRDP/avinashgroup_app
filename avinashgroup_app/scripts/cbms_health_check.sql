-- CBMS health check: Sales Invoice <-> CBMS Bill <-> CBMS Bill Return.
--
-- One result set. Every row is a finding; an empty result means everything
-- below holds. Read-only — no writes, no locks beyond the read.
--
--   bench --site ng-group.raindropinc.com mariadb < cbms_health_check.sql
--
-- Columns: severity | check_name | company | fiscal_year | detail | cnt | sample
--
-- "In scope" always means what the submit hook and backfill.py mean by it:
-- the company's CBMS Config has enable_cbms = 1 AND the invoice's posting_date
-- is on or after enable_from_date. An invoice outside that window is SUPPOSED
-- to have no CBMS record, so counting it as missing would bury the real gaps.

WITH scoped AS (
    SELECT
        si.name,
        si.company,
        si.posting_date,
        si.is_return,
        si.grand_total,
        si.docstatus,
        cfg.enable_from_date,
        COALESCE(fy.name, '(no fiscal year)') AS fiscal_year
    FROM `tabSales Invoice` si
    JOIN `tabCBMS Config` cfg
      ON cfg.company = si.company
     AND cfg.enable_cbms = 1
     AND cfg.enable_from_date IS NOT NULL
     AND si.posting_date >= cfg.enable_from_date
    LEFT JOIN `tabFiscal Year` fy
      ON si.posting_date BETWEEN fy.year_start_date AND fy.year_end_date
    WHERE si.docstatus = 1
),

-- One row per invoice that has any CBMS record, with how many, so duplicates
-- and coverage come from the same pass.
bill_count AS (
    SELECT sales_invoice, COUNT(*) AS n FROM `tabCBMS Bill` GROUP BY sales_invoice
),
ret_count AS (
    SELECT sales_invoice, COUNT(*) AS n FROM `tabCBMS Bill Return` GROUP BY sales_invoice
)

-- 1. CONFIG ------------------------------------------------------------------
-- A future or missing enable_from_date silently blinds BOTH the submit hook and
-- backfill.py, so the repair tool reports success having found nothing.
SELECT 'CRITICAL' AS severity,
       'config: cutoff blocks everything' AS check_name,
       cfg.company,
       '-' AS fiscal_year,
       CONCAT('enable_from_date = ', COALESCE(CAST(cfg.enable_from_date AS CHAR), 'NOT SET'),
              CASE WHEN cfg.enable_from_date > CURDATE() THEN ' (in the FUTURE)' ELSE '' END) AS detail,
       1 AS cnt,
       '' AS sample
FROM `tabCBMS Config` cfg
WHERE cfg.enable_cbms = 1
  AND (cfg.enable_from_date IS NULL OR cfg.enable_from_date > CURDATE())

UNION ALL
SELECT 'INFO', 'config: CBMS disabled', cfg.company, '-',
       'enable_cbms = 0, nothing will ever sync', 1, ''
FROM `tabCBMS Config` cfg
WHERE cfg.enable_cbms = 0

UNION ALL
SELECT 'WARN', 'config: company has no CBMS Config', c.name, '-',
       'invoices exist but no config row', COUNT(si.name), ''
FROM `tabCompany` c
JOIN `tabSales Invoice` si ON si.company = c.name AND si.docstatus = 1
LEFT JOIN `tabCBMS Config` cfg ON cfg.company = c.name
WHERE cfg.name IS NULL
GROUP BY c.name

-- 2. COVERAGE ----------------------------------------------------------------
UNION ALL
SELECT 'CRITICAL', 'missing CBMS Bill', s.company, s.fiscal_year,
       'in-scope submitted invoice with no CBMS Bill',
       COUNT(*), LEFT(GROUP_CONCAT(s.name ORDER BY s.name SEPARATOR ', '), 200)
FROM scoped s
LEFT JOIN bill_count b ON b.sales_invoice = s.name
WHERE s.is_return = 0 AND b.n IS NULL
GROUP BY s.company, s.fiscal_year

UNION ALL
SELECT 'CRITICAL', 'missing CBMS Bill Return', s.company, s.fiscal_year,
       'in-scope submitted credit note with no CBMS Bill Return',
       COUNT(*), LEFT(GROUP_CONCAT(s.name ORDER BY s.name SEPARATOR ', '), 200)
FROM scoped s
LEFT JOIN ret_count r ON r.sales_invoice = s.name
WHERE s.is_return = 1 AND r.n IS NULL
GROUP BY s.company, s.fiscal_year

-- 3. DUPLICATES --------------------------------------------------------------
-- CBMS Bill has no autoname, so nothing at the DB level stops a second record
-- for one invoice — a retry that races the submit hook can file the bill twice.
UNION ALL
SELECT 'CRITICAL', 'duplicate CBMS Bill', si.company, '-',
       CONCAT(COUNT(*), ' invoice(s) with more than one CBMS Bill'),
       COUNT(*), LEFT(GROUP_CONCAT(b.sales_invoice ORDER BY b.sales_invoice SEPARATOR ', '), 200)
FROM bill_count b
JOIN `tabSales Invoice` si ON si.name = b.sales_invoice
WHERE b.n > 1
GROUP BY si.company

UNION ALL
SELECT 'CRITICAL', 'duplicate CBMS Bill Return', si.company, '-',
       CONCAT(COUNT(*), ' credit note(s) with more than one CBMS Bill Return'),
       COUNT(*), LEFT(GROUP_CONCAT(r.sales_invoice ORDER BY r.sales_invoice SEPARATOR ', '), 200)
FROM ret_count r
JOIN `tabSales Invoice` si ON si.name = r.sales_invoice
WHERE r.n > 1
GROUP BY si.company

-- 4. ORPHANS AND WRONG TYPE --------------------------------------------------
UNION ALL
SELECT 'CRITICAL', 'orphan CBMS Bill', b.company, COALESCE(b.fiscal_year, '-'),
       'CBMS Bill whose Sales Invoice no longer exists',
       COUNT(*), LEFT(GROUP_CONCAT(b.sales_invoice SEPARATOR ', '), 200)
FROM `tabCBMS Bill` b
LEFT JOIN `tabSales Invoice` si ON si.name = b.sales_invoice
WHERE si.name IS NULL
GROUP BY b.company, b.fiscal_year

UNION ALL
SELECT 'CRITICAL', 'orphan CBMS Bill Return', r.company, COALESCE(r.fiscal_year, '-'),
       'CBMS Bill Return whose Sales Invoice no longer exists',
       COUNT(*), LEFT(GROUP_CONCAT(r.sales_invoice SEPARATOR ', '), 200)
FROM `tabCBMS Bill Return` r
LEFT JOIN `tabSales Invoice` si ON si.name = r.sales_invoice
WHERE si.name IS NULL
GROUP BY r.company, r.fiscal_year

UNION ALL
-- Already filed with IRD, then the invoice was cancelled or reopened here.
SELECT 'CRITICAL', 'CBMS Bill on a cancelled/draft invoice', b.company,
       COALESCE(b.fiscal_year, '-'),
       CONCAT('sync_status = ', b.sync_status, ', docstatus = ', si.docstatus),
       COUNT(*), LEFT(GROUP_CONCAT(b.sales_invoice SEPARATOR ', '), 200)
FROM `tabCBMS Bill` b
JOIN `tabSales Invoice` si ON si.name = b.sales_invoice
WHERE si.docstatus <> 1
GROUP BY b.company, b.fiscal_year, b.sync_status, si.docstatus

UNION ALL
SELECT 'CRITICAL', 'CBMS Bill filed for a CREDIT NOTE', b.company,
       COALESCE(b.fiscal_year, '-'),
       'a return was filed as a bill — IRD has it as a sale',
       COUNT(*), LEFT(GROUP_CONCAT(b.sales_invoice SEPARATOR ', '), 200)
FROM `tabCBMS Bill` b
JOIN `tabSales Invoice` si ON si.name = b.sales_invoice
WHERE si.is_return = 1
GROUP BY b.company, b.fiscal_year

UNION ALL
SELECT 'CRITICAL', 'CBMS Bill Return filed for a SALE', r.company,
       COALESCE(r.fiscal_year, '-'),
       'a normal invoice was filed as a credit note',
       COUNT(*), LEFT(GROUP_CONCAT(r.sales_invoice SEPARATOR ', '), 200)
FROM `tabCBMS Bill Return` r
JOIN `tabSales Invoice` si ON si.name = r.sales_invoice
WHERE si.is_return = 0
GROUP BY r.company, r.fiscal_year

-- 5. WHAT IRD ACTUALLY HAS ---------------------------------------------------
-- sync_status records what the API said on the LAST attempt. Pending means the
-- record exists here and was never accepted there.
UNION ALL
SELECT CASE WHEN b.sync_status = 'Failed' THEN 'CRITICAL' ELSE 'WARN' END,
       CONCAT('CBMS Bill not synced (', b.sync_status, ')'),
       b.company, COALESCE(b.fiscal_year, '-'),
       CONCAT('max attempts ', MAX(b.attempt_count),
              ', last error: ', COALESCE(LEFT(MAX(b.sync_response), 60), 'none')),
       COUNT(*), LEFT(GROUP_CONCAT(b.sales_invoice SEPARATOR ', '), 200)
FROM `tabCBMS Bill` b
WHERE COALESCE(b.sync_status, 'Pending') <> 'Synced'
GROUP BY b.company, b.fiscal_year, b.sync_status

UNION ALL
SELECT CASE WHEN r.sync_status = 'Failed' THEN 'CRITICAL' ELSE 'WARN' END,
       CONCAT('CBMS Bill Return not synced (', r.sync_status, ')'),
       r.company, COALESCE(r.fiscal_year, '-'),
       CONCAT('max attempts ', MAX(r.attempt_count),
              ', last error: ', COALESCE(LEFT(MAX(r.sync_response), 60), 'none')),
       COUNT(*), LEFT(GROUP_CONCAT(r.sales_invoice SEPARATOR ', '), 200)
FROM `tabCBMS Bill Return` r
WHERE COALESCE(r.sync_status, 'Pending') <> 'Synced'
GROUP BY r.company, r.fiscal_year, r.sync_status

UNION ALL
-- is_synced is a separate column from sync_status; if they disagree, one of the
-- two lies to whatever reads it.
SELECT 'CRITICAL', 'is_synced disagrees with sync_status', b.company,
       COALESCE(b.fiscal_year, '-'),
       CONCAT('sync_status = ', COALESCE(b.sync_status, 'NULL'),
              ' but is_synced = ', COALESCE(b.is_synced, 0)),
       COUNT(*), LEFT(GROUP_CONCAT(b.sales_invoice SEPARATOR ', '), 200)
FROM `tabCBMS Bill` b
WHERE (b.sync_status = 'Synced') <> (COALESCE(b.is_synced, 0) = 1)
GROUP BY b.company, b.fiscal_year, b.sync_status, b.is_synced

-- 6. AMOUNTS -----------------------------------------------------------------
-- total_sales is |grand_total| - tax_exempted_sales, so the two must add back
-- up. Exports are excluded: there total_sales is the whole grand_total.
UNION ALL
SELECT 'CRITICAL', 'CBMS Bill amount does not match invoice', b.company,
       COALESCE(b.fiscal_year, '-'),
       CONCAT('total_sales + exempt <> |grand_total|, worst gap ',
              ROUND(MAX(ABS(b.total_sales + b.tax_exempted_sales - ABS(si.grand_total))), 2)),
       COUNT(*), LEFT(GROUP_CONCAT(b.sales_invoice SEPARATOR ', '), 200)
FROM `tabCBMS Bill` b
JOIN `tabSales Invoice` si ON si.name = b.sales_invoice
WHERE COALESCE(b.export_sales, 0) = 0
  AND ABS(b.total_sales + b.tax_exempted_sales - ABS(si.grand_total)) > 0.05
GROUP BY b.company, b.fiscal_year

UNION ALL
SELECT 'CRITICAL', 'CBMS Bill Return amount does not match credit note', r.company,
       COALESCE(r.fiscal_year, '-'),
       CONCAT('total_sales + exempt <> |grand_total|, worst gap ',
              ROUND(MAX(ABS(r.total_sales + r.tax_exempted_sales - ABS(si.grand_total))), 2)),
       COUNT(*), LEFT(GROUP_CONCAT(r.sales_invoice SEPARATOR ', '), 200)
FROM `tabCBMS Bill Return` r
JOIN `tabSales Invoice` si ON si.name = r.sales_invoice
WHERE COALESCE(r.export_sales, 0) = 0
  AND ABS(r.total_sales + r.tax_exempted_sales - ABS(si.grand_total)) > 0.05
GROUP BY r.company, r.fiscal_year

UNION ALL
-- VAT must be 13% of the taxable value. This is what catches the class of bug
-- where a blank custom_vat_apply_on defaulted to 'VAT 13%' on a zero-rated line.
SELECT 'WARN', 'VAT is not 13% of taxable value', b.company,
       COALESCE(b.fiscal_year, '-'),
       CONCAT('worst gap ', ROUND(MAX(ABS(b.vat - b.taxable_sales_vat * 0.13)), 2),
              ' on taxable ', ROUND(MAX(b.taxable_sales_vat), 2)),
       COUNT(*), LEFT(GROUP_CONCAT(b.sales_invoice SEPARATOR ', '), 200)
FROM `tabCBMS Bill` b
WHERE ABS(b.vat - b.taxable_sales_vat * 0.13) > 0.50
GROUP BY b.company, b.fiscal_year

UNION ALL
-- A bill IRD accepted for zero. Legal only if the invoice really is zero.
SELECT 'WARN', 'CBMS Bill filed with zero value', b.company,
       COALESCE(b.fiscal_year, '-'),
       'total_sales = 0', COUNT(*),
       LEFT(GROUP_CONCAT(b.sales_invoice SEPARATOR ', '), 200)
FROM `tabCBMS Bill` b
JOIN `tabSales Invoice` si ON si.name = b.sales_invoice
WHERE COALESCE(b.total_sales, 0) = 0 AND ABS(si.grand_total) > 0
GROUP BY b.company, b.fiscal_year

-- 7. REFERENTIAL -------------------------------------------------------------
UNION ALL
-- Every credit note points at an original. If that original never reached IRD,
-- the return references a bill IRD does not have.
SELECT 'CRITICAL', 'return against a bill IRD never received', si.company,
       COALESCE(r.fiscal_year, '-'),
       'return_against has no Synced CBMS Bill',
       COUNT(*), LEFT(GROUP_CONCAT(r.sales_invoice SEPARATOR ', '), 200)
FROM `tabCBMS Bill Return` r
JOIN `tabSales Invoice` si ON si.name = r.sales_invoice
LEFT JOIN `tabCBMS Bill` ob
       ON ob.sales_invoice = si.return_against AND ob.sync_status = 'Synced'
WHERE si.return_against IS NOT NULL AND si.return_against <> ''
  AND ob.name IS NULL
GROUP BY si.company, r.fiscal_year

UNION ALL
SELECT 'WARN', 'CBMS record has no fiscal year', b.company, '-',
       'fiscal_year is blank on the CBMS Bill', COUNT(*),
       LEFT(GROUP_CONCAT(b.sales_invoice SEPARATOR ', '), 200)
FROM `tabCBMS Bill` b
WHERE COALESCE(b.fiscal_year, '') = ''
GROUP BY b.company

UNION ALL
SELECT 'WARN', 'CBMS record has no seller PAN', b.company, '-',
       'seller_pan is blank — IRD rejects these', COUNT(*),
       LEFT(GROUP_CONCAT(b.sales_invoice SEPARATOR ', '), 200)
FROM `tabCBMS Bill` b
WHERE COALESCE(b.seller_pan, '') = ''
GROUP BY b.company

ORDER BY FIELD(severity, 'CRITICAL', 'WARN', 'INFO'), check_name, company, fiscal_year;
