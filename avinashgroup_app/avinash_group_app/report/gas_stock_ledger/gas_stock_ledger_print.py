# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

"""Gas Stock Ledger, printed as the legacy Posting Detail page.

The same page General Ledger Posting Detail prints ("Normal Sub Ledger - Detail -
Posting Detail"), with quantities where money was: the masthead, the boxed
column heads, Opening Balance / Period Total / Closing Balance bands, a block's
heading repeated on every page it runs onto, "Page n/N", and Report Parameters
closing the last page.

Nothing here re-implements that page. The font metrics, the text wrap, the
placement of each line and the HTML template are General Ledger Posting
Detail's own (`glpd`), so the two prints stay identical as either changes. Only
the frame's labels, the column positions and what goes in each line are
stock's.

Blocks follow the report's Group By (`gas_stock_ledger._blocks`): an Item or
Warehouse block runs a balance like a ledger; a Party, Refinery or Movement
block totals what moved through it, and the stock's own opening and closing
follow the last block -- where the legacy print puts a ledger's Balance line.
"""

import json
import os

import frappe
from frappe import _
from frappe.utils import cint, flt

from avinashgroup_app.avinash_group_app.report.gas_stock_ledger import gas_stock_ledger as gsl
from avinashgroup_app.avinash_group_app.report.general_ledger_posting_detail import (
	general_ledger_posting_detail as glpd,
)

REPORT = "Gas Stock Ledger"

# x positions in points: left edges, or right edges for quantities. Code,
# description, date, voucher and text are the legacy page's own; the three
# quantity columns take the room Document Amount / Debit / Credit had.
X = frappe._dict(
	code=23.0,
	desc=110.3,
	date=50.2,
	voucher=101.3,
	text=188.4,
	net=197.7,  # right edge of a band's figure
	side=201.4,  # the unit after it
	qty_in=420.0,
	qty_out=499.0,
	balance=578.3,
	params=(23.0, 196.4, 361.6),
)
TEXT_W = 172.0  # 188.4 -> 360.4: clear of the widest In figure
CODE_W = 85.0  # a block code must end before its description at 110.3
QTY_W = 74.0  # one quantity column


def _capped(lines, limit=None):
	"""A long remark cut to `limit` lines with an ellipsis, so no row outgrows a page."""
	limit = limit or glpd.PRINT_NARRATION_MAX
	if len(lines) <= limit:
		return lines
	lines = lines[:limit]
	last = lines[-1]
	if isinstance(last, list):  # placed runs: [[run]]
		last[0] = dict(last[0], text=last[0]["text"].rstrip(". ") + " …")
	else:
		lines[-1] = last.rstrip(". ") + " …"
	return lines


def _flow_label(ctx, label):
	"""'In (MT)' -- or bare 'In' under Transaction UOM, where each row names its own UOM."""
	return label if ctx.txn_uom else "{0} ({1})".format(label, ctx.unit)


def _unit_label(ctx):
	"""What the quantities are in, for a print's masthead and parameters."""
	return _("Transaction UOM (totals in {0})").format(ctx.unit) if ctx.txn_uom else ctx.unit


def _flow_text(ctx, text):
	"""A band's In / Out figure; under Transaction UOM it says its unit."""
	return "{0} {1}".format(text, ctx.unit) if text and ctx.txn_uom else text


def _fmt_qty(value, precision):
	"""Nepali digit grouping at the unit's precision -- 1,23,456.789. Blank for zero."""
	value = flt(value, precision)
	if not value:
		return ""
	whole, _sep, decimals = "{0:.{1}f}".format(abs(value), precision).partition(".")
	if len(whole) > 3:
		grouped, whole = whole[-3:], whole[:-3]
		while whole:
			grouped, whole = whole[-2:] + "," + grouped, whole[:-2]
	else:
		grouped = whole
	return "{0}{1}{2}".format("-" if value < 0 else "", grouped, "." + decimals if decimals else "")


