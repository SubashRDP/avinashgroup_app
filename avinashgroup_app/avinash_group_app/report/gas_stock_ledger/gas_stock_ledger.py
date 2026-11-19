# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

"""Gas Stock Ledger -- a voucher-wise stock ledger shaped for the LPG business.

Why ERPNext's own Stock Ledger is not enough for Nepal Gas (measured on avinas1,
2026-11-19):

* **One item, many units.** Each gas company keeps a single "LP Gas" item in Kg,
  buys it in 1 MT tanker loads and sells it as 14.2 / 7.1 / 5 / 19 / 47.5 / 50 /
  425 / 450 kg cylinders, 1 MT bulk and loose Kg. People read stock in MT and
  sales in cylinders; the stock ledger only speaks Kg. This report shows the
  quantity in MT, Kg or any UOM on the item (a balance of "14.2 KG" reads as
  that many domestic cylinders' worth), and how many cylinders of each size moved.
* **Where the gas came from.** Each tanker's Purchase Invoice names its
  refinery (custom_refinery). Detail shows it per load, the Refinery filter
  narrows to one, and the Refinery Summary view totals loads, quantity and cost
  per refinery.
* **Grouped like GL Posting Detail.** Group By decides what each block of the
  Detail view (and the printed Posting Detail) is headed by: the Item (every
  warehouse as one stock -- the default, because the warehouses are only an
  accounting split), each Warehouse, each Party, each Refinery, or each
  Movement type. Item and Warehouse blocks carry a running balance; the others
  total their own in/out and close on the stock's opening and closing.
* **Nepali dates.** Periods are picked as BS mitis (From/To Miti, synced to the
  AD dates in the desk); Miti leads every row, days and months are labelled in BS.
* **Two warehouses that never meet.** Purchases land in "Gas Purchase / Stock",
  sales leave "Gas Purchase / Stock (Sales)", and nothing ever transfers between
  them. Per warehouse, one only grows and the other is deeply negative. The
  company's gas is one pool, so the default view pools every warehouse of the
  company; "By Warehouse" stays available.
* **Every sale is booked at zero cost.** All 289,744 Sales Invoice SLEs carry
  valuation_rate 0 and stock_value_difference 0, so ERPNext shows no stock value
  and no cost of gas sold. This report values the pool itself at moving average:
  any SLE that carries a value (a purchase) is taken as booked; any SLE that
  carries none (a sale, a sales return) moves at the running average rate.
  Negative stock is carried at the current rate.

The running balance always covers every movement in the pool. The Voucher Type,
Customer, Supplier and Branch filters only choose which rows are *shown*, the
way ERPNext's Stock Ledger does, so the Balance column stays the true stock.

What this does NOT do: it never writes valuation back to the SLEs or the GL. The
zero-COGS posting is an accounting fix (repost with a proper valuation), owned by
the books, not by a report. It also takes booked Kg as the truth: a line booked
with the wrong conversion factor (GEPL "7.1 KG" = 7.0 kg) is flagged, not
corrected.

Landmine: SLE's only useful index is (item_code, warehouse, posting_datetime).
Filter on posting_date, or leave the warehouse out, and the opening scan goes
from ~1s to ~12s on NGI. Every query here names the warehouses and filters on
posting_datetime for that reason.
"""

import re
from collections import OrderedDict
from functools import lru_cache

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, getdate

from avinashgroup_app.custom_code.CBMS.utils import bs_date_str
from avinashgroup_app.utils.voucher_numbers import link as voucher_link
from avinashgroup_app.utils.voucher_numbers import target_fields

VIEW_DETAIL = "Detail"
VIEW_DAILY = "Daily Summary"
VIEW_MONTHLY = "Monthly Summary (BS)"
VIEW_STOCK_BOOK = "Stock Book (मौज्दात खाता)"
VIEW_REFINERY = "Refinery Summary"

# Display units every Kg item offers, -> kg in one unit. The item's own UOMs
# ("14.2 KG", "425 KG", ...) are added per item by _units().
UNIT_FACTORS = {"MT": 1000.0, "Kg": 1.0}
UNIT_PRECISION = {"MT": 3, "Kg": 2}
# any other unit (a cylinder size, a non-weight UOM)
OTHER_PRECISION = 2

# The "1 MT" UOM is the MT unit under another name; offering both is noise.
UNIT_ALIASES = {"1 MT": "MT"}

# Shown for a purchase whose invoice names no refinery.
NO_REFINERY = "(Not recorded)"

# Group By: what each block of the Detail view and the print is headed by.
GROUP_ITEM = "Item"
GROUP_WAREHOUSE = "Warehouse"
GROUP_PARTY = "Party"
GROUP_REFINERY = "Refinery"
GROUP_MOVEMENT = "Movement"
GROUPS = (GROUP_ITEM, GROUP_WAREHOUSE, GROUP_PARTY, GROUP_REFINERY, GROUP_MOVEMENT)
# Item and Warehouse blocks are stock pools with a balance of their own; a party,
# a refinery or a movement type has no stock, only what moved through it.
RUNNING_GROUPS = (GROUP_ITEM, GROUP_WAREHOUSE)

# Every gas company's single stock item is named this on avinas1 (NGI-ITEM-00167,
# NGG-ITEM-00152, NGK-ITEM-00008, NGN-ITEM-00150, GEPL-ITEM-00066).
GAS_ITEM_NAME = "LP Gas"

# The domestic cylinder; "14.2-kg equivalent" is how the trade compares volumes.
DOMESTIC_CYLINDER_KG = 14.2

# A UOM at or above this many kg is bulk (the "1 MT" UOM), counted in MT not pieces.
BULK_MIN_KG = 1000.0

# Cylinder UOMs are named after their weight: "14.2 KG", "1 MT".
NOMINAL_RE = re.compile(r"([\d.]+)\s*(KG|MT)\b", re.IGNORECASE)

EPS = 1e-6

# How each voucher type's header names the things a gas clerk looks for. Fields
# missing on a site are skipped (checked against meta), never assumed.
HEADER_FIELDS = {
	"Sales Invoice": {
		"party": "customer_name",
		"party_id": "customer",
		"branch": "custom_branch",
		"vehicle": "custom_vehicle_no",
	},
	"Delivery Note": {
		"party": "customer_name",
		"party_id": "customer",
		"branch": "custom_branch",
		"vehicle": "vehicle_no",
	},
	"Purchase Invoice": {
		"party": "supplier_name",
		"party_id": "supplier",
		"branch": "custom_branch",
		"vehicle": "custom_vehicle_no",
		"pdo": "custom_pdo_no",
		"challan": "custom_ioc_challan_no",
		"refinery": "custom_refinery",
		"transporter": "custom_name_of_transportor",
	},
	"Purchase Receipt": {
		"party": "supplier_name",
		"party_id": "supplier",
		"branch": "custom_branch",
		"vehicle": "custom_vehicle_no",
		"pdo": "custom_pdo_no",
		"challan": "custom_ioc_challan_no",
		"refinery": "custom_refinery",
		"transporter": "custom_name_of_transportor",
	},
	"Stock Entry": {"party": "stock_entry_type"},
	"Stock Reconciliation": {"party": "purpose"},
}

