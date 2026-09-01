// List view columns sized to their content, the way Frappe v16 does it.
//
// v15 splits `.level-left` evenly between the columns, so a column whose
// values are long (Voucher No., Created By, invoice names) clips with an
// ellipsis while its neighbours sit half empty. Measured on this site's Sales
// Invoice list: 19 of 147 cells clipped, every one of them "Created By",
// which wanted 220px and was given 188px -- while Status next to it needed
// far less than its own 188px.
//
// v16 replaced the even split with per-column widths measured from the widest
// value actually on screen. This is that half of it, as a prototype patch on
// frappe.views.ListView so `bench update` cannot revert it. v16 also scrolls
// the list sideways once the columns stop fitting; that part is deliberately
// left out -- see the note on the flex rule below.
//
// Deliberately conservative:
//   * One hook, `after_render`. Nothing here rewrites the list's HTML, so
//     there is no copied markup to drift out of step with core.
//   * A list whose columns already fit is left completely alone -- the
//     stock even split still applies, no widths are set, nothing scrolls.
//   * Widths are only set when a column is genuinely being clipped, which is
//     the only case v15 handles badly.
//   * No new overflow container, so nothing that opens inside a list row can
//     be clipped by this.
//   * Any failure is caught and logged; a broken measurement must never take
//     the list view down with it.
//
// list_cleanup.css still owns the right-hand meta area (its 180px is the same
// figure v16 settled on) and is untouched by this file.