def _frame(ctx, head, page_no, total_pages):
	"""Masthead, rules, the boxed column heads and the foot, on every page."""
	pt, at = glpd._pt, glpd._set_y
	right = glpd.PRINT_PAGE_W - 16.0
	u = ctx.unit
	items = [
		{"kind": "rule", "y": 14.4, "w": 1.5, "colour": "#000"},
		at(pt(X.code, "{0}{1}".format(head.company, " FY [{0}]".format(head.fy) if head.fy else ""), bold=True), 17.3),
		at(pt(right, "Stock Ledger - Detail - Posting Detail", size=14.0, bold=True, align="r"), 18.2),
		at(pt(right, "Accounting Period : {0}".format(head.period) if head.period else "", bold=True, align="r"), 36.6),
		at(pt(right, "Page {0}/{1}".format(page_no, total_pages), bold=True, align="r"), 75.4),
		# the Nepali month, when the period is exactly one -- "Month : Kartik 2083"
		at(pt(X.code, "Month : {0}".format(head.month) if head.month else "", bold=True), 75.4),
		at(pt(X.code, "From {0} To {1}".format(head.from_bs, head.to_bs)), 88.2),
		at(pt(151.2, "(All parameters listed at end of report)"), 88.2),
		at(
			pt(
				right,
				"Quantity in {0}{1}".format(_unit_label(ctx), " · Amount in Nepalese Rupee ( NPR )" if ctx.show_value else ""),
				align="r",
			),
			88.2,
		),
		{"kind": "rule", "y": 99.9, "w": 0.75, "colour": "#000"},
		{"kind": "box", "top": 102.8, "height": 43.3, "w": 0.8},
		at(pt(X.code, "Item Code", bold=True), 107.1),
		at(pt(X.desc, "Item Description", bold=True), 107.1),
		at(pt(X.code, "Sub Ledger Code", bold=True), 120.7),
		at(pt(X.desc, "Sub Ledger Description", bold=True), 120.7),
		at(pt(X.date, "Date", bold=True), 134.5),
		at(pt(X.voucher, "Voucher Number", bold=True), 134.5),
		at(pt(X.text, "Party / Description", bold=True), 134.5),
		at(pt(X.qty_in, _flow_label(ctx, "In"), bold=True, align="r"), 134.5),
		at(pt(X.qty_out, _flow_label(ctx, "Out"), bold=True, align="r"), 134.5),
		at(pt(578.0, "Balance ({0})".format(u), bold=True, align="r"), 134.5),
	]
	label = "Design Name : "
	items.append(at(pt(X.code, label, size=6.0, bold=True), 813.4))
	items.append(at(pt(X.code + glpd._text_pt(label, 6.0, True), "Stock Posting Detail [DEFAULT]", size=6.0), 813.4))
	return items