ITEM_TABLES = {
	"Sales Invoice": "Sales Invoice Item",
	"Delivery Note": "Delivery Note Item",
	"Purchase Invoice": "Purchase Invoice Item",
	"Purchase Receipt": "Purchase Receipt Item",
	"Stock Entry": "Stock Entry Detail",
}

# Movement category -> (English, Nepali). Order is the column order in summaries.
CATEGORIES = OrderedDict(
	[
		("purchase", ("Purchase", "खरिद")),
		("purchase_return", ("Purchase Return", "खरिद फिर्ता")),
		("sale", ("Sale", "बिक्री")),
		("sale_return", ("Sale Return", "बिक्री फिर्ता")),
		("other", ("Transfer / Adjustment", "समायोजन")),
	]
)
INWARD = {"purchase", "sale_return"}


def execute(filters=None):
	filters = frappe._dict(filters or {})
	ctx = _context(filters)

	sections = _build_sections(ctx)
	_enrich(ctx, sections)

	view = ctx.view
	if view == VIEW_DAILY:
		columns, data = _summary_view(ctx, sections, by="day")
	elif view == VIEW_MONTHLY:
		columns, data = _summary_view(ctx, sections, by="month")
	elif view == VIEW_STOCK_BOOK:
		columns, data = _stock_book_view(ctx, sections)
	elif view == VIEW_REFINERY:
		columns, data = _refinery_view(ctx, sections)
	else:
		columns, data = _detail_view(ctx, sections)

	return columns, data, _message(ctx, sections), _chart(ctx, sections), _cards(ctx, sections)


# ---------------------------------------------------------------- context


def _context(filters):
	"""Validate filters and resolve everything the queries need.

	Raises if company/item/dates are missing or the user cannot see the company.
	"""
	# A caller that sends only BS mitis (the API, a saved report from the desk
	# whose AD dates were cleared) still gets its period.
	for ad_field, miti_field in (("from_date", "from_miti"), ("to_date", "to_miti")):
		if not filters.get(ad_field) and filters.get(miti_field):
			filters[ad_field] = _miti_to_ad(filters[miti_field])

	for field in ("company", "item_code", "from_date", "to_date"):
		if not filters.get(field):
			frappe.throw(_("{0} is required").format(frappe.unscrub(field)))

	company = filters.company
	if company not in frappe.get_list("Company", pluck="name"):
		frappe.throw(_("You are not permitted to see stock of {0}").format(company))

	from_date, to_date = getdate(filters.from_date), getdate(filters.to_date)
	if from_date > to_date:
		frappe.throw(_("From Date must be before To Date"))

	item = frappe.db.get_value(
		"Item", filters.item_code, ["name", "item_name", "stock_uom"], as_dict=True
	)
	if not item:
		frappe.throw(_("Item {0} not found").format(filters.item_code))

	warehouses = _as_list(filters.get("warehouse"))
	company_warehouses = frappe.get_all(
		"Warehouse", filters={"company": company, "is_group": 0}, pluck="name"
	)
	warehouses = [w for w in warehouses if w in company_warehouses] or company_warehouses
	if not warehouses:
		frappe.throw(_("{0} has no warehouses").format(company))

	weight_item = _is_weight(item.stock_uom)
	units = OrderedDict(_units(item.name, item.stock_uom))
	unit = UNIT_ALIASES.get(filters.get("unit"), filters.get("unit"))
	if unit not in units:
		unit = "MT" if weight_item else item.stock_uom

	group_by = filters.get("group_by")
	if group_by not in GROUPS:
		# saved reports from before Group By carried the Warehouses switch
		group_by = GROUP_WAREHOUSE if filters.get("warehouse_mode") == "By Warehouse" else GROUP_ITEM

	return frappe._dict(
		filters=filters,
		company=company,
		from_date=from_date,
		to_date=to_date,
		item=item,
		warehouses=warehouses,
		group_by=group_by,
		by_warehouse=group_by == GROUP_WAREHOUSE,
		view=filters.get("view") or VIEW_DETAIL,
		unit=unit,
		weight_item=weight_item,
		factor=units[unit],
		precision=UNIT_PRECISION.get(unit, OTHER_PRECISION),
		show_value=cint(filters.get("show_value", 1)),
		show_cylinders=cint(filters.get("show_cylinders", 1)),
		category_filter=_category_key(filters.get("voucher_category")),
		customer=filters.get("customer"),
		supplier=filters.get("supplier"),
		branch=filters.get("branch"),
		refinery=filters.get("refinery"),
	)


def _is_weight(uom):
	return (uom or "").lower() in ("kg", "kgs", "kilogram")


def _units(item_code, stock_uom):
	"""[(unit, stock-UOM qty in one unit)] the item's quantity can be shown in.

	A Kg item offers MT and Kg, then each of its own UOMs by size ("5 KG" ...
	"450 KG"). Another item offers its stock UOM and its UOMs. The item's own
	conversion factor is used, so a mis-set one ("7.1 KG" = 7 on GEPL) shows
	the item's view of that unit -- the same factor every invoice line used.
	"""
	units = OrderedDict()
	if _is_weight(stock_uom):
		units.update(UNIT_FACTORS)
	else:
		units[stock_uom] = 1.0
	for uom, factor in frappe.get_all(
		"UOM Conversion Detail",
		filters={"parent": item_code, "parenttype": "Item"},
		fields=["uom", "conversion_factor"],
		order_by="conversion_factor",
		as_list=True,
	):
		uom = UNIT_ALIASES.get(uom, uom) if _is_weight(stock_uom) else uom
		if uom not in units and flt(factor) > 0:
			units[uom] = flt(factor)
	return list(units.items())


def _miti_to_ad(miti):
	from avinashgroup_app.utils.bs_miti import miti_to_ad

	try:
		return miti_to_ad(miti)
	except Exception:
		frappe.throw(_("{0} is not a valid Miti (use YYYY-MM-DD in BS)").format(miti))


def _as_list(value):
	if not value:
		return []
	if isinstance(value, str):
		value = value.strip()
		if value.startswith("["):
			return [v for v in frappe.parse_json(value) if v]
		return [value]
	return [v for v in value if v]


def _category_key(label):
	for key, (english, _nepali) in CATEGORIES.items():
		if label == english:
			return key
	return None


# ------------------------------------------------------------- valuation


