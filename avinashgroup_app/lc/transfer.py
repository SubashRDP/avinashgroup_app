"""LC transfer — the goods arrived: move the LC's landed cost into stock and fixed assets.

Until the goods arrive every cost of the import sits in LC Goods in Transit
(lc/accounting.py). This is the step that empties it. The balance is spread
over the LC's goods rows (by value in the LC currency, or by quantity), and:

    rows to Stock         one Material Receipt Stock Entry, each row at its
                          landed rate; ERPNext posts Dr Stock / Cr the row's
                          Difference Account, which is set to Goods in Transit
    rows to Fixed Asset   one Journal Entry, Dr each Asset Category's Fixed
                          Asset account / Cr Goods in Transit, and a draft
                          Asset per row for the user to complete (location,
                          depreciation) and submit

Why the Asset is an "existing asset": ERPNext only lets an asset be bought
through a Purchase Receipt or Invoice (and its CWIP flow) unless it is marked
existing. Its value is already in the fixed asset account by the JE above, so
the Asset must not post again; an existing asset does not. This matches how
fixed_assets/ handles assets whose cost was booked elsewhere.

Boundary: it allocates and creates documents; History, totals and undo
bookkeeping are lifecycle.record_event's. It only runs once per LC: a cost
booked after the transfer stays in transit until Close clears it.

Landmine: Stock Entry basic_rate is per *stock* UOM, so a row bought in another
UOM is divided by its conversion factor; rounding of the rate can leave a few
paisa in transit, which Close clears.
"""

import frappe
from frappe import _
from frappe.utils import flt

from avinashgroup_app.lc import accounting


def allocate(lc, total):
	"""Each goods row's share of `total`, by value or quantity; the last row takes the rounding."""
	basis_field = "qty" if lc.allocate_by == "Quantity" else "amount"
	basis = [flt(i.get(basis_field)) for i in lc.items]
	whole = sum(basis)
	if whole <= 0:
		frappe.throw(_("The goods rows have no {0} to share the cost by.").format(
			_("quantity") if basis_field == "qty" else _("amount")))
	shares = [flt(total * b / whole, 2) for b in basis]
	if shares:
		biggest = max(range(len(shares)), key=lambda i: basis[i])
		shares[biggest] = flt(shares[biggest] + flt(total, 2) - sum(shares), 2)
	return shares


def _stock_uom_factor(item_code, uom):
	from erpnext.stock.get_item_details import get_conversion_factor

	stock_uom = frappe.get_cached_value("Item", item_code, "stock_uom")
	if not uom or uom == stock_uom:
		return stock_uom, 1.0
	factor = flt(get_conversion_factor(item_code, uom).get("conversion_factor"))
	if not factor:
		frappe.throw(_("Item {0} has no conversion from {1} to its stock unit {2}.").format(item_code, uom, stock_uom))
	return uom, factor


def check_rows(lc):
	"""Every goods row must say where it goes, with what it needs there. Returns problems as text."""
	problems = []
	for i in lc.items:
		label = _("Row {0}").format(i.idx)
		if not i.item_code:
			problems.append(_("{0}: choose the Item.").format(label))
			continue
		item = frappe.get_cached_value("Item", i.item_code, ["is_stock_item", "is_fixed_asset", "disabled"], as_dict=True)
		if item.disabled:
			problems.append(_("{0}: {1} is disabled.").format(label, i.item_code))
		if flt(i.qty) <= 0:
			problems.append(_("{0}: quantity must be more than zero.").format(label))
		if i.transfer_to == "Fixed Asset":
			if not item.is_fixed_asset:
				problems.append(_("{0}: {1} is not a fixed-asset item.").format(label, i.item_code))
			elif not i.asset_category:
				problems.append(_("{0}: choose the Asset Category.").format(label))
			elif not fixed_asset_account(i.asset_category, lc.company):
				problems.append(_("{0}: Asset Category {1} has no Fixed Asset account for {2}.").format(
					label, i.asset_category, lc.company))
		else:
			if not item.is_stock_item:
				problems.append(_("{0}: {1} is not a stock item.").format(label, i.item_code))
			warehouse = i.warehouse or lc.set_warehouse
			if not warehouse:
				problems.append(_("{0}: choose the Warehouse.").format(label))
			elif frappe.get_cached_value("Warehouse", warehouse, "company") != lc.company:
				problems.append(_("{0}: {1} is not a warehouse of {2}.").format(label, warehouse, lc.company))
	return problems