def _pages(ctx, sections):
	"""The ledger cut into pages of placed items, the way the legacy print cuts it.

	A heading travels with its Opening Balance, a movement with its sub-lines, a
	block's totals with each other; a page that opens inside a block repeats the
	block's heading lines first.
	"""
	pt = glpd._pt
	blocks = gsl._blocks(ctx, sections)
	opening, closing = gsl._pool_totals(sections)
	if not blocks and abs(opening.qty) < gsl.EPS:
		return []

	def qty(kg):
		return _fmt_qty(gsl._q(ctx, kg), ctx.precision)

	def balance(kg):
		# a balance is always stated, zero included -- "0.000", never blank
		return qty(kg) or "{0:.{1}f}".format(0, ctx.precision)

	def amount_run(x, text, bold=False):
		return pt(x, text, size=glpd._fit(text, QTY_W, 9.0, bold), bold=bold, align="r")

	def moved(move):
		"""A movement's In / Out figure: its own UOM under Transaction UOM."""
		if ctx.txn_uom:
			return gsl._txn_text(ctx, move) if move.txn else _flow_text(ctx, qty(abs(move.qty)))
		return qty(abs(move.qty))

	def heading(code, desc):
		runs = []
		if code:
			runs.append(pt(X.code, code, size=glpd._fit(code, CODE_W, 9.0, True), bold=True))
		runs.append(pt(X.desc, desc or "", bold=True))
		return {"lines": [runs]}

	def value_line(bal):
		if not ctx.show_value:
			return []
		from avinashgroup_app.avinash_group_app.report.custom_ledger.custom_ledger import _fmt_npr

		text = "Value : {0}".format(_fmt_npr(bal.value) or "0.00")
		if bal.rate:
			text += "   @ {0} / {1}".format(_fmt_npr(gsl._r(ctx, bal.rate)), ctx.unit)
		return [[pt(X.text, text)]]

	def band(label, net_kg=None, in_kg=0.0, out_kg=0.0, bal=None, rule=None, rule_after=False, flow=False):
		"""A bold band line. A balance keeps its sign (negative stock is real); a
		flow (Period Total) is stated as a size and a side -- "4.572 MT OUT" -- as
		the legacy page states a net with DEBIT / CREDIT."""
		runs = [pt(X.code, label, bold=True)]
		if net_kg is not None:
			figure = abs(net_kg) if flow else net_kg
			runs.append(pt(X.net, balance(figure), bold=True, align="r"))
			side = ctx.unit
			if flow and qty(figure):
				side = "{0} {1}".format(ctx.unit, "IN" if net_kg > 0 else "OUT")
			runs.append(pt(X.side, side, bold=True))
		if qty(in_kg):
			runs.append(amount_run(X.qty_in, _flow_text(ctx, qty(in_kg))))
		if qty(out_kg):
			runs.append(amount_run(X.qty_out, _flow_text(ctx, qty(out_kg))))
		if bal is not None:
			runs.append(amount_run(X.balance, balance(bal.qty), bold=True))
		lines = [runs] + (value_line(bal) if bal is not None else [])
		return {"lines": lines, "rule": rule, "rule_after": rule_after}

	def text_lines(text):
		return [[pt(X.text, line)] for line in glpd._wrap_pt(text, TEXT_W)]

	def cylinders(move):
		parts = []
		for key, count in sorted(move.cylinders.items(), key=lambda kv: ctx.sizes.get(kv[0], ("", 0))[1]):
			label = ctx.sizes.get(key, (key, 0))[0]
			shown = _fmt_qty(count, 3 if key in ("bulk", "loose") else 0)
			if shown:
				parts.append("{0} × {1}".format(label, shown))
		return ", ".join(parts)

	def movement_fields(move, running):
		english, _nepali = gsl.CATEGORIES[move.category]

		# What moved, in which sizes, at what cost -- one line where it fits.
		detail = [english]
		# a load booked only in bulk or loose kg would just repeat the In / Out figure
		if ctx.show_cylinders and set(move.cylinders) - {"bulk", "loose"} and not (ctx.txn_uom and move.txn):
			detail.append(cylinders(move))
		if ctx.show_value and abs(move.value) >= 0.005:
			from avinashgroup_app.avinash_group_app.report.custom_ledger.custom_ledger import _fmt_npr

			detail.append("{0}: {1}".format("Value" if move.qty > 0 else "Cost", _fmt_npr(abs(move.value))))
		detail = " · ".join(detail)

		# Under a party's own heading its name would only repeat on every row, so
		# the row opens with what moved instead -- as GL Posting Detail drops the
		# party from rows grouped by party.
		by_party = ctx.group_by == gsl.GROUP_PARTY and (move.party or move.party_id)
		desc = glpd._wrap_pt(detail if by_party else (move.party or _(english)), TEXT_W)
		voucher = move.number or move.voucher_no or ""
		first = [
			pt(X.date, gsl._miti(move.posting_date).replace("-", "/")),
			pt(X.voucher, voucher, size=min(9.0, round(9.0 * glpd.PRINT_VOUCHER_W / max(glpd._text_pt(voucher), 1), 2))),
			pt(X.text, desc[0]),
		]
		figure = moved(move)
		first.append(amount_run(X.qty_in if move.qty > 0 else X.qty_out, figure))
		if running:
			first.append(amount_run(X.balance, balance(move.balance_qty)))
		fields = [{"lines": [first] + [[pt(X.text, line)] for line in desc[1:]]}]
		if not by_party:
			fields.append({"lines": text_lines(detail)})

		facts = []
		if move.refinery:
			facts.append("Refinery: {0}".format(move.refinery))
		if move.reference:
			facts.append(move.reference)
		if move.vehicle:
			facts.append("Vehicle: {0}".format(move.vehicle))
		if facts:
			fields.append({"lines": text_lines(" · ".join(facts))})
		if move.narration:
			# the voucher's own remark, as the legacy page prints a narration
			fields.append({"lines": _capped(text_lines("Narration : {0}".format(move.narration)))})
		if move.remarks:
			fields.append({"lines": text_lines("Note : {0}".format("; ".join(move.remarks)))})
		return fields

	units = []
	item_line = heading(ctx.item.name, ctx.item.item_name)
	for index, block in enumerate(blocks):
		sub_line = heading(block.code, block.desc) if block.sub else None
		context = [item_line] + ([sub_line] if sub_line else [])
		head = ([item_line] if index == 0 else []) + ([sub_line] if sub_line else [])
		if block.running:
			head.append(band(_("Opening Balance"), block.opening.qty, bal=block.opening))
		units.append({"fields": head, "ctx": context, "head": True})

		in_kg = out_kg = 0.0
		for move in block.moves:
			units.append({"fields": movement_fields(move, block.running), "ctx": context, "head": False})
			if move.qty > 0:
				in_kg += move.qty
			else:
				out_kg -= move.qty

		tail = [band(_("Period Total"), in_kg - out_kg, in_kg, out_kg, rule=glpd.PRINT_GREY_RULE, flow=True)]
		if block.running:
			tail.append(band(_("Closing Balance"), block.closing.qty, bal=block.closing))
		units.append({"fields": tail, "ctx": context, "head": False})

	if not blocks:
		units.append({"fields": [item_line], "ctx": [], "head": True})
	if ctx.group_by not in gsl.RUNNING_GROUPS or len(blocks) != 1:
		# the stock itself, under blocks that are not the stock -- the legacy
		# print's Balance line for a ledger with sub ledgers
		units.append(
			{
				"fields": [
					band(_("Opening Balance"), opening.qty, bal=opening, rule=glpd.PRINT_GREY_RULE),
					band(_("Closing Balance"), closing.qty, bal=closing, rule_after=True),
				],
				"ctx": [item_line],
				"head": False,
			}
		)

	pages = [[]]
	cursor = glpd.PRINT_BODY_TOP
	after_rule = False
	for unit in units:
		end = glpd._measure(cursor, unit["fields"])
		if end - glpd.PRINT_PITCH > glpd.PRINT_BODY_BOTTOM and cursor > glpd.PRINT_BODY_TOP:
			pages.append([])
			cursor = glpd.PRINT_BODY_TOP
			if not unit["head"] and unit["ctx"]:
				for field in unit["ctx"]:
					cursor = glpd._place(pages[-1], cursor, field)
		for field in unit["fields"]:
			cursor = glpd._place(pages[-1], cursor, field)
			after_rule = bool(field.get("rule_after"))

	_parameters_block(ctx, pages, cursor, after_rule)
	return pages