class _Pool:
	"""Running quantity, value and moving-average rate of one stock pool.

	Quantities are kg (stock UOM). A movement brings its own value only when
	ERPNext booked one (stock_value_difference != 0 -- purchases). Everything
	else moves at the current rate, which is what fixes the zero-cost sales.
	"""

	__slots__ = ("qty", "value", "rate", "by_warehouse")

	def __init__(self):
		self.qty = self.value = self.rate = 0.0
		self.by_warehouse = {}

	def normalise(self, sle):
		"""(qty, booked_qty, booked_value) one SLE moves, in kg.

		A Stock Reconciliation SLE without batches carries actual_qty 0 and *sets*
		the warehouse to qty_after_transaction (erpnext stock_reconciliation.py,
		the `"actual_qty": 0` row), so its movement is the difference from what
		that warehouse held. A count-up arrives at the reconciliation's own rate;
		a count-down leaves at the running average like any issue.
		"""
		held = self.by_warehouse.get(sle.warehouse, 0.0)
		qty, value = flt(sle.actual_qty), flt(sle.stock_value_difference)
		if sle.voucher_type == "Stock Reconciliation" and abs(qty) < EPS:
			qty = flt(sle.qty_after_transaction) - held
			value = qty * flt(sle.valuation_rate) if qty > 0 else 0.0
		self.by_warehouse[sle.warehouse] = held + qty
		if abs(value) > EPS:
			return qty, qty, value
		return qty, 0.0, 0.0

	def apply(self, qty, booked_qty, booked_value):
		"""Move `qty` kg, of which `booked_qty` arrives with `booked_value`.

		Returns the value of the movement (negative for an issue).
		"""
		moved = 0.0
		if abs(booked_qty) > EPS or abs(booked_value) > EPS:
			if booked_qty > EPS:
				# a receipt re-averages; into empty or negative stock it sets the rate
				if self.qty > EPS:
					self.rate = (self.value + booked_value) / (self.qty + booked_qty)
				else:
					self.rate = booked_value / booked_qty
			self.qty += booked_qty
			self.value += booked_value
			moved += booked_value

		rest = qty - booked_qty
		if abs(rest) > EPS:
			value = rest * self.rate
			self.qty += rest
			self.value += value
			moved += value

		if self.qty <= EPS:
			# negative or empty stock is carried at the current rate
			self.value = self.qty * self.rate
		return moved


# ------------------------------------------------------------- movements


def _sle_conditions(ctx):
	return {
		"item_code": ctx.item.name,
		"warehouses": tuple(ctx.warehouses),
		"start": "{} 00:00:00".format(ctx.from_date),
		"end": "{} 00:00:00".format(add_days(ctx.to_date, 1)),
	}


def _build_sections(ctx):
	"""Opening pool per section, then the period's movements in posting order.

	A section is the whole company pool, or one warehouse in By Warehouse mode.
	A movement is one voucher (per warehouse in By Warehouse mode): an invoice
	with a 14.2 KG and a 7.1 KG line is one row, and a transfer between two
	pooled warehouses nets to nothing and is dropped.
	"""
	params = _sle_conditions(ctx)
	section_of = (lambda wh: wh) if ctx.by_warehouse else (lambda wh: "")

	pools = {}
	# Opening: replay every earlier SLE, not just a SUM -- the moving average
	# depends on the order in which receipts and issues happened.
	# Sorted here, not in SQL: with several warehouses the index cannot hand
	# rows back in posting order, and the filesort took 7.5s of a 0.6s query
	# on NGI (97,710 rows before 82/83).
	earlier = frappe.db.sql(
		"""
		SELECT posting_datetime, creation, warehouse, voucher_type, actual_qty,
			stock_value_difference, qty_after_transaction, valuation_rate
		FROM `tabStock Ledger Entry`
		WHERE item_code = %(item_code)s AND warehouse IN %(warehouses)s
			AND posting_datetime < %(start)s AND is_cancelled = 0
		""",
		params,
		as_dict=True,
	)
	earlier.sort(key=lambda sle: (sle.posting_datetime, sle.creation))
	for sle in earlier:
		pool = pools.setdefault(section_of(sle.warehouse), _Pool())
		pool.apply(*pool.normalise(sle))

	sections = OrderedDict()
	keys = [section_of(w) for w in ctx.warehouses] if ctx.by_warehouse else [""]
	for key in keys:
		pool = pools.get(key) or _Pool()
		sections[key] = frappe._dict(
			key=key,
			opening=frappe._dict(qty=pool.qty, value=pool.value, rate=pool.rate),
			pool=pool,
			movements=OrderedDict(),
			had_cost_before=pool.rate > EPS,
		)

	for sle in frappe.db.sql(
		"""
		SELECT posting_date, posting_datetime, warehouse, voucher_type, voucher_no,
			voucher_detail_no, actual_qty, stock_value_difference,
			qty_after_transaction, valuation_rate
		FROM `tabStock Ledger Entry`
		WHERE item_code = %(item_code)s AND warehouse IN %(warehouses)s
			AND posting_datetime >= %(start)s AND posting_datetime < %(end)s
			AND is_cancelled = 0
		ORDER BY posting_datetime, creation
		""",
		params,
		as_dict=True,
	):
		section = sections[section_of(sle.warehouse)]
		key = (sle.voucher_type, sle.voucher_no)
		move = section.movements.get(key)
		if not move:
			move = section.movements[key] = frappe._dict(
				posting_date=sle.posting_date,
				voucher_type=sle.voucher_type,
				voucher_no=sle.voucher_no,
				warehouse=sle.warehouse,
				qty=0.0,
				booked_qty=0.0,
				booked_value=0.0,
				stored_zero=0,
				detail_nos=[],
			)
		qty, booked_qty, booked_value = section.pool.normalise(sle)
		move.qty += qty
		move.booked_qty += booked_qty
		move.booked_value += booked_value
		if qty < 0 and not booked_qty:
			move.stored_zero += 1
		if sle.voucher_detail_no:
			move.detail_nos.append(sle.voucher_detail_no)

	# Value each movement in order and drop the ones that net to nothing.
	for section in sections.values():
		kept = []
		for move in section.movements.values():
			if abs(move.qty) < EPS and abs(move.booked_value) < 0.005:
				continue
			move.value = section.pool.apply(move.qty, move.booked_qty, move.booked_value)
			move.balance_qty = section.pool.qty
			move.balance_value = section.pool.value
			move.rate = section.pool.rate
			move.category = _categorise(move.voucher_type, move.qty)
			kept.append(move)
		section.movements = kept
		section.closing = frappe._dict(
			qty=section.pool.qty, value=section.pool.value, rate=section.pool.rate
		)
	if ctx.by_warehouse:
		# a warehouse that never held this item is noise, not a zero balance
		for key in [k for k, s in sections.items() if not s.movements and abs(s.opening.qty) < EPS]:
			del sections[key]
	return sections


def _categorise(voucher_type, qty):
	if voucher_type in ("Purchase Invoice", "Purchase Receipt"):
		return "purchase" if qty > 0 else "purchase_return"
	if voucher_type in ("Sales Invoice", "Delivery Note"):
		return "sale" if qty < 0 else "sale_return"
	return "other"


# ------------------------------------------------------------ enrichment


def _enrich(ctx, sections):
	"""Attach party, numbers, tanker details and cylinder counts; mark visibility."""
	moves = [m for s in sections.values() for m in s.movements]
	# Summaries need party/branch only to apply those filters; skipping the
	# header join saves ~4s on a year of NGI invoices.
	needs_headers = (
		ctx.view in (VIEW_DETAIL, VIEW_STOCK_BOOK, VIEW_REFINERY)
		or ctx.customer
		or ctx.supplier
		or ctx.branch
		or ctx.refinery
	)
	headers = _headers(ctx, moves) if needs_headers else {}
	lines = _item_lines(ctx, moves) if ctx.show_cylinders or ctx.view == VIEW_DETAIL else {}
	ctx.sizes = {}
	ctx.factor_mismatch = {}

	for move in moves:
		head = headers.get((move.voucher_type, move.voucher_no), {})
		move.party = head.get("party") or ""
		move.party_id = head.get("party_id")
		move.branch = head.get("branch")
		move.vehicle = head.get("vehicle") or ""
		move.refinery = head.get("refinery") or ""
		move.number = head.get("number") or move.voucher_no
		move.reference = " · ".join(
			"{}: {}".format(label, head[field])
			for field, label in (
				("pdo", "PDO"),
				("challan", "Challan"),
				("transporter", "Transporter"),
			)
			if head.get(field)
		)
		move.cylinders = {}
		move.remarks = []
		for line in (lines.get(name) for name in move.detail_nos):
			if line:
				_count_cylinders(ctx, move, line)
		move.visible = _visible(ctx, move)