def fixed_asset_account(asset_category, company):
	return frappe.db.get_value("Asset Category Account",
		{"parent": asset_category, "company_name": company}, "fixed_asset_account")


def preview(lc):
	"""What the transfer would do, for the dialog: rows with their share, and any blockers."""
	balance = accounting.transit_balance(lc)
	problems = check_rows(lc)
	if not lc.arrival_date:
		problems.insert(0, _("Fill the Reach Date first."))
	if lc.transferred_on:
		problems.insert(0, _("Already transferred on {0}.").format(frappe.format(lc.transferred_on, "Date")))
	if flt(lc.goods_cost) <= 0:
		problems.insert(0, _("Book the goods payment (or the accepted bill) first: the goods are not in the cost yet."))
	if balance <= 0:
		problems.append(_("LC Goods in Transit holds nothing for this LC."))
	shares = allocate(lc, balance) if balance > 0 and lc.items else [0] * len(lc.items)
	rows = []
	for i, share in zip(lc.items, shares):
		rows.append({
			"idx": i.idx, "item_code": i.item_code, "description": i.description, "qty": i.qty, "uom": i.uom,
			"transfer_to": i.transfer_to, "target": i.warehouse or lc.set_warehouse if i.transfer_to == "Stock" else i.asset_category,
			"allocated_cost": share, "landed_rate": flt(share / flt(i.qty), 4) if flt(i.qty) else 0,
		})
	warnings = []
	if flt(lc.goods_pending_fc) > 0.005:
		warnings.append(_("{0} {1} of the LC is not paid or accepted yet. If it is paid later, Close clears it out of transit.").format(
			lc.currency, lc.goods_pending_fc))
	return {"balance": balance, "total_cost": flt(lc.total_cost), "rows": rows, "problems": problems, "warnings": warnings}


def make_stock_entry(lc, posting_date, rows):
	transit = accounting.get_company_accounts(lc.company).transit_account
	cc = accounting.cost_center(lc)
	se = frappe.new_doc("Stock Entry")
	se.update({
		"stock_entry_type": "Material Receipt",
		"purpose": "Material Receipt",
		"company": lc.company,
		"posting_date": posting_date,
		"set_posting_time": 1,
		"letter_of_credit": lc.name,
		"remarks": _("Goods of LC {0} ({1}) from {2}, at landed cost").format(lc.lc_no, lc.name, lc.supplier_name),
	})
	for item, share in rows:
		uom, factor = _stock_uom_factor(item.item_code, item.uom)
		transfer_qty = flt(item.qty) * factor
		se.append("items", {
			"item_code": item.item_code,
			"qty": item.qty,
			"uom": uom,
			"conversion_factor": factor,
			"transfer_qty": transfer_qty,
			"t_warehouse": item.warehouse or lc.set_warehouse,
			"basic_rate": flt(share) / transfer_qty,
			# ERPNext computes basic_amount only for rates it sets itself.
			"basic_amount": flt(share, 2),
			"set_basic_rate_manually": 1,
			"expense_account": transit,
			"cost_center": cc,
		})
	se.flags.ignore_permissions = True
	se.insert()
	se.submit()
	return se


def make_asset_entry(lc, posting_date, rows):
	"""One JE for every fixed-asset row: Dr the category's account / Cr Goods in Transit."""
	transit = accounting.get_company_accounts(lc.company).transit_account
	cc = accounting.cost_center(lc)
	entries = []
	for item, share in rows:
		entries.append(accounting._row(fixed_asset_account(item.asset_category, lc.company), share, "debit", cc))
	entries.append(accounting._row(transit, sum(flt(s) for _i, s in rows), "credit", cc))
	return accounting.make_journal_entry(lc, posting_date, entries, _("Goods capitalised as fixed assets"), bank_entry=False)