def _parameters(ctx):
	"""The Report Parameters block, three to a line, as the legacy page closes."""
	f = ctx.filters

	def listed(values, limit=3):
		values = [v for v in values if v]
		if not values:
			return "All"
		return ", ".join(values[:limit]) + ("…" if len(values) > limit else "")

	chosen_warehouses = gsl._as_list(f.get("warehouse"))
	party = ctx.customer or ctx.supplier
	return [
		[
			("Date Range", "From {0} To {1}".format(gsl._miti(ctx.from_date).replace("-", "/"), gsl._miti(ctx.to_date).replace("-", "/"))),
			("Item", ctx.item.name),
			("Group By", ctx.group_by),
		],
		[
			("Quantity In", _unit_label(ctx)),
			("Warehouses", listed(chosen_warehouses) if chosen_warehouses else "All (one stock)"),
			("Movement", f.get("voucher_category") or "All"),
		],
		[
			("Party", party or "All"),
			("Refinery", ctx.refinery or "All"),
			("Branch", ctx.branch or "All"),
		],
		[
			("Show Value", "Yes" if ctx.show_value else "No"),
			("Cylinder Detail", "Yes" if ctx.show_cylinders else "No"),
			# its own slot: inside Date Range it would run into the next column
			("Month", gsl.period_label(ctx.from_date, ctx.to_date) or "-"),
		],
		[("Narration", "Yes" if ctx.show_narration else "No"), None, None],
	]


def _parameters_block(ctx, pages, cursor, after_rule):
	"""Report Parameters under the last rule, on a new page if it will not fit."""
	pt, at = glpd._pt, glpd._set_y
	params = _parameters(ctx)
	height = (0 if after_rule else 4.6) + 13.0 + 12.2 * (len(params) - 1) + 11.9
	if cursor + height > glpd.PRINT_BODY_BOTTOM + glpd.PRINT_PITCH:
		pages.append([])
		cursor = glpd.PRINT_BODY_TOP
		after_rule = True
	if not after_rule:
		pages[-1].append({"kind": "rule", "y": cursor - 1.25, "w": 0.75, "colour": "#000"})
		cursor += 3.35
	pages[-1].append(at(pt(X.code, "Report Parameters", size=8.5, bold=True), cursor))
	for row, line in enumerate(params):
		y = cursor + 13.0 + 12.2 * row
		for column, cell in enumerate(line):
			if not cell:
				continue
			label = "{0} : ".format(cell[0])
			x = X.params[column]
			pages[-1].append(at(pt(x, label, size=8.5), y))
			pages[-1].append(at(pt(x + glpd._text_pt(label, 8.5), cell[1], size=8.5, grey=True), y))
	pages[-1].append({"kind": "rule", "y": cursor + 13.0 + 12.2 * (len(params) - 1) + 11.9, "w": 0.75, "colour": "#000"})


# ---------------------------------------------------------------------------
# The standard print -- the same ledger, laid out for reading
# ---------------------------------------------------------------------------
#
# General Ledger Posting Detail's Standard print, for stock: the company, period
# (Nepali month named) and every filter on page one; a band per block; each
# movement with its miti over its AD date, its voucher over its type, and under
# the party what moved, the tanker details and the voucher's own narration; a
# running balance; "Carried forward" / "Brought forward" where a block crosses
# a page; and a summary closing the document. Same machinery as that print
# (glpd.STD, _std_place, Carlito widths), so the two read as one family.