def _joined(ctx, voucher_type, table, on, fields):
	"""Rows of `table` joined from this run's SLEs of one voucher type.

	A join from the SLE index range beats `name IN (...)` lists of tens of
	thousands of names, which measured 12s for NGI's year of invoice lines.
	"""
	params = _sle_conditions(ctx)
	params["voucher_type"] = voucher_type
	return frappe.db.sql(
		"""
		SELECT DISTINCT t.name, {fields}
		FROM `tabStock Ledger Entry` sle
		JOIN `tab{table}` t ON t.name = sle.{on}
		WHERE sle.item_code = %(item_code)s AND sle.warehouse IN %(warehouses)s
			AND sle.posting_datetime >= %(start)s AND sle.posting_datetime < %(end)s
			AND sle.is_cancelled = 0 AND sle.voucher_type = %(voucher_type)s
		""".format(fields=fields, table=table, on=on),
		params,
		as_dict=True,
	)


def _headers(ctx, moves):
	"""{(voucher_type, name): {party, party_id, branch, vehicle, number, ...}}."""
	numbers = target_fields()
	out = {}
	for voucher_type in {m.voucher_type for m in moves}:
		meta = frappe.get_meta(voucher_type)
		mapping = {
			alias: field
			for alias, field in HEADER_FIELDS.get(voucher_type, {}).items()
			if meta.has_field(field)
		}
		number_field = numbers.get(voucher_type)
		if number_field and meta.has_field(number_field):
			mapping["number"] = number_field
		if not mapping:
			continue
		fields = ", ".join("t.`{}` AS `{}`".format(f, a) for a, f in mapping.items())
		for row in _joined(ctx, voucher_type, voucher_type, "voucher_no", fields):
			out[(voucher_type, row.name)] = row
	return out


def _item_lines(ctx, moves):
	"""{child row name: {uom, qty, conversion_factor, stock_qty}}."""
	out = {}
	for voucher_type in {m.voucher_type for m in moves}:
		table = ITEM_TABLES.get(voucher_type)
		if not table:
			continue
		fields = "t.uom, t.qty, t.conversion_factor, t.stock_qty" if frappe.db.has_column(
			table, "stock_qty"
		) else "t.uom, t.qty, t.conversion_factor, t.transfer_qty AS stock_qty"
		for row in _joined(ctx, voucher_type, table, "voucher_detail_no", fields):
			out[row.name] = row
	return out


@lru_cache(maxsize=256)
def _size(uom, stock_uom):
	"""(key, label, nominal kg, sort order) of the size a UOM stands for."""
	if not uom or uom == stock_uom:
		return ("loose", _("Loose ({0})").format(stock_uom), None, 99999)
	match = NOMINAL_RE.search(uom)
	if not match:
		return (frappe.scrub(uom), uom, None, 99998)
	kg = flt(match.group(1)) * (1000 if match.group(2).upper() == "MT" else 1)
	if kg >= BULK_MIN_KG:
		return ("bulk", _("Bulk (MT)"), kg, 99997)
	return ("kg_" + match.group(1).replace(".", "_"), uom, kg, kg)


def _count_cylinders(ctx, move, line):
	key, label, nominal, order = _size(line.uom, ctx.item.stock_uom)
	stock_kg = abs(flt(line.stock_qty) or flt(line.qty) * flt(line.conversion_factor))
	if key == "bulk":
		count = stock_kg / 1000.0
	elif key == "loose":
		count = stock_kg
	else:
		count = abs(flt(line.qty))
	move.cylinders[key] = move.cylinders.get(key, 0.0) + count
	ctx.sizes[key] = (label, order)

	if nominal and abs(nominal - flt(line.conversion_factor)) > 0.0005:
		# booked kg is what the stock moved by; flag it, never correct it
		tag = (line.uom, flt(line.conversion_factor))
		ctx.factor_mismatch[tag] = ctx.factor_mismatch.get(tag, 0) + 1
		note = _("{0} booked as {1} kg each").format(line.uom, flt(line.conversion_factor))
		if note not in move.remarks:
			move.remarks.append(note)


def _visible(ctx, move):
	if ctx.category_filter and move.category != ctx.category_filter:
		return False
	if ctx.customer and move.party_id != ctx.customer:
		return False
	if ctx.supplier and move.party_id != ctx.supplier:
		return False
	if ctx.branch and move.branch != ctx.branch:
		return False
	if ctx.refinery and move.refinery != ctx.refinery:
		return False
	return True


# ------------------------------------------------------------------ views


def _q(ctx, kg):
	return flt(kg / ctx.factor, ctx.precision)


def _r(ctx, rate_per_kg):
	return flt(rate_per_kg * ctx.factor, 4)


def _size_columns(ctx):
	if not ctx.show_cylinders:
		return []
	cols = []
	for key, (label, _order) in sorted(ctx.sizes.items(), key=lambda kv: kv[1][1]):
		precision = 3 if key in ("bulk", "loose") else 0
		cols.append(
			{"fieldname": "cyl_" + key, "label": label, "fieldtype": "Float",
			 "precision": precision, "width": 90}
		)
	return cols


@lru_cache(maxsize=4096)
def _miti(date):
	return bs_date_str(date)


def _blocks(ctx, sections):
	"""The blocks Detail and the print show, in order, and whether they run a balance.

	Item / Warehouse: one block per stock section, with its own opening, running
	balance and closing. Party / Refinery / Movement: the pooled stock's visible
	movements split by that key; each block totals what moved through it.
	"""
	if ctx.group_by in RUNNING_GROUPS:
		blocks = []
		for section in sections.values():
			blocks.append(
				frappe._dict(
					code="" if section.key else ctx.item.name,
					desc=section.key or ctx.item.item_name,
					sub=bool(section.key),
					running=True,
					opening=section.opening,
					closing=section.closing,
					moves=[m for m in section.movements if m.visible],
				)
			)
		return blocks

	groups = {}
	for section in sections.values():
		for move in section.movements:
			if not move.visible:
				continue
			key, code, desc, order = _group_of(ctx, move)
			block = groups.get(key)
			if not block:
				block = groups[key] = frappe._dict(
					code=code, desc=desc, order=order, sub=True, running=False, moves=[]
				)
			block.moves.append(move)
	return sorted(groups.values(), key=lambda b: b.order)


def _group_of(ctx, move):
	"""(key, code, description, sort order) of the block a movement belongs to."""
	if ctx.group_by == GROUP_PARTY:
		if not (move.party_id or move.party):
			return ("", "", _("No Party"), (1, ""))
		return (move.party_id or move.party, move.party_id or "", move.party or move.party_id, (0, (move.party or "").lower()))
	if ctx.group_by == GROUP_REFINERY:
		if move.category in ("purchase", "purchase_return"):
			if move.refinery:
				return (move.refinery, move.refinery, _("{0} Refinery").format(move.refinery), (0, move.refinery))
			return (NO_REFINERY, "", _("Purchases, refinery not recorded"), (1, ""))
		return ("~other", "", _("Sales and other movements"), (2, ""))
	# Movement
	english, nepali = CATEGORIES[move.category]
	return (move.category, _(english), nepali, (list(CATEGORIES).index(move.category), ""))