def make_asset(lc, posting_date, item, share):
	"""Draft Asset for one row, already valued; the user adds the location and depreciation."""
	asset = frappe.new_doc("Asset")
	asset.update({
		"company": lc.company,
		"item_code": item.item_code,
		"asset_name": item.item_name or item.description,
		"asset_category": item.asset_category,
		"asset_quantity": max(int(flt(item.qty)), 1),
		"is_existing_asset": 1,
		"purchase_date": posting_date,
		"available_for_use_date": posting_date,
		"gross_purchase_amount": flt(share, 2),
		"purchase_amount": flt(share, 2),
		"calculate_depreciation": 0,
		"cost_center": accounting.cost_center(lc),
		"letter_of_credit": lc.name,
	})
	asset.flags.ignore_permissions = True
	asset.flags.ignore_mandatory = True  # location is the user's to fill
	asset.insert()
	return asset.name


def transfer(lc, posting_date):
	"""Run the transfer and record it on the LC (called by lifecycle.transfer)."""
	from avinashgroup_app.lc import lifecycle

	p = preview(lc)
	if p["problems"]:
		frappe.throw("<br>".join(p["problems"]), title=_("Cannot transfer yet"))
	shares = [r["allocated_cost"] for r in p["rows"]]
	stock_rows = [(i, s) for i, s in zip(lc.items, shares) if i.transfer_to != "Fixed Asset"]
	asset_rows = [(i, s) for i, s in zip(lc.items, shares) if i.transfer_to == "Fixed Asset"]

	external, touched = [], []
	if stock_rows:
		se = make_stock_entry(lc, posting_date, stock_rows)
		external.append(["Stock Entry", se.name])
		landed = {d.idx: d for d in se.items}
		for n, (item, share) in enumerate(stock_rows, start=1):
			value = flt(landed[n].amount) if n in landed else share
			touched.append((item, {"allocated_cost": value, "landed_rate": flt(value / flt(item.qty), 4),
				"stock_entry": se.name, "warehouse": item.warehouse or lc.set_warehouse}))
	if asset_rows:
		je = make_asset_entry(lc, posting_date, asset_rows)
		external.append(["Journal Entry", je])
		for item, share in asset_rows:
			asset = make_asset(lc, posting_date, item, share)
			external.append(["Asset", asset])
			touched.append((item, {"allocated_cost": share, "landed_rate": flt(share / flt(item.qty), 4),
				"asset_journal_entry": je, "asset": asset}))

	lifecycle.record_event(lc, "Transferred", posting_date, {"transferred_on": posting_date},
		amount=p["balance"], touched=touched, external=external,
		remarks=", ".join(name for _dt, name in external))


def undo_document(doctype, name):
	"""Undo a document the transfer (or close) created: cancel it, or delete a draft Asset."""
	docstatus = frappe.db.get_value(doctype, name, "docstatus")
	if docstatus is None:
		return
	if doctype == "Asset":
		if docstatus == 1:
			frappe.throw(_("Asset {0} is already submitted. Cancel it first, then undo the transfer.").format(name))
		if docstatus == 0:
			frappe.delete_doc("Asset", name, ignore_permissions=True, force=True)
		return
	if doctype == "Journal Entry":
		accounting.cancel_journal_entry(name)
		return
	if docstatus == 1:
		frappe.flags[accounting.INTERNAL_CANCEL_FLAG] = True
		try:
			doc = frappe.get_doc(doctype, name)
			doc.flags.ignore_permissions = True
			doc.flags.ignore_links = True  # the LC's own rows still point at it
			doc.cancel()
		finally:
			frappe.flags[accounting.INTERNAL_CANCEL_FLAG] = False


@frappe.whitelist()
def transfer_preview(name):
	lc = frappe.get_doc("Letter of Credit", name)
	lc.check_permission("read")
	return preview(lc)
