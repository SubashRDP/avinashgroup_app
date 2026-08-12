-- Reconcile the local books against the IRD CBMS register (2026-08-11 drop).
--
--   bench --site ng-group.raindropinc.com mariadb < ird_filed.sql       -- once, loads the register
--   bench --site ng-group.raindropinc.com mariadb < ird_reconcile.sql   -- this file, read-only after that
--
-- Joins on custom_branch_name, which IS the number filed with the IRD
-- (utils.cbms_invoice_number returns it, and CBMS Bill.invoice_number is a copy).
-- Returns are joined on company too: RTN numbers repeat across companies.
--
-- Reports only. Nothing here writes to a Frappe table.

SET SQL_BIG_SELECTS = 1;
SET SESSION group_concat_max_len = 8192;

-- Company names as they appear on ng-group.
DROP TABLE IF EXISTS zz_ird_company;
CREATE TABLE zz_ird_company (abbr varchar(8) PRIMARY KEY, company varchar(140)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
INSERT INTO zz_ird_company VALUES
  ('NGI', 'Nepal Gas Udhyog Pvt. Ltd.'),
  ('NGG', 'Nepal Gas Udhyog (Gandaki) Pvt. Ltd.'),
  ('NGK', 'Nepal Gas Udhyog (Karnali) Pvt. Ltd.'),
  ('NGN', 'Nepal Gas Udhyog (Narayani) Pvt. Ltd.');

-- 1. HEADLINE ----------------------------------------------------------------
-- Every IRD record, by whether we can find the invoice it was filed for.
SELECT 'A. coverage' AS report, f.abbr, f.fy, f.kind,
       COUNT(*) AS ird_rows,
       SUM(si.name IS NOT NULL) AS matched_locally,
       SUM(si.name IS NULL)     AS no_local_invoice
FROM zz_ird_filed f
JOIN zz_ird_company c ON c.abbr = f.abbr
LEFT JOIN `tabSales Invoice` si
       ON si.custom_branch_name = f.invoice_number
      AND si.company = c.company
GROUP BY f.abbr, f.fy, f.kind
ORDER BY f.abbr, f.fy, f.kind;

-- 2. THE FIX LIST ------------------------------------------------------------
-- IRD HAS the bill; we say it is not synced. These are the rows a retry would
-- re-file, creating a duplicate at the IRD.
SELECT 'B. we say unsynced, IRD has it' AS report, f.abbr, f.fy,
       COALESCE(b.sync_status, 'no CBMS Bill') AS local_status,
       COUNT(*) AS cnt,
       LEFT(GROUP_CONCAT(f.invoice_number ORDER BY f.invoice_number SEPARATOR ', '), 200) AS sample
FROM zz_ird_filed f
JOIN zz_ird_company c ON c.abbr = f.abbr
JOIN `tabSales Invoice` si
       ON si.custom_branch_name = f.invoice_number
      AND si.company = c.company
LEFT JOIN `tabCBMS Bill` b ON b.sales_invoice = si.name
WHERE f.kind = 'Sales'
  AND (b.name IS NULL OR b.sync_status <> 'Synced' OR COALESCE(b.is_synced, 0) = 0)
GROUP BY f.abbr, f.fy, COALESCE(b.sync_status, 'no CBMS Bill')
ORDER BY cnt DESC;

-- 3. THE LIE LIST ------------------------------------------------------------
-- We say Synced; the IRD register has no such number. docstatus 2 is listed
-- separately because a cancelled invoice is a different story from a lost one.
SELECT 'C. we say Synced, IRD has not' AS report, si.company,
       COALESCE(fy.name, '(no fiscal year)') AS fiscal_year, si.docstatus,
       COUNT(*) AS cnt,
       LEFT(GROUP_CONCAT(si.custom_branch_name ORDER BY si.custom_branch_name SEPARATOR ', '), 200) AS sample
FROM `tabCBMS Bill` b
JOIN `tabSales Invoice` si ON si.name = b.sales_invoice
JOIN zz_ird_company c ON c.company = si.company
JOIN `tabFiscal Year` fy ON si.posting_date BETWEEN fy.year_start_date AND fy.year_end_date
LEFT JOIN zz_ird_filed f
       ON f.invoice_number = si.custom_branch_name AND f.abbr = c.abbr AND f.kind = 'Sales'
WHERE b.sync_status = 'Synced'
  AND fy.name IN ('79/80', '80/81', '81/82', '82/83')
  AND f.invoice_number IS NULL
GROUP BY si.company, fy.name, si.docstatus
ORDER BY cnt DESC;

-- 4. NEVER FILED -------------------------------------------------------------
-- Submitted invoice, inside the years the register covers, absent from it.
SELECT 'D. never reached IRD' AS report, si.company,
       COALESCE(fy.name, '(no fiscal year)') AS fiscal_year,
       COALESCE(b.sync_status, 'no CBMS Bill') AS local_status,
       COUNT(*) AS cnt, ROUND(SUM(ABS(si.grand_total)), 2) AS value,
       LEFT(GROUP_CONCAT(si.custom_branch_name ORDER BY si.custom_branch_name SEPARATOR ', '), 200) AS sample
FROM `tabSales Invoice` si
JOIN zz_ird_company c ON c.company = si.company
JOIN `tabFiscal Year` fy ON si.posting_date BETWEEN fy.year_start_date AND fy.year_end_date
LEFT JOIN `tabCBMS Bill` b ON b.sales_invoice = si.name
LEFT JOIN zz_ird_filed f
       ON f.invoice_number = si.custom_branch_name AND f.abbr = c.abbr
WHERE si.docstatus = 1
  AND si.is_return = 0
  AND fy.name IN ('79/80', '80/81', '81/82', '82/83')
  AND f.invoice_number IS NULL
GROUP BY si.company, fy.name, COALESCE(b.sync_status, 'no CBMS Bill')
ORDER BY cnt DESC;

-- 5. AMOUNT DIVERGENCE -------------------------------------------------------
-- What was filed vs what the books say. > 1 rupee only; the register rounds.
SELECT 'E. filed amount <> invoice' AS report, f.abbr, f.fy,
       COUNT(*) AS cnt,
       ROUND(MAX(ABS(f.total - ABS(si.grand_total))), 2) AS worst_gap,
       LEFT(GROUP_CONCAT(f.invoice_number ORDER BY ABS(f.total - ABS(si.grand_total)) DESC SEPARATOR ', '), 200) AS sample
FROM zz_ird_filed f
JOIN zz_ird_company c ON c.abbr = f.abbr
JOIN `tabSales Invoice` si
       ON si.custom_branch_name = f.invoice_number
      AND si.company = c.company
WHERE ABS(f.total - ABS(si.grand_total)) > 1.00
GROUP BY f.abbr, f.fy
ORDER BY worst_gap DESC;

-- 6. THE DOUBLE-FILED CREDIT NOTES -------------------------------------------
-- One local credit note, two IRD rows. Nothing to import; IRD-side correction.
SELECT 'F. filed twice at IRD' AS report, f.abbr, f.fy, f.invoice_number,
       COUNT(*) AS ird_rows, MAX(f.total) AS total, MAX(f.tax) AS vat,
       GROUP_CONCAT(f.synced_at ORDER BY f.synced_at SEPARATOR ' | ') AS filed_at
FROM zz_ird_filed f
WHERE f.kind = 'SalesReturn'
GROUP BY f.abbr, f.fy, f.invoice_number
HAVING COUNT(*) > 1
ORDER BY f.abbr, f.invoice_number;

-- Clean up when you are done:
--   DROP TABLE zz_ird_filed; DROP TABLE zz_ird_company;