def _pool_totals(sections):
	"""Opening and closing of the whole stock, across every section."""
	def total(attr):
		qty = sum(s[attr].qty for s in sections.values())
		value = sum(s[attr].value for s in sections.values())
		if len(sections) == 1:
			rate = next(iter(sections.values()))[attr].rate
		else:
			rate = value / qty if qty > EPS else 0.0
		return frappe._dict(qty=qty, value=value, rate=rate)

	return total("opening"), total("closing")


def _detail_view(ctx, sections):
	u = ctx.unit
	columns = [
		{"fieldname": "miti", "label": _("Miti"), "fieldtype": "Data", "width": 95},
		{"fieldname": "posting_date", "label": _("Date (AD)"), "fieldtype": "Date", "width": 95},
		{"fieldname": "type", "label": _("Type"), "fieldtype": "Data", "width": 120},
		{"fieldname": "voucher_no", "label": _("Voucher No"), "fieldtype": "HTML", "width": 150},
		{"fieldname": "party", "label": _("Party"), "fieldtype": "Data", "width": 200},
	]
	# only when a load in the period names one: a sales-only period stays as it was
	if any(m.refinery for s in sections.values() for m in s.movements if m.visible):
		columns.append({"fieldname": "refinery", "label": _("Refinery"), "fieldtype": "Data", "width": 100})
	columns += _size_columns(ctx)
	columns += [
		{"fieldname": "in_qty", "label": _("In ({0})").format(u), "fieldtype": "Float", "precision": ctx.precision, "width": 105},
		{"fieldname": "out_qty", "label": _("Out ({0})").format(u), "fieldtype": "Float", "precision": ctx.precision, "width": 105},
		{"fieldname": "balance_qty", "label": _("Balance ({0})").format(u), "fieldtype": "Float", "precision": ctx.precision, "width": 120},
	]
	if ctx.show_value:
		columns += [
			{"fieldname": "rate", "label": _("Avg Rate / {0}").format(u), "fieldtype": "Currency", "width": 115},
			{"fieldname": "in_value", "label": _("In Value"), "fieldtype": "Currency", "width": 130},
			{"fieldname": "out_value", "label": _("Out Value (Cost)"), "fieldtype": "Currency", "width": 130},
			{"fieldname": "balance_value", "label": _("Balance Value"), "fieldtype": "Currency", "width": 140},
		]
	columns += [
		{"fieldname": "vehicle", "label": _("Vehicle"), "fieldtype": "Data", "width": 110},
		{"fieldname": "reference", "label": _("Tanker / Reference"), "fieldtype": "Data", "width": 220},
		{"fieldname": "remarks", "label": _("Remarks"), "fieldtype": "Data", "width": 200},
	]

	data = []
	blocks = _blocks(ctx, sections)
	for block in blocks:
		if block.sub or len(blocks) > 1:
			heading = "{0}   {1}".format(block.code, block.desc).strip() if block.code else block.desc
			data.append({"type": heading, "is_heading": 1, "bold": 1})
		if block.running:
			data.append(_balance_row(ctx, _("Opening Balance"), block.opening, ctx.from_date))
		total = _Totals()
		for move in block.moves:
			total.add(move)
			data.append(_move_row(ctx, move, block.running))
		data.append(total.row(ctx, _("Period Total")))
		if block.running:
			data.append(_balance_row(ctx, _("Closing Balance"), block.closing, ctx.to_date))

	if ctx.group_by not in RUNNING_GROUPS or len(blocks) > 1:
		# the stock as a whole, under blocks that are not themselves the stock
		opening, closing = _pool_totals(sections)
		data.append({"type": _("Stock"), "is_heading": 1, "bold": 1})
		data.append(_balance_row(ctx, _("Opening Balance"), opening, ctx.from_date))
		data.append(_balance_row(ctx, _("Closing Balance"), closing, ctx.to_date))
	return columns, data


def _move_row(ctx, move, running):
	inward = move.qty > 0
	row = {
		"posting_date": move.posting_date,
		"miti": _miti(move.posting_date),
		"type": CATEGORIES[move.category][0],
		"voucher_no": voucher_link(move.voucher_type, move.voucher_no, move.number),
		"voucher_number": move.number,
		"party": move.party,
		"refinery": move.refinery,
		"warehouse": move.warehouse,
		"in_qty": _q(ctx, move.qty) if inward else 0,
		"out_qty": _q(ctx, -move.qty) if not inward else 0,
		"in_value": flt(move.value, 2) if inward else 0,
		"out_value": flt(-move.value, 2) if not inward else 0,
		"vehicle": move.vehicle,
		"reference": move.reference,
		"remarks": "; ".join(move.remarks),
		"category": move.category,
	}
	if running:
		# a party or refinery has no stock of its own; its rows carry no balance
		row.update(
			balance_qty=_q(ctx, move.balance_qty),
			rate=_r(ctx, move.rate),
			balance_value=flt(move.balance_value, 2),
		)
	for key, count in move.cylinders.items():
		row["cyl_" + key] = count
	return row


def _balance_row(ctx, label, bal, date):
	return {
		"posting_date": date,
		"miti": _miti(date),
		"type": label,
		"balance_qty": _q(ctx, bal.qty),
		"rate": _r(ctx, bal.rate),
		"balance_value": flt(bal.value, 2),
		"bold": 1,
		"is_balance": 1,
	}


class _Totals:
	"""Sums of the visible movements: in/out kg and value, per category, per size."""

	def __init__(self):
		self.in_kg = self.out_kg = self.in_value = self.out_value = 0.0
		self.by_category = {key: 0.0 for key in CATEGORIES}
		self.sold = {}

	def add(self, move):
		if move.qty > 0:
			self.in_kg += move.qty
			self.in_value += move.value
		else:
			self.out_kg -= move.qty
			self.out_value -= move.value
		self.by_category[move.category] += abs(move.qty)
		if move.category in ("sale", "sale_return"):
			sign = 1 if move.category == "sale" else -1
			for key, count in move.cylinders.items():
				self.sold[key] = self.sold.get(key, 0.0) + sign * count

	def row(self, ctx, label):
		row = {
			"type": label,
			"in_qty": _q(ctx, self.in_kg),
			"out_qty": _q(ctx, self.out_kg),
			"in_value": flt(self.in_value, 2),
			"out_value": flt(self.out_value, 2),
			"bold": 1,
			"is_total": 1,
		}
		for key, count in self.sold.items():
			row["cyl_" + key] = count
		return row


