# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

"""Coordinate source for the A5 data-only overlays (one per pre-printed form).

Every pre-printed sprocket form already has a calibrated coordinate map living
in its raw-ESC/P generator (escp_*.py). Rather than re-measure or hand-copy
those into the HTML overlay (which would drift), the overlay pulls them from
here, and here re-uses the ESC/P module's own POS dict. One source of truth.

The ESC/P POS positions are true millimetres: x from the paper's left edge,
y from the top (perforation). That is exactly what the HTML overlay needs, so
the only work is reshaping tuples into the small nested dict the template reads,
carrying each form's own anchoring convention across (COPY_LABEL_ANCHOR, which
the form module declares beside the coordinate), and — on the A5 page only —
clamping the right-hand columns to 210mm.
"""

import frappe

# form key -> escp module name. The key is what a print format passes as `form`.
_FORMS = {
	"ngi": "escp_invoice",
	"ngi_udyog": "escp_ngi_udyog",
	"gandaki": "escp_gandaki",
	"karnali": "escp_karnali",
	"narayani": "escp_narayani",
	"grishma": "escp_grishma",
	"avinash": "escp_avinash_slip",
}

# A5 is 210mm wide. The LQ-310 head reaches ~210mm, and the ESC/P maps already
# clamp the amount there, but we pull it 3mm further in for a print-edge margin.
AMT_RIGHT = 207.0
# Dates are right-aligned to this edge so they never run past A5, whatever x the
# form's date box sits at (Gandaki/Narayani/Grishma put it at 198mm, past 210 if
# left-aligned).
DATE_RIGHT = 205.0

# Both clamps above exist ONLY to squeeze the right-hand columns inside A5's
# 210mm. On the real 241.3mm form they are wrong: they drag the dates ~11mm and
# the amounts 3mm inboard of the boxes the ESC/P map was calibrated against.
# Until 2026-07-25 they were applied on every page, contradicting the overlay
# template's own promise that the form page clamps nothing. `page` selects.
#
# NOTE those two are the only numbers in this file, and they are properties of
# the A5 PAGE, not of any form. Nothing here describes a form: every per-form
# fact — its coordinates AND how to read them — belongs in that form's own
# escp_*.py, next to the measurement. This module only reshapes.


def _form_module(form: str):
	name = _FORMS.get(form)
	if not name:
		frappe.throw(f"Unknown overlay form '{form}'. Known: {', '.join(_FORMS)}")
	return frappe.get_module(f"avinashgroup_app.custom_code.printing.{name}")


def _copy_label_anchor(mod, form: str) -> str:
	"""How to read POS["copy_label"] x for this form: "center" (the builder
	centres the label on it) or "left" (the x is where the text starts).

	Declared by the form module as COPY_LABEL_ANCHOR, beside the coordinate it
	describes. Deliberately NOT defaulted: this convention differs per form, and
	assuming one here is the exact bug found 2026-07-25 — every form's x was
	taken as a centre, so the forms that mean "left" printed their title about
	half a label width off. A new form must state which it is.
	"""
	anchor = getattr(mod, "COPY_LABEL_ANCHOR", None)
	if anchor not in ("left", "center"):
		frappe.throw(
			f"{mod.__name__} must declare COPY_LABEL_ANCHOR = 'left' or 'center' "
			f"(overlay form '{form}'). It says whether POS['copy_label'] x is the "
			f"left edge of the label or its centre; guessing prints the title "
			f"half a label width off."
		)
	return anchor


def overlay_pos(form: str = "ngi", page: str = "form") -> dict:
	"""Return the overlay coordinate map for one pre-printed form.

	Shaped for nepal_gas_invoice_a5_overlay.html. Reads the ESC/P POS dict so it
	always tracks the calibrated source; missing optional keys (e.g. Avinash has
	no D/O number) come back as None and the template skips them.

	`page` is the overlay's page mode: "form" (241.3mm, the real pre-printed
	sprocket form) or "a5" (210mm plain-paper fallback). It only selects whether
	the A5 width clamps apply — on the form, every column keeps the calibrated
	position from the ESC/P map. Defaults to "form" so a one-arg call is the
	real-form case.
	"""
	mod = _form_module(form)
	P = mod.POS
	is_a5 = page == "a5"

	def xy(key):
		v = P.get(key)
		return {"x": v[0], "y": v[1]} if v else None

	cl = P.get("copy_label")
	return {
		"copy_label": {
			"x": cl[0],
			"cx": cl[0],  # legacy alias — prefer x + align
			"y": cl[1],
			"align": _copy_label_anchor(mod, form),
		} if cl else None,
		"invoice_no": xy("invoice_no"),
		"ref_inv": xy("ref_inv"),
		"trans_date": xy("trans_date"),
		"invoice_date": xy("invoice_date"),
		"do_no": xy("do_no"),
		# date_r set => right-align the dates to it (A5). None => left-align each
		# date at its own calibrated x, which is what the ESC/P builders do.
		"date_r": DATE_RIGHT if is_a5 else None,
		"customer": xy("customer"),
		"address": xy("address"),
		"pan": xy("pan"),
		"body_top": P["body_top"][1],
		"row_h": P["row_h"],
		"words": {"x": P["words"][0], "y": P["words"][1], "w": 90},
		"c_sno": P["c_sno"],
		"c_hs": P.get("c_hs"),
		"c_part": P["c_part"],
		"r_qty": P["r_qty"],
		"r_rate": P["r_rate"],
		"amt_r": AMT_RIGHT if is_a5 else P["r_amt"],
		"y_disc": P["y_disc"],
		"y_taxable": P["y_taxable"],
		"y_vat": P["y_vat"],
		"y_grand": P["y_grand"],
	}
