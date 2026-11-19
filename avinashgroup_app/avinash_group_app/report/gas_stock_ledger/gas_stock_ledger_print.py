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
				"Quantity in {0}{1}".format(u, " · Amount in Nepalese Rupee ( NPR )" if ctx.show_value else ""),
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
		at(pt(X.qty_in, "In ({0})".format(u), bold=True, align="r"), 134.5),
		at(pt(X.qty_out, "Out ({0})".format(u), bold=True, align="r"), 134.5),
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
			runs.append(amount_run(X.qty_in, qty(in_kg)))
		if qty(out_kg):
			runs.append(amount_run(X.qty_out, qty(out_kg)))
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
		if ctx.show_cylinders and set(move.cylinders) - {"bulk", "loose"}:
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
		if move.qty > 0:
			first.append(amount_run(X.qty_in, qty(move.qty)))
		else:
			first.append(amount_run(X.qty_out, qty(-move.qty)))
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
			("Quantity In", ctx.unit),
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


def build_html(filters):
	"""The print as HTML, and the context it was built from (tests read both)."""
	filters = frappe._dict(json.loads(filters) if isinstance(filters, str) else filters or {})
	# The print is the Detail ledger whatever view is on screen.
	filters.view = gsl.VIEW_DETAIL
	ctx = gsl._context(filters)
	sections = gsl._build_sections(ctx)
	gsl._enrich(ctx, sections)
	pages = _pages(ctx, sections)
	if not pages:
		frappe.throw(_("Nothing to print for these filters."))

	head = glpd._print_masthead(frappe._dict(company=ctx.company, from_date=ctx.from_date, to_date=ctx.to_date, fiscal_year=filters.get("fiscal_year")))
	head.month = gsl.period_label(ctx.from_date, ctx.to_date)
	sheets = [_frame(ctx, head, index + 1, len(pages)) + body for index, body in enumerate(pages)]
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
def download_pdf(filters):
	"""The Gas Stock Ledger as the legacy Posting Detail page, A4 portrait."""
	from frappe.utils.pdf import get_pdf

	from avinashgroup_app.custom_code.printing.chrome_pdf import render as chrome_render

	if not frappe.get_doc("Report", REPORT).is_permitted():
		frappe.throw(_("You are not permitted to print {0}").format(REPORT), frappe.PermissionError)

	html, ctx, _pages_count = build_html(filters)

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