def _summary_view(ctx, sections, by):
	"""One row per day (AD + Miti) or per BS month, with the period's flow."""
	u = ctx.unit
	columns = [
		{"fieldname": "period", "label": _("Miti") if by == "day" else _("Month (BS)"), "fieldtype": "Data", "width": 130},
	]
	if by == "day":
		columns.append({"fieldname": "ad_date", "label": _("Date (AD)"), "fieldtype": "Data", "width": 95})
	columns.append({"fieldname": "opening_qty", "label": _("Opening ({0})").format(u), "fieldtype": "Float", "precision": ctx.precision, "width": 115})
	for key, (english, _nepali) in CATEGORIES.items():
		columns.append({"fieldname": key, "label": "{} ({})".format(_(english), u), "fieldtype": "Float", "precision": ctx.precision, "width": 115})
	columns.append({"fieldname": "closing_qty", "label": _("Closing ({0})").format(u), "fieldtype": "Float", "precision": ctx.precision, "width": 115})
	sized = _size_columns(ctx)
	for col in sized:
		col["label"] = _("{0} sold").format(col["label"])
	columns += sized
	if ctx.show_value:
		columns += [
			{"fieldname": "in_value", "label": _("Received Value"), "fieldtype": "Currency", "width": 135},
			{"fieldname": "out_value", "label": _("Cost of Issue"), "fieldtype": "Currency", "width": 135},
			{"fieldname": "closing_value", "label": _("Closing Value"), "fieldtype": "Currency", "width": 140},
			{"fieldname": "rate", "label": _("Avg Rate / {0}").format(u), "fieldtype": "Currency", "width": 115},
		]

	data = []
	for section in sections.values():
		if ctx.by_warehouse:
			data.append({"period": section.key, "bold": 1, "is_heading": 1})
		buckets = _buckets(ctx, section, by)
		grand = _Totals()
		for bucket in buckets:
			row = {
				"period": bucket.label,
				"ad_date": bucket.get("ad_date"),
				"opening_qty": _q(ctx, bucket.opening.qty),
				"closing_qty": _q(ctx, bucket.closing.qty),
				"in_value": flt(bucket.totals.in_value, 2),
				"out_value": flt(bucket.totals.out_value, 2),
				"closing_value": flt(bucket.closing.value, 2),
				"rate": _r(ctx, bucket.closing.rate),
			}
			for key, kg in bucket.totals.by_category.items():
				row[key] = _q(ctx, kg)
			for key, count in bucket.totals.sold.items():
				row["cyl_" + key] = count
			data.append(row)
			for move in bucket.moves:
				grand.add(move)
		total = {
			"period": _("Total"),
			"opening_qty": _q(ctx, section.opening.qty),
			"closing_qty": _q(ctx, section.closing.qty),
			"in_value": flt(grand.in_value, 2),
			"out_value": flt(grand.out_value, 2),
			"closing_value": flt(section.closing.value, 2),
			"rate": _r(ctx, section.closing.rate),
			"bold": 1,
			"is_total": 1,
		}
		for key, kg in grand.by_category.items():
			total[key] = _q(ctx, kg)
		for key, count in grand.sold.items():
			total["cyl_" + key] = count
		data.append(total)
	return columns, data


def _buckets(ctx, section, by):
	"""Group a section's movements by day or BS month.

	Opening/closing of a bucket are the true pool balance (every movement),
	the flow columns sum only the visible ones. Monthly lists every BS month in
	the range, quiet ones included, so a month with no sale still shows its stock.
	"""
	from rdp_common_app.utils.bs_boundaries import ad_to_bs, get_bs_month_name, get_bs_month_range

	def month_key(date):
		bs = ad_to_bs(date)
		return (bs.year, bs.month)

	buckets = OrderedDict()
	if by == "month":
		start, end = month_key(ctx.from_date), month_key(ctx.to_date)
		year, month = start
		while (year, month) <= end:
			buckets[(year, month)] = frappe._dict(
				label="{} {}".format(get_bs_month_name(month), year), moves=[]
			)
			year, month = (year + 1, 1) if month == 12 else (year, month + 1)

	balance = frappe._dict(section.opening)
	for move in section.movements:
		key = move.posting_date if by == "day" else month_key(move.posting_date)
		bucket = buckets.get(key)
		if bucket is None:
			bucket = buckets[key] = frappe._dict(
				label=_miti(move.posting_date),
				ad_date=frappe.format(move.posting_date, "Date"),
				moves=[],
			)
		bucket.setdefault("opening", balance)
		bucket.moves.append(move)
		balance = frappe._dict(qty=move.balance_qty, value=move.balance_value, rate=move.rate)
		bucket.closing = balance

	carried = frappe._dict(section.opening)
	for bucket in buckets.values():
		bucket.setdefault("opening", carried)
		bucket.setdefault("closing", bucket.opening)
		carried = bucket.closing
		bucket.totals = _Totals()
		for move in bucket.moves:
			if move.visible:
				bucket.totals.add(move)
	return list(buckets.values())


def _stock_book_view(ctx, sections):
	"""The IRD-style stock book: receipts, issues and balance, each qty/rate/amount."""
	u = ctx.unit
	num = lambda f, label, w=110: {"fieldname": f, "label": label, "fieldtype": "Float", "precision": ctx.precision, "width": w}
	cur = lambda f, label, w=130: {"fieldname": f, "label": label, "fieldtype": "Currency", "width": w}
	columns = [
		{"fieldname": "miti", "label": "मिति", "fieldtype": "Data", "width": 95},
		{"fieldname": "particulars", "label": "विवरण", "fieldtype": "Data", "width": 230},
		{"fieldname": "voucher_no", "label": "बीजक / भौचर नं.", "fieldtype": "HTML", "width": 150},
		num("in_qty", "आम्दानी परिमाण ({})".format(u)),
		cur("in_rate", "आम्दानी दर", 100),
		cur("in_value", "आम्दानी रकम"),
		num("out_qty", "खर्च परिमाण ({})".format(u)),
		cur("out_rate", "खर्च दर", 100),
		cur("out_value", "खर्च रकम"),
		num("balance_qty", "बाँकी परिमाण ({})".format(u)),
		cur("rate", "बाँकी दर", 100),
		cur("balance_value", "बाँकी रकम", 140),
		{"fieldname": "remarks", "label": "कैफियत", "fieldtype": "Data", "width": 180},
	]

	data = []
	for section in sections.values():
		if ctx.by_warehouse:
			data.append({"particulars": section.key, "bold": 1, "is_heading": 1})
		op = section.opening
		data.append({
			"miti": _miti(ctx.from_date), "particulars": "अघिल्लो मौज्दात (Opening)",
			"balance_qty": _q(ctx, op.qty), "rate": _r(ctx, op.rate),
			"balance_value": flt(op.value, 2), "bold": 1, "is_balance": 1,
		})
		total = _Totals()
		for move in section.movements:
			if not move.visible:
				continue
			total.add(move)
			english, nepali = CATEGORIES[move.category]
			qty = _q(ctx, abs(move.qty))
			rate = flt(abs(move.value) / qty, 4) if qty else 0
			inward = move.qty > 0
			data.append({
				"miti": _miti(move.posting_date),
				"particulars": "{} — {}".format(nepali, move.party) if move.party else nepali,
				"voucher_no": voucher_link(move.voucher_type, move.voucher_no, move.number),
				"voucher_number": move.number,
				"in_qty": qty if inward else 0,
				"in_rate": rate if inward else 0,
				"in_value": flt(move.value, 2) if inward else 0,
				"out_qty": qty if not inward else 0,
				"out_rate": rate if not inward else 0,
				"out_value": flt(-move.value, 2) if not inward else 0,
				"balance_qty": _q(ctx, move.balance_qty),
				"rate": _r(ctx, move.rate),
				"balance_value": flt(move.balance_value, 2),
				"remarks": "; ".join(move.remarks),
				"category": move.category,
			})
		data.append({
			"particulars": "जम्मा (Total)",
			"in_qty": _q(ctx, total.in_kg), "in_value": flt(total.in_value, 2),
			"out_qty": _q(ctx, total.out_kg), "out_value": flt(total.out_value, 2),
			"bold": 1, "is_total": 1,
		})
		cl = section.closing
		data.append({
			"miti": _miti(ctx.to_date), "particulars": "बाँकी मौज्दात (Closing)",
			"balance_qty": _q(ctx, cl.qty), "rate": _r(ctx, cl.rate),
			"balance_value": flt(cl.value, 2), "bold": 1, "is_balance": 1,
		})
	return columns, data


