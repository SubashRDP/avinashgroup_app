-- Write the IRD register's verdict onto the CBMS records.
--
-- READ ird_reconcile.sql's output FIRST. This file changes data; it is meant to
-- be run once, deliberately, after the coverage report has shown that the join
-- resolves (report A: no_local_invoice ~ 0). Run it in one session:
--
--   bench --site ng-group.raindropinc.com mariadb < ird_filed.sql            -- loads the register
--   bench --site ng-group.raindropinc.com mariadb < ird_reconcile.sql        -- look at this
--   bench --site ng-group.raindropinc.com mariadb < ird_apply_sync_status.sql
--
-- What it sets, and why:
--   sync_status = 'Synced', is_synced = 1   the IRD has the bill; it must never be re-filed
--   last_attempt = the IRD's own entry time the only true record of when it was accepted
--   sync_response = a provenance note      so nobody later mistakes this for a live sync
--
-- The IRD's entry time is Nepal local time, which is what Frappe stores, so it
-- is assigned straight across with no conversion.
--
-- Straight SQL, not the ORM: no Version rows are written and no hooks fire.
-- That is deliberate for a 18k-row backfill of a status field, but it does mean
-- the change is invisible in each document's history — the sync_response note is
-- the only trace, so leave it in place.

SET SQL_BIG_SELECTS = 1;

-- ird_reconcile.sql builds this; repeated here so running the two out of order
-- fails on the register being absent rather than on a missing lookup table.
CREATE TABLE IF NOT EXISTS zz_ird_company (abbr varchar(8) PRIMARY KEY, company varchar(140));
INSERT IGNORE INTO zz_ird_company VALUES
  ('NGI', 'Nepal Gas Udhyog Pvt. Ltd.'),
  ('NGG', 'Nepal Gas Udhyog (Gandaki) Pvt. Ltd.'),
  ('NGK', 'Nepal Gas Udhyog (Karnali) Pvt. Ltd.'),
  ('NGN', 'Nepal Gas Udhyog (Narayani) Pvt. Ltd.');

-- The first filing is the true one. 640 credit notes were submitted twice (see
-- report F); without this the join would match two rows and pick one at random.
DROP TABLE IF EXISTS zz_ird_first;
CREATE TABLE zz_ird_first (
  abbr varchar(8), kind varchar(12), invoice_number varchar(64),
  first_synced_at datetime,
  PRIMARY KEY (abbr, kind, invoice_number)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
AS SELECT abbr, kind, invoice_number, MIN(synced_at) AS first_synced_at
   FROM zz_ird_filed GROUP BY abbr, kind, invoice_number;

START TRANSACTION;

-- 1. Bills the IRD holds -----------------------------------------------------
UPDATE `tabCBMS Bill` b
JOIN `tabSales Invoice` si ON si.name = b.sales_invoice
JOIN zz_ird_company c      ON c.company = si.company
JOIN zz_ird_first f        ON f.invoice_number = si.custom_branch_name
                          AND f.abbr = c.abbr
                          AND f.kind = 'Sales'
SET b.sync_status  = 'Synced',
    b.is_synced    = 1,
    b.last_attempt = f.first_synced_at,
    b.sync_response = CONCAT('confirmed present in the IRD register (2026-08-11 drop), filed ',
                             DATE_FORMAT(f.first_synced_at, '%Y-%m-%d %H:%i:%s')),
    b.modified      = NOW(),
    b.modified_by   = 'Administrator'
WHERE b.sync_status <> 'Synced' OR COALESCE(b.is_synced, 0) = 0;

SELECT ROW_COUNT() AS bills_marked_synced;

-- 2. Credit notes the IRD holds ---------------------------------------------
UPDATE `tabCBMS Bill Return` r
JOIN `tabSales Invoice` si ON si.name = r.sales_invoice
JOIN zz_ird_company c      ON c.company = si.company
JOIN zz_ird_first f        ON f.invoice_number = si.custom_branch_name
                          AND f.abbr = c.abbr
                          AND f.kind = 'SalesReturn'
SET r.sync_status  = 'Synced',
    r.is_synced    = 1,
    r.last_attempt = f.first_synced_at,
    r.sync_response = CONCAT('confirmed present in the IRD register (2026-08-11 drop), filed ',
                             DATE_FORMAT(f.first_synced_at, '%Y-%m-%d %H:%i:%s')),
    r.modified      = NOW(),
    r.modified_by   = 'Administrator'
WHERE r.sync_status <> 'Synced' OR COALESCE(r.is_synced, 0) = 0;

SELECT ROW_COUNT() AS returns_marked_synced;

COMMIT;
-- ROLLBACK;  -- if the counts above do not look like report B, run this instead

-- 3. The other direction -----------------------------------------------------
-- Bills we call Synced that are absent from the register. Left commented: read
-- report C first and decide per company-year, because "absent" means one of two
-- very different things — cancelled and never issued, or issued and never filed.
-- Clearing the flag makes them eligible for filing the moment CBMS is re-enabled,
-- which for an old fiscal year may not be what anyone wants.
--
-- UPDATE `tabCBMS Bill` b
-- JOIN `tabSales Invoice` si ON si.name = b.sales_invoice
-- JOIN zz_ird_company c      ON c.company = si.company
-- JOIN `tabFiscal Year` fy   ON si.posting_date BETWEEN fy.year_start_date AND fy.year_end_date
-- LEFT JOIN zz_ird_first f   ON f.invoice_number = si.custom_branch_name
--                           AND f.abbr = c.abbr AND f.kind = 'Sales'
-- SET b.sync_status = 'Pending', b.is_synced = 0,
--     b.sync_response = 'absent from the IRD register (2026-08-11 drop)',
--     b.modified = NOW(), b.modified_by = 'Administrator'
-- WHERE b.sync_status = 'Synced'
--   AND si.docstatus = 1
--   AND fy.name IN ('79/80', '80/81', '81/82', '82/83')
--   AND f.invoice_number IS NULL;

-- Clean up when finished:
--   DROP TABLE zz_ird_first; DROP TABLE zz_ird_filed; DROP TABLE zz_ird_company;