def _std_info(ctx, filters):
	"""Everything the frame says, worked out once."""
	fy = frappe.db.sql(
		"""SELECT name FROM `tabFiscal Year` WHERE %(d)s BETWEEN year_start_date AND year_end_date
		   ORDER BY year_start_date DESC LIMIT 1""",
		{"d": ctx.from_date},
	)
	fy = str((fy[0][0] if fy else "") or filters.get("fiscal_year") or "")
	parts = fy.split("/")
	if len(parts) == 2 and all(part.isdigit() and len(part) == 2 for part in parts):
		fy = "20{0}/{1}".format(*parts)

	def bs(date):
		return gsl._miti(date).replace("-", "/")

	def listed(values, limit=3):
		values = [v for v in values if v]
		if not values:
			return _("All")
		return ", ".join(values[:limit]) + ("…" if len(values) > limit else "")

	month = gsl.period_label(ctx.from_date, ctx.to_date)
	chosen = gsl._as_list(filters.get("warehouse"))
	pairs = [
		(_("Item"), "{0}  {1}".format(ctx.item.name, ctx.item.item_name or "")),
		(_("Group by"), ctx.group_by),
		(_("Quantity in"), _unit_label(ctx)),
		(_("Warehouses"), listed(chosen) if chosen else _("All, as one stock")),
		(_("Movement"), filters.get("voucher_category") or _("All")),
		(_("Party"), ctx.customer or ctx.supplier or _("All")),
		(_("Refinery"), ctx.refinery or _("All")),
		(_("Branch"), ctx.branch or _("All")),
		(_("Narration"), _("Shown") if ctx.show_narration else _("Hidden")),
	]
	now = frappe.utils.now_datetime()
	notes = [_("Balance runs across every movement of the stock; the filters choose only which rows are listed.")]
	if ctx.show_value:
		notes.append(_("Values are at the moving-average cost of the pooled stock."))
	return frappe._dict(
		company=ctx.company,
		left="   ·   ".join(
			p for p in (_("Fiscal Year {0}").format(fy) if fy else "", _("Quantity in {0}").format(_unit_label(ctx)),
			            _("Amounts in NPR") if ctx.show_value else "") if p
		),
		period="{0}{1} – {2} BS   ·   {3} – {4} AD".format(
			"{0}   ·   ".format(month) if month else "", bs(ctx.from_date), bs(ctx.to_date), ctx.from_date, ctx.to_date
		),
		printed=_("Printed {0} {1} by {2}").format(bs(now.date()), now.strftime("%H:%M"), frappe.utils.get_fullname(frappe.session.user)),
		filters=[pairs[i : i + 3] for i in range(0, len(pairs), 3)],
		note=" ".join(notes),
		as_at_open=bs(ctx.from_date),
		as_at_close=bs(ctx.to_date),
	)


def _std_frame(ctx, info, page_no, total_pages):
	"""Masthead, the first page's filters, the column heads and the foot."""
	S, pt, at = glpd.STD, glpd._pt, glpd._set_y
	u = ctx.unit
	items = [
		at(pt(S.left, info.company, size=12.5, bold=True, colour=S.ink), 28.0),
		at(pt(S.right, _("Gas Stock Ledger"), size=15.0, bold=True, align="r", colour=S.ink), 26.5),
		at(pt(S.left, info.left, size=7.5, colour=S.muted), 47.0),
		at(pt(S.right, info.period, size=7.5, align="r", colour=S.muted), 47.0),
		{"kind": "rule", "x": S.left, "width": S.right - S.left, "y": 59.0, "w": 1.0, "colour": S.accent},
	]
	head_y = 66.0
	if page_no == 1:
		column_w = (S.right - S.left) / 3.0
		for row, pairs in enumerate(info.filters):
			y = 66.0 + 10.0 * row
			for column, (label, value) in enumerate(pairs):
				x = S.left + column * column_w
				items.append(at(pt(x, label, size=7.0, colour=S.muted), y))
				items.append(at(pt(x + 58.0, value, size=glpd._fit(value, column_w - 62.0, 7.0), colour=S.ink), y))
		items.append(at(pt(S.left, info.note, size=glpd._fit(info.note, S.right - S.left, 6.8), italic=True, colour=S.faint), 98.0))
		head_y = 112.0
	items.append({"kind": "fill", "x": S.left, "w": S.right - S.left, "top": head_y, "h": 16.0, "colour": S.band})
	for x, label, align in (
		(S.date, _("Miti / Date"), "l"),
		(S.voucher, _("Voucher"), "l"),
		(S.text, _("Particulars"), "l"),
		(S.debit, _flow_label(ctx, _("In")), "r"),
		(S.credit, _flow_label(ctx, _("Out")), "r"),
		(S.balance, _("Balance ({0})").format(u), "r"),
	):
		items.append(at(pt(x, label, size=glpd._fit(label, 64.0, 7.5, True), bold=True, align=align, colour=S.ink), head_y + 4.25))
	items.append({"kind": "rule", "x": S.left, "width": S.right - S.left, "y": head_y + 16.0, "w": 0.6, "colour": S.faint})
	items.append({"kind": "rule", "x": S.left, "width": S.right - S.left, "y": 810.0, "w": 0.4, "colour": S.hair})
	items.append(at(pt(S.left, info.printed, size=6.5, colour=S.muted), 815.0))
	items.append(at(pt(S.right, _("Page {0} of {1}").format(page_no, total_pages), size=6.5, bold=True, align="r", colour=S.muted), 815.0))
	return items


STD_FIRST_BODY_TOP = 134.0  # under the filters and the column heads on page one
NEGATIVE = "#b91c1c"


