# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

"""Coordinate source for the A5 data-only overlays (one per pre-printed form).

Every pre-printed sprocket form already has a calibrated coordinate map living
in its raw-ESC/P generator (escp_*.py). Rather than re-measure or hand-copy
those into the HTML overlay (which would drift), the overlay pulls them from
here, and here re-uses the ESC/P module's own POS dict. One source of truth.

The ESC/P POS positions are true millimetres: x from the paper's left edge,
y from the top (perforation). That is exactly what the HTML overlay needs, so
the only work is reshaping tuples into the small nested dict the template reads
and clamping the two right-hand columns to A5's 210mm width.
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
# left-aligned). Tune per form later with oy/ox if a box needs it.
DATE_RIGHT = 205.0


def _pos_module(form: str):
	name = _FORMS.get(form)
	if not name:
		frappe.throw(f"Unknown overlay form '{form}'. Known: {', '.join(_FORMS)}")
	mod = frappe.get_module(f"avinashgroup_app.custom_code.printing.{name}")
	return mod.POS


def overlay_pos(form: str = "ngi") -> dict:
	"""Return the overlay coordinate map for one pre-printed form.

	Shaped for nepal_gas_invoice_a5_overlay.html. Reads the ESC/P POS dict so it
	always tracks the calibrated source; missing optional keys (e.g. Avinash has
	no D/O number) come back as None and the template skips them.
	"""
	P = _pos_module(form)

	def xy(key):
		v = P.get(key)
		return {"x": v[0], "y": v[1]} if v else None

	cl = P.get("copy_label")
	return {
		"copy_label": {"cx": cl[0], "y": cl[1]} if cl else None,
		"invoice_no": xy("invoice_no"),
		"ref_inv": xy("ref_inv"),
		"trans_date": {"y": P["trans_date"][1]},
		"invoice_date": {"y": P["invoice_date"][1]},
		"do_no": {"y": P["do_no"][1]} if P.get("do_no") else None,
		"date_r": DATE_RIGHT,
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
		"amt_r": AMT_RIGHT,
		"y_disc": P["y_disc"],
		"y_taxable": P["y_taxable"],
		"y_vat": P["y_vat"],
		"y_grand": P["y_grand"],
	}