(() => {
	const FLAG = "_agx_list_widths_patched";

	// Breathing room added to a measured width, so text is not flush against
	// the next column's border.
	const PADDING_PX = 12;
	// A column never shrinks below this (a 2-character value still needs a
	// readable, clickable target) nor grows past it (one 300-character
	// Description must not push everything else off the row).
	const MIN_COL_PX = 60;
	const MAX_COL_PX = 400;

	const LV = frappe.views.ListView;
	if (!LV || LV.prototype[FLAG]) return;

	function opted_out(lv) {
		// Per doctype, either from List View Settings (matching the field v16
		// added there) or from a listview_settings override in an app.
		if (lv.list_view_settings && lv.list_view_settings.disable_scrolling) return true;
		const settings = (frappe.listview_settings || {})[lv.doctype] || {};
		return !!settings.disable_scrolling;
	}

	// The cells of one column, header row first. Returns null unless every row
	// agrees with the header on how many columns there are -- a doctype whose
	// listview_settings renders its own markup can disagree, and guessing at
	// that is how you corrupt someone else's layout.
	function column_groups(result) {
		const header = result.querySelector(".list-row-head .level-left");
		const rows = Array.from(
			result.querySelectorAll(".list-row-container .list-row .level-left")
		);
		if (!header || !rows.length) return null;

		const groups = [header, ...rows].map((r) =>
			Array.from(r.querySelectorAll(".list-row-col"))
		);
		const count = groups[0].length;
		if (!count || !groups.every((g) => g.length === count)) return null;
		return groups;
	}

	// `scrollWidth` can never report less than the element's own box, so it
	// cannot tell us a column wants LESS than the share it was given -- and
	// reclaiming that slack is the whole point. Measure under `max-content`
	// instead, which reports what the content actually wants in both
	// directions, then put the styles back exactly as they were.
	function measure_natural_widths(groups) {
		const count = groups[0].length;
		const saved = [];

		groups.forEach((g) =>
			g.forEach((cell) => {
				saved.push([cell, cell.style.cssText]);
				cell.style.width = "max-content";
				cell.style.maxWidth = "none";
				cell.style.flex = "0 0 auto";
			})
		);

		// one forced reflow, then read every cell
		const widths = new Array(count).fill(0);
		const hidden = new Array(count).fill(true);
		for (const g of groups) {
			for (let i = 0; i < count; i++) {
				const rect = g[i].getBoundingClientRect();
				if (rect.width > 0) hidden[i] = false;
				if (rect.width > widths[i]) widths[i] = rect.width;
			}
		}

		saved.forEach(([cell, css]) => {
			cell.style.cssText = css;
		});

		return { widths, hidden };
	}

	function size_columns(lv) {
		if (opted_out(lv)) return;
		if (frappe.is_mobile && frappe.is_mobile()) return;
		if (!lv.$result || !lv.$result.length) return;

		const groups = column_groups(lv.$result[0]);
		if (!groups) return;

		// Start from a clean slate: last render's widths would otherwise be
		// what we measure, and the columns would ratchet.
		groups.forEach((g) =>
			g.forEach((cell) => {
				cell.style.width = "";
				cell.style.flex = "";
			})
		);

		// What each column is getting under the stock even split, measured
		// before we disturb anything.
		const allotted = groups[0].map((_, i) =>
			Math.max(...groups.map((g) => g[i].getBoundingClientRect().width))
		);

		const { widths, hidden } = measure_natural_widths(groups);

		const wanted = widths.map((w, i) =>
			hidden[i] ? null : Math.min(Math.max(Math.ceil(w) + PADDING_PX, MIN_COL_PX), MAX_COL_PX)
		);
		if (!wanted.some((w) => w != null)) return;

		// Intervene only when a column is actually being clipped. Note this is
		// NOT the same as "the total does not fit": the even split can starve
		// one column while its neighbours sit half empty, and the total still
		// fits comfortably. That is the common case here -- Created By wanting
		// 220px out of an even 188px, inside a row with 300px to spare.
		const clipping = wanted.some((w, i) => w != null && w > allotted[i] + 1);
		if (!clipping) return;

		// If the columns cannot all have what they want, stand down and leave
		// the stock even split in place.
		//
		// This is the one case v16 answers by scrolling the list sideways, and
		// scrolling is deliberately not built here: it needs an overflow
		// container (which would clip anything opening inside a row), sticky
		// columns, and a second layout mode to keep working. Declining instead
		// makes the rule strictly safe -- a list is either improved or left
		// exactly as it is today, never made worse.
		//
		// Shrinking to fit is NOT a usable fallback: with a shrink factor the
		// columns shrink in proportion to their bases, so a column that needed
		// the extra room loses it again. Measured while trying it: clipping on
		// this site's Sales Invoice list went from 19 cells to 54.
		const available = groups[0][0].parentElement.getBoundingClientRect().width;
		const total = wanted.reduce((sum, w) => sum + (w || 0), 0);
		if (total > available) return;

		// Fits: each column's own content is its flex basis, and they grow
		// into whatever slack is left so the row still fills the width. A zero
		// shrink factor is safe here precisely because we know it fits.
		groups.forEach((g) =>
			wanted.forEach((w, i) => {
				if (w == null) return;
				g[i].style.flex = `1 0 ${w}px`;
			})
		);
	}

	const orig_after_render = LV.prototype.after_render;
	LV.prototype.after_render = function () {
		const out = orig_after_render ? orig_after_render.apply(this, arguments) : undefined;
		try {
			size_columns(this);
		} catch (e) {
			// A miscalculated width is a cosmetic problem; taking the list
			// view down over it is not.
			console.error("[avinash] list column sizing failed", e);
		}
		return out;
	};

	// Whether the columns fit depends on the viewport, so a resize has to be
	// re-judged -- otherwise pixel widths measured at one size are stranded at
	// another, which is worse than never having set them.
	$(window).on(
		"resize.agx_list_widths",
		frappe.utils.debounce(() => {
			const lv = frappe.get_route()[0] === "List" && cur_list;
			if (lv && lv.$result) {
				try {
					size_columns(lv);
				} catch (e) {
					console.error("[avinash] list column sizing failed on resize", e);
				}
			}
		}, 200)
	);

	LV.prototype[FLAG] = true;
})();
