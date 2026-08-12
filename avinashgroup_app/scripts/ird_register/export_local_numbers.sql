-- Read-only alternative: dump the local side, no staging table, no writes.
--   bench --site ng-group.raindropinc.com mariadb -B -e "$(cat export_local_numbers.sql)" > local_numbers.tsv
SET SQL_BIG_SELECTS = 1;
SELECT si.company, si.custom_branch_name, si.is_return, si.posting_date,
       ABS(si.grand_total) AS grand_total, si.docstatus,
       COALESCE(b.sync_status, r.sync_status, '') AS sync_status,
       COALESCE(b.is_synced,  r.is_synced,  '')   AS is_synced
FROM `tabSales Invoice` si
LEFT JOIN `tabCBMS Bill` b        ON b.sales_invoice = si.name
LEFT JOIN `tabCBMS Bill Return` r ON r.sales_invoice = si.name
WHERE si.docstatus = 1
  AND si.company IN ('Nepal Gas Udhyog Pvt. Ltd.',
                     'Nepal Gas Udhyog (Gandaki) Pvt. Ltd.',
                     'Nepal Gas Udhyog (Karnali) Pvt. Ltd.',
                     'Nepal Gas Udhyog (Narayani) Pvt. Ltd.')
  AND si.posting_date BETWEEN '2022-07-17' AND '2026-07-16';