def _std_pages(ctx, sections, info):
	"""The standard print, cut into pages of placed items."""
	from avinashgroup_app.avinash_group_app.report.custom_ledger.custom_ledger import _fmt_npr

	S, pt = glpd.STD, glpd._pt
	blocks = gsl._blocks(ctx, sections)
	opening, closing = gsl._pool_totals(sections)
	if not blocks and abs(opening.qty) < gsl.EPS:
		return []

	def qty_text(kg):
		return _fmt_qty(gsl._q(ctx, kg), ctx.precision)

	def amt(kg, x, bold=False, colour=None, move=None):
		text = qty_text(kg)
		if ctx.txn_uom:
			# a movement in its own UOM; a total (or a mixed voucher) says MT
			text = gsl._txn_text(ctx, move) if move is not None and move.txn else _flow_text(ctx, text)
		if not text:
			return None
		return pt(x, text, size=glpd._fit(text, S.amount_w, 8.0, bold), bold=bold, align="r", colour=colour or S.ink)

	def bal(kg, bold=False, colour=None, size=8.0):
		text = qty_text(kg) or "{0:.{1}f}".format(0, ctx.precision)
		colour = colour or (NEGATIVE if flt(gsl._q(ctx, kg), ctx.precision) < 0 else S.ink)
		return pt(S.balance, text, size=glpd._fit(text, S.balance_w, size, bold), bold=bold, align="r", colour=colour)

	def runs(*items):
		return [item for item in items if item]

	def labelled(label, note, size=8.0, bold=True, colour=None):
		out = [pt(S.text, label, size=size, bold=bold, colour=colour or S.ink)]
		if note:
			out.append(pt(S.text + glpd._text_pt(label + "   ", size, bold), note, size=7.0, colour=S.muted))
		return out

	def value_note(b):
		if not ctx.show_value:
			return ""
		text = _("value {0}").format(_fmt_npr(b.value) or "0.00")
		if b.rate:
			text += _(" @ {0} / {1}").format(_fmt_npr(gsl._r(ctx, b.rate)), ctx.unit)
		return text

	def item_band(cont=False):
		return {
			"h": 16.0,
			"fill": S.band,
			"runs": [
				pt(S.left + 6.0, "{0}   {1}".format(ctx.item.name, ctx.item.item_name or ""), size=9.0, bold=True, colour=S.ink),
				pt(S.right - 6.0, _("continued") if cont else _("Item"), size=7.0, italic=cont, align="r", colour=S.muted),
			],
		}

	def sub_band(block, cont=False):
		label = "{0}   {1}".format(block.code, block.desc).strip() if block.code else block.desc
		return {
			"h": 14.0,
			"fill": S.subband,
			"runs": [
				pt(S.left + 14.0, label, size=8.5, bold=True, colour=S.ink),
				pt(S.right - 6.0, _("continued") if cont else _(ctx.group_by), size=7.0, italic=cont, align="r", colour=S.muted),
			],
		}

	def balance_line(label, b, as_at, closing=False):
		note = _("as at {0}").format(as_at)
		extra = value_note(b)
		return {
			"h": 14.0,
			"runs": labelled(label, "{0}{1}".format(note, "   ·   " + extra if extra else "")) + [bal(b.qty, bold=True)],
			"rule_bottom": (S.accent, 0.9) if closing else (S.hair, 0.4),
		}

	def total_line(in_kg, out_kg, final=False):
		net = in_kg - out_kg
		side = _("net in") if net > 0 else _("net out") if net < 0 else _("no net change")
		return {
			"h": 13.0,
			"runs": labelled(_("Total for the period"), "{0} {1}".format(qty_text(abs(net)), side).strip() if qty_text(net) else side)
			+ runs(amt(in_kg, S.debit, bold=True), amt(out_kg, S.credit, bold=True)),
			"rule_top": (S.faint, 0.6),
			"rule_bottom": (S.accent, 0.9) if final else None,
		}

	def cylinders(move):
		parts = []
		for key, count in sorted(move.cylinders.items(), key=lambda kv: ctx.sizes.get(kv[0], ("", 0))[1]):
			shown = _fmt_qty(count, 3 if key in ("bulk", "loose") else 0)
			if shown:
				parts.append("{0} × {1}".format(ctx.sizes.get(key, (key, 0))[0], shown))
		return ", ".join(parts)

	def movement_lines(move, running):
		english, _nepali = gsl.CATEGORIES[move.category]
		detail = [english]
		if ctx.show_cylinders and set(move.cylinders) - {"bulk", "loose"} and not (ctx.txn_uom and move.txn):
			detail.append(cylinders(move))
		if ctx.show_value and abs(move.value) >= 0.005:
			detail.append("{0} {1}".format(_("value") if move.qty > 0 else _("cost"), _fmt_npr(abs(move.value))))
		facts = []
		if move.refinery:
			facts.append(_("Refinery {0}").format(move.refinery))
		if move.reference:
			facts.append(move.reference)
		if move.vehicle:
			facts.append(_("Vehicle {0}").format(move.vehicle))

		by_party = ctx.group_by == gsl.GROUP_PARTY and (move.party or move.party_id)
		stream = []
		if not by_party:
			stream += [(line, 8.0, False, S.ink) for line in glpd._wrap_pt(move.party or english, S.text_w, 8.0)]
		stream += [(line, 7.2, False, S.muted) for line in glpd._wrap_pt(" · ".join(detail), S.text_w, 7.2)]
		if facts:
			stream += [(line, 7.2, False, S.muted) for line in glpd._wrap_pt(" · ".join(facts), S.text_w, 7.2)]
		if move.narration:
			stream += [(line, 7.2, True, S.muted) for line in _capped(glpd._wrap_pt(move.narration, S.text_w, 7.2))]
		if move.remarks:
			stream += [(line, 7.0, False, "#b45309") for line in glpd._wrap_pt("; ".join(move.remarks), S.text_w, 7.0)]

		voucher = move.number or move.voucher_no or ""
		out = []
		for index in range(max(len(stream), 2)):
			line_runs = []
			if index == 0:
				line_runs += runs(
					pt(S.date, gsl._miti(move.posting_date).replace("-", "/"), size=8.0, colour=S.ink),
					pt(S.voucher, voucher, size=glpd._fit(voucher, S.voucher_w, 8.0), colour=S.ink),
					amt(move.qty, S.debit, move=move) if move.qty > 0 else amt(-move.qty, S.credit, move=move),
					bal(move.balance_qty) if running else None,
				)
			elif index == 1:
				line_runs += runs(
					pt(S.date, str(move.posting_date), size=6.8, colour=S.faint),
					pt(S.voucher, move.voucher_type, size=glpd._fit(move.voucher_type, S.voucher_w, 6.8), colour=S.faint),
				)
			if index < len(stream):
				text, size, italic, colour = stream[index]
				line_runs.append(pt(S.text, text, size=size, italic=italic, colour=colour))
			out.append({"h": glpd.STD_LINE if index == 0 else glpd.STD_SUBLINE, "runs": line_runs})
		out[-1]["h"] += glpd.STD_GAP
		out[-1]["rule_bottom"] = (S.hair, 0.4)
		return out

	def forward(label, kg):
		return {"h": glpd.STD_CF, "runs": [pt(S.text, label, size=7.2, italic=True, colour=S.muted), bal(kg, colour=S.muted, size=7.6)]}

	units = []
	grand_in = grand_out = 0.0
	vouchers = set()
	counts = {key: 0 for key in gsl.CATEGORIES}
	for index, block in enumerate(blocks):
		bands = ([item_band()] if index == 0 else []) + ([sub_band(block)] if block.sub else [])
		context = [item_band(True)] + ([sub_band(block, True)] if block.sub else [])
		head = list(bands)
		if block.running:
			head.append(balance_line(_("Opening balance"), block.opening, info.as_at_open))
		in_kg = out_kg = 0.0
		brought = block.opening.qty if block.running else None
		for position, move in enumerate(block.moves):
			lines = movement_lines(move, block.running)
			if position == 0:
				# the heading and opening travel with the first movement
				units.append({"lines": head + lines, "head": True})
			else:
				units.append({"lines": lines, "ctx": context, "bf": brought, "head": False})
			if block.running:
				brought = move.balance_qty
			if move.qty > 0:
				in_kg += move.qty
			else:
				out_kg -= move.qty
			vouchers.add((move.voucher_type, move.voucher_no))
			counts[move.category] += 1
		if not block.moves:
			units.append({"lines": head, "head": True})
		tail = [total_line(in_kg, out_kg, final=not block.running)]
		if block.running:
			tail.append(balance_line(_("Closing balance"), block.closing, info.as_at_close, closing=True))
		units.append({"lines": tail, "ctx": context, "bf": brought, "head": False})
		grand_in += in_kg
		grand_out += out_kg

	if not blocks:
		units.append({"lines": [item_band()], "head": True})
	if ctx.group_by not in gsl.RUNNING_GROUPS or len(blocks) != 1:
		units.append(
			{
				"lines": [
					{"h": 6.0, "runs": []},
					{"h": 15.0, "fill": S.band, "runs": [pt(S.left + 6.0, _("Stock, all movements"), size=9.0, bold=True, colour=S.ink)]},
					balance_line(_("Opening balance"), opening, info.as_at_open),
					balance_line(_("Closing balance"), closing, info.as_at_close, closing=True),
				],
				"head": True,
			}
		)

	# the summary that closes the document
	width = (S.right - S.left) / 4.0
	boxes = [
		(_("Opening"), bal(opening.qty)["text"]),
		(_("Received"), qty_text(grand_in) or "0"),
		(_("Issued"), qty_text(grand_out) or "0"),
		(_("Closing"), bal(closing.qty)["text"]),
	]
	labels, values = [], []
	for column, (label, text) in enumerate(boxes):
		x = S.left + column * width + 8.0
		labels.append(pt(x, "{0} ({1})".format(label, ctx.unit).upper(), size=6.5, bold=True, colour=S.muted))
		values.append(pt(x, text, size=glpd._fit(text, width - 16.0, 11.0, True), bold=True, colour=S.ink))

	def counted(n, one, many):
		return "{0} {1}".format(n, one if n == 1 else many)

	facts = [
		counted(len(vouchers), _("voucher"), _("vouchers")),
		counted(counts["purchase"], _("purchase"), _("purchases")),
		counted(counts["sale"], _("sale"), _("sales")),
	]
	if counts["sale_return"] or counts["purchase_return"]:
		facts.append(counted(counts["sale_return"] + counts["purchase_return"], _("return"), _("returns")))
	if ctx.show_value:
		facts.append(_("closing value {0}").format(_fmt_npr(closing.value) or "0.00"))
	units.append(
		{
			"lines": [
				{"h": 10.0, "runs": []},
				{"h": 16.0, "runs": [pt(S.left, _("Summary"), size=9.0, bold=True, colour=S.ink)], "rule_bottom": (S.accent, 0.9)},
				{"h": 16.0, "fill": S.subband, "runs": labels},
				{"h": 20.0, "fill": S.subband, "runs": values, "rule_bottom": (S.hair, 0.4)},
				{"h": 14.0, "runs": [pt(S.left, "   ·   ".join(facts), size=7.2, colour=S.muted)]},
			],
			"head": True,
		}
	)

	pages = [[]]
	y = STD_FIRST_BODY_TOP
	for unit in units:
		need = sum(line["h"] for line in unit["lines"])
		mid = not unit["head"] and unit.get("ctx")
		carry = mid and unit.get("bf") is not None
		room = S.body_bottom - (glpd.STD_CF if carry else 0.0)
		top = STD_FIRST_BODY_TOP if len(pages) == 1 else S.body_top
		if y + need > room and y > top + 0.5:
			if carry:
				y = glpd._std_place(pages[-1], y, forward(_("Carried forward"), unit["bf"]))
			pages.append([])
			y = S.body_top
			if mid:
				for line in unit["ctx"]:
					y = glpd._std_place(pages[-1], y, line)
				if carry:
					y = glpd._std_place(pages[-1], y, forward(_("Brought forward"), unit["bf"]))
		for line in unit["lines"]:
			y = glpd._std_place(pages[-1], y, line)
	return pages