def _refinery_view(ctx, sections):
	"""Where the gas came from: loads, quantity and landed cost per refinery.

	Counts purchases and purchase returns only (a return nets against its
	refinery's loads). Purchases whose invoice names no refinery are one row of
	their own, so the total always equals the period's purchases.
	"""
	u = ctx.unit
	columns = [
		{"fieldname": "refinery", "label": _("Refinery"), "fieldtype": "Data", "width": 160},
		{"fieldname": "loads", "label": _("Loads"), "fieldtype": "Int", "width": 80},
		{"fieldname": "received", "label": _("Received ({0})").format(u), "fieldtype": "Float", "precision": ctx.precision, "width": 125},
		{"fieldname": "returned", "label": _("Returned ({0})").format(u), "fieldtype": "Float", "precision": ctx.precision, "width": 125},
		{"fieldname": "net", "label": _("Net ({0})").format(u), "fieldtype": "Float", "precision": ctx.precision, "width": 125},
		{"fieldname": "share", "label": _("Share %"), "fieldtype": "Percent", "width": 90},
	]
	if ctx.show_value:
		columns += [
			{"fieldname": "value", "label": _("Net Cost"), "fieldtype": "Currency", "width": 140},
			{"fieldname": "rate", "label": _("Avg Cost / {0}").format(u), "fieldtype": "Currency", "width": 125},
		]
	columns += [
		{"fieldname": "first_miti", "label": _("First Load (Miti)"), "fieldtype": "Data", "width": 120},
		{"fieldname": "last_miti", "label": _("Last Load (Miti)"), "fieldtype": "Data", "width": 120},
	]

	rows = {}
	for section in sections.values():
		for move in section.movements:
			if not move.visible or move.category not in ("purchase", "purchase_return"):
				continue
			key = move.refinery or NO_REFINERY
			row = rows.setdefault(key, frappe._dict(refinery=key, loads=0, in_kg=0.0, out_kg=0.0, value=0.0, first=None, last=None))
			if move.category == "purchase":
				row.loads += 1
				row.in_kg += move.qty
				row.first = min(row.first or move.posting_date, move.posting_date)
				row.last = max(row.last or move.posting_date, move.posting_date)
			else:
				row.out_kg -= move.qty
			row.value += move.value

	net_total = sum(r.in_kg - r.out_kg for r in rows.values())
	# biggest supplier of gas first, "(Not recorded)" always last
	ordered = sorted(rows.values(), key=lambda r: (r.refinery == NO_REFINERY, -(r.in_kg - r.out_kg)))
	data = [_refinery_row(ctx, r, net_total) for r in ordered]
	if data:
		total = frappe._dict(
			refinery=_("Total"),
			loads=sum(r.loads for r in rows.values()),
			in_kg=sum(r.in_kg for r in rows.values()),
			out_kg=sum(r.out_kg for r in rows.values()),
			value=sum(r.value for r in rows.values()),
			first=min((r.first for r in rows.values() if r.first), default=None),
			last=max((r.last for r in rows.values() if r.last), default=None),
		)
		data.append(dict(_refinery_row(ctx, total, net_total), bold=1, is_total=1))
	return columns, data


def _refinery_row(ctx, r, net_total):
	net = r.in_kg - r.out_kg
	return {
		"refinery": r.refinery,
		"loads": r.loads,
		"received": _q(ctx, r.in_kg),
		"returned": _q(ctx, r.out_kg),
		"net": _q(ctx, net),
		"share": flt(net / net_total * 100, 2) if abs(net_total) > EPS else 0,
		"value": flt(r.value, 2),
		"rate": _r(ctx, r.value / net) if abs(net) > EPS else 0,
		"first_miti": _miti(r.first) if r.first else "",
		"last_miti": _miti(r.last) if r.last else "",
	}


# ----------------------------------------------- message, chart, cards


def _message(ctx, sections):
	"""Plain-language warnings about the data, so a strange balance explains itself."""
	notes = []
	for section in sections.values():
		where = " ({})".format(section.key) if section.key else ""
		low = min([section.opening] + [frappe._dict(qty=m.balance_qty, d=m.posting_date) for m in section.movements], key=lambda b: b.qty)
		if low.qty < -EPS:
			first = next((m for m in section.movements if m.balance_qty < -EPS), None)
			when = _("before this period") if section.opening.qty < -EPS or not first else frappe.format(first.posting_date, "Date")
			notes.append(_(
				"Stock{0} is below zero from {1} (lowest {2} {3}). Gas was sold without a matching purchase "
				"or opening stock in the system."
			).format(where, when, frappe.format(_q(ctx, low.qty), "Float"), ctx.unit))
		has_receipt = section.had_cost_before or any(m.booked_qty > EPS for m in section.movements)
		if ctx.show_value and not has_receipt:
			notes.append(_("No purchase cost is recorded{0} up to {1}, so values show 0. Enter the opening stock "
				"(Stock Reconciliation) or purchases to value it.").format(where, frappe.format(ctx.to_date, "Date")))

	for (uom, factor), count in sorted(ctx.factor_mismatch.items()):
		notes.append(_("{0} line(s) in this period book \"{1}\" as {2} kg each. Booked kg is shown; fix the UOM "
			"conversion on the item.").format(count, uom, factor))

	zero = sum(m.stored_zero for s in sections.values() for m in s.movements)
	if ctx.show_value and zero:
		notes.append(_("ERPNext booked {0} issue entries at zero cost; values here are this report's moving "
			"average, so they will differ from ERPNext's Stock Ledger and the GL.").format(zero))

	if not notes:
		return None
	items = "".join("<li>{}</li>".format(frappe.utils.escape_html(n)) for n in notes)
	return '<div class="gas-ledger-notes"><ul style="margin:0;padding-left:18px">{}</ul></div>'.format(items)


def _chart(ctx, sections):
	if ctx.view not in (VIEW_DAILY, VIEW_MONTHLY) or len(sections) != 1:
		return None
	section = next(iter(sections.values()))
	buckets = _buckets(ctx, section, "day" if ctx.view == VIEW_DAILY else "month")
	if len(buckets) < 2:
		return None
	return {
		"data": {
			"labels": [b.label for b in buckets],
			"datasets": [{"name": _("Closing ({0})").format(ctx.unit), "values": [_q(ctx, b.closing.qty) for b in buckets]}],
		},
		"type": "line",
		"lineOptions": {"regionFill": 1},
		"fieldtype": "Float",
	}


