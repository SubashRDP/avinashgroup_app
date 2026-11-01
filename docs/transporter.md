# Transporter list ("Name of Transportor" on PI / PR)

## What it is

"Name of Transportor" (`custom_name_of_transportor`) on Purchase Invoice and
Purchase Receipt is a **Link to the Transporter doctype**. It used to be a
Select with a fixed list of names.

The Transporter list holds:

1. **Suppliers ticked "Is Transporter"**, added automatically when the supplier
   is saved (`custom_code/transporter.py`, Supplier `on_update` in `hooks.py`).
2. **Transporters typed in by hand**, from the field's "+ Create a new
   Transporter" or the Transporter list. No supplier is needed.
3. **Every name the old Select offered or an old bill holds**, created once by
   the patch so old bills keep linking.

A Transporter's record ID is its name, so bills store the readable name. Reports
and the remarks line (`gas_purchase_report.py`, `gas_purchase_remarks.py`) read
the field as text and need no change.

## One-time setup: `patches/transporter_select_to_link.py`

Runs on migrate (post_model_sync):

- creates a Transporter for every old Select option, every value already in
  PI / PR, and every supplier already ticked "Is Transporter";
- sets the Custom Field to `Link` / `Transporter` directly, because Frappe
  refuses Select -> Link in Customize Form and Custom Field.

No bill is changed. Select and Link use the same varchar column.

## Gotchas

- **Unticking "Is Transporter" does not remove the Transporter.** Bills that use
  it must keep linking. To hide one from the dropdown, tick **Disabled** on it.
- **Misspelt duplicates** (e.g. "Shyam Loistics" in old Purchase Receipts):
  open that Transporter, rename it to the correct name and tick "Merge with
  existing". Frappe updates every bill that links to it.
- `custom/purchase_invoice.json` and `purchase_receipt.json` have
  `sync_on_migrate: 0`; the patch, not the JSON, changes the field on a site.