STYLES = ("standard", "legacy")


def build_html(filters, style="standard"):
	"""The print as HTML, and the context it was built from (tests read both)."""
	filters = frappe._dict(json.loads(filters) if isinstance(filters, str) else filters or {})
	# The print is the Detail ledger whatever view is on screen.
	filters.view = gsl.VIEW_DETAIL
	ctx = gsl._context(filters)
	sections = gsl._build_sections(ctx)
	gsl._enrich(ctx, sections)

	if style == "legacy":
		pages = _pages(ctx, sections)
		head = glpd._print_masthead(frappe._dict(company=ctx.company, from_date=ctx.from_date, to_date=ctx.to_date, fiscal_year=filters.get("fiscal_year")))
		head.month = gsl.period_label(ctx.from_date, ctx.to_date)

		def frame(index, total):
			return _frame(ctx, head, index + 1, total)

	else:
		info = _std_info(ctx, filters)
		pages = _std_pages(ctx, sections, info)

		def frame(index, total):
			return _std_frame(ctx, info, index + 1, total)

	if not pages:
		frappe.throw(_("Nothing to print for these filters."))
	sheets = [frame(index, len(pages)) + body for index, body in enumerate(pages)]
	metrics = glpd._carlito()
	template_path = os.path.join(os.path.dirname(glpd.__file__), "general_ledger_posting_detail_pdf.html")
	with open(template_path) as handle:
		template = handle.read()
	html = frappe.render_template(
		template,
		{
			"sheets": sheets,
			"page_w": glpd.PRINT_PAGE_W,
			"page_h": glpd.PRINT_PAGE_H,
			"grey": glpd.PRINT_GREY_TEXT,
			"font_regular": metrics["font_regular"],
			"font_bold": metrics["font_bold"],
		},
	)
	return html, ctx, len(pages)


@frappe.whitelist()
def download_pdf(filters, style="standard"):
	"""The Gas Stock Ledger as a PDF, A4 portrait: "standard" (for reading) or
	"legacy" (the old Posting Detail page)."""
	from frappe.utils.pdf import get_pdf

	from avinashgroup_app.custom_code.printing.chrome_pdf import render as chrome_render

	if not frappe.get_doc("Report", REPORT).is_permitted():
		frappe.throw(_("You are not permitted to print {0}").format(REPORT), frappe.PermissionError)
	if style not in STYLES:
		style = "standard"

	html, ctx, _pages_count = build_html(filters, style)
	# Chrome first, as General Ledger Posting Detail renders; get_pdf is the
	# fallback for a bench without Chrome.
	pdf = chrome_render(html=html, pdf_generator="chrome")
	if not pdf:
		pdf = get_pdf(
			html,
			{
				"page-size": "A4",
				"orientation": "Portrait",
				"margin-top": "0mm",
				"margin-bottom": "0mm",
				"margin-left": "0mm",
				"margin-right": "0mm",
			},
		)

	frappe.local.response.filename = "Gas Stock Ledger - {0}.pdf".format(ctx.company)
	frappe.local.response.filecontent = pdf
	frappe.local.response.type = "download"