def _cards(ctx, sections):
	opening = sum(s.opening.qty for s in sections.values())
	closing = sum(s.closing.qty for s in sections.values())
	value = sum(s.closing.value for s in sections.values())
	total = _Totals()
	for section in sections.values():
		for move in section.movements:
			if move.visible:
				total.add(move)
	received = total.by_category["purchase"] - total.by_category["purchase_return"]
	sold = total.by_category["sale"] - total.by_category["sale_return"]
	q = lambda kg: frappe.format(_q(ctx, kg), {"fieldtype": "Float", "precision": ctx.precision})
	month = period_label(ctx.from_date, ctx.to_date)
	cards = [
		{
			"label": _("Period"),
			"value": month or "{0} – {1}".format(_miti(ctx.from_date), _miti(ctx.to_date)),
			"datatype": "Data",
		},
		{"label": _("Opening ({0})").format(ctx.unit), "value": q(opening), "datatype": "Data"},
		{"label": _("Purchased, net ({0})").format(ctx.unit), "value": q(received), "datatype": "Data", "indicator": "Green"},
		{"label": _("Sold, net ({0})").format(ctx.unit), "value": q(sold), "datatype": "Data", "indicator": "Blue"},
		{"label": _("Closing ({0})").format(ctx.unit), "value": q(closing), "datatype": "Data",
		 "indicator": "Red" if closing < -EPS else "Green"},
	]
	if ctx.weight_item:
		cards.append({"label": _("Sold as 14.2 kg cylinders"), "value": cint(sold / DOMESTIC_CYLINDER_KG), "datatype": "Int"})
	if ctx.show_value:
		cards.append({"label": _("Closing Value"), "value": value, "datatype": "Currency"})
	return cards


# ------------------------------------------------------------ filter helpers


# BS months in fiscal-year order: Shrawan (4) opens the year, Ashadh (3) closes it.
BS_FY_MONTHS = (4, 5, 6, 7, 8, 9, 10, 11, 12, 1, 2, 3)

# Period choices around the months, in the order the dropdown lists them.
PERIODS_BEFORE_MONTHS = ("Fiscal Year", "Last Fiscal Year", "This Fiscal Quarter", "Last Fiscal Quarter")
PERIODS_AFTER_MONTHS = ("Today", "Yesterday", "Custom Dates")


def _bs_month_number(name):
	"""1-12 for a BS month name ("Shrawan" -> 4), else 0."""
	from rdp_common_app.utils.bs_boundaries import BS_MONTH_NAMES

	return next((number for number, month in BS_MONTH_NAMES.items() if month == name), 0)


def _fy_start_bs_year(fiscal_year=None):
	"""The BS year a fiscal year's Shrawan falls in (FY 83/84 -> 2083)."""
	from rdp_common_app.utils.bs_boundaries import ad_to_bs

	start = fiscal_year and frappe.db.get_value("Fiscal Year", fiscal_year, "year_start_date")
	if start:
		return ad_to_bs(getdate(start)).year
	today = ad_to_bs(getdate(frappe.utils.nowdate()))
	return today.year if today.month >= 4 else today.year - 1


@frappe.whitelist()
def get_period_options(fiscal_year=None):
	"""The Period dropdown: the fixed choices, with the selected fiscal year's
	twelve Nepali months (Shrawan .. Ashadh) in it, and This / Last Month saying
	which month they are."""
	from rdp_common_app.utils.bs_boundaries import get_bs_month_name

	this, last = get_bs_month_period("This Month"), get_bs_month_period("Last Month")
	first_year = _fy_start_bs_year(fiscal_year)
	options = [{"value": p, "label": _(p)} for p in PERIODS_BEFORE_MONTHS]
	options.append({"value": "This Month", "label": _("This Month ({0})").format(this["label"])})
	options.append({"value": "Last Month", "label": _("Last Month ({0})").format(last["label"])})
	for month in BS_FY_MONTHS:
		year = first_year if month >= 4 else first_year + 1
		name = get_bs_month_name(month)
		options.append({"value": name, "label": "{0} {1}".format(name, year)})
	options += [{"value": p, "label": _(p)} for p in PERIODS_AFTER_MONTHS]
	return options


@frappe.whitelist()
def get_bs_month_period(preset=None, fiscal_year=None, bs_year=None, bs_month=None):
	"""AD dates of a Nepali month, and which month it is.

	`preset` is "This Month", "Last Month", or a month's name ("Kartik"), which
	is that month of `fiscal_year` (the current one if none). A caller may give
	`bs_year` and `bs_month` (1 = Baisakh) instead.
	"""
	from rdp_common_app.utils.bs_boundaries import ad_to_bs, get_bs_month_range

	named = _bs_month_number(preset)
	if named:
		first_year = _fy_start_bs_year(fiscal_year)
		year, month = (first_year if named >= 4 else first_year + 1), named
	elif preset in ("This Month", "Last Month") or not (cint(bs_year) and cint(bs_month)):
		today = ad_to_bs(getdate(frappe.utils.nowdate()))
		year, month = today.year, today.month
		if preset == "Last Month":
			year, month = (year - 1, 12) if month == 1 else (year, month - 1)
	else:
		year, month = cint(bs_year), cint(bs_month)
		if not 1 <= month <= 12:
			frappe.throw(_("Month must be 1 to 12"))
	start, end = get_bs_month_range(year, month)
	return {
		"from_date": str(start),
		"to_date": str(end),
		"bs_year": year,
		"bs_month": month,
		"label": _month_label(year, month),
	}


def _month_label(year, month):
	from rdp_common_app.utils.bs_boundaries import get_bs_month_name

	return "{0} {1}".format(get_bs_month_name(month), year)


def period_label(from_date, to_date):
	"""'Kartik 2083' when the period is exactly one Nepali month, else ''."""
	from rdp_common_app.utils.bs_boundaries import ad_to_bs, get_bs_month_range

	start = ad_to_bs(getdate(from_date))
	if start.day != 1:
		return ""
	first, last = get_bs_month_range(start.year, start.month)
	if getdate(first) == getdate(from_date) and getdate(last) == getdate(to_date):
		return _month_label(start.year, start.month)
	return ""


@frappe.whitelist()
def get_units(item_code):
	"""The units the Show Quantity In filter offers: MT and Kg, then the item's UOMs by size."""
	stock_uom = frappe.db.get_value("Item", item_code, "stock_uom")
	if not stock_uom:
		return []
	return [unit for unit, _factor in _units(item_code, stock_uom)]


@frappe.whitelist()
def get_refineries():
	"""The Refinery options, read from the Purchase Invoice field itself."""
	df = frappe.get_meta("Purchase Invoice").get_field(HEADER_FIELDS["Purchase Invoice"]["refinery"])
	if not df or df.fieldtype != "Select":
		return []
	return [o for o in (df.options or "").split("\n") if o]


@frappe.whitelist()
def get_default_item(company):
	"""The company's gas item, so the report opens on the thing people ask about."""
	return frappe.db.get_value(
		"Item",
		{"item_name": GAS_ITEM_NAME, "custom_company": company, "disabled": 0, "is_stock_item": 1},
		"name",
	)
