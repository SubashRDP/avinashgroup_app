// Copyright (c) 2026, Avinash Group and contributors
// For license information, please see license.txt

/**
 * Quick date-range buttons — 7 Days / 15 Days / 1 Month — for the customer portal
 * report pages (Customer Statement, Product Wise Invoice Details, Sales Order
 * Analysis). Clicking one sets From = today minus the period and To = today.
 *
 * Portal-only on purpose. It used to be a desk-wide script in rdp_common_app, which
 * is shared with other clients; these buttons are this client's portal feature, so
 * they live here and each page mounts them in its own unlabelled slot, placed right
 * after the Customer filter.
 *
 * Each page owns its date fields and reload, so this file only draws the buttons
 * and works out the range; the page's `apply` callback writes the dates and reloads.
 * No frappe.datetime: website pages don't load it, so the date maths is done here.
 */
(function () {
	const PRESETS = [
		{ label: "7 Days", from: (today) => add_days(today, -7) },
		{ label: "15 Days", from: (today) => add_days(today, -15) },
		{ label: "1 Month", from: (today) => add_months(today, -1) },
	];

	// Dates are handled as YYYY-MM-DD strings, and the maths is done in UTC so a
	// daylight-saving shift in the viewer's timezone can never move a day.
	function parse(ymd) {
		const [y, m, d] = ymd.split("-").map(Number);
		return new Date(Date.UTC(y, m - 1, d));
	}

	function fmt(date) {
		return date.toISOString().slice(0, 10);
	}

	function add_days(ymd, n) {
		const d = parse(ymd);
		d.setUTCDate(d.getUTCDate() + n);
		return fmt(d);
	}

	// Same as the desk's frappe.datetime.add_months: a day past the end of the
	// target month clamps to its last day (31 Mar - 1 month = 28/29 Feb).
	function add_months(ymd, n) {
		const d = parse(ymd);
		const day = d.getUTCDate();
		d.setUTCDate(1);
		d.setUTCMonth(d.getUTCMonth() + n);
		const last = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + 1, 0)).getUTCDate();
		d.setUTCDate(Math.min(day, last));
		return fmt(d);
	}

	function local_today() {
		const now = new Date();
		return fmt(new Date(Date.UTC(now.getFullYear(), now.getMonth(), now.getDate())));
	}

	function add_styles() {
		if (document.getElementById("ag-quick-dates-style")) return;
		const style = document.createElement("style");
		style.id = "ag-quick-dates-style";
		style.textContent = `
			.ag-quick-dates { display: flex; flex-wrap: wrap; gap: 6px; }
			.ag-quick-dates .ag-quick-date-btn { font-weight: 600; white-space: nowrap; }
		`;
		document.head.appendChild(style);
	}

	/**
	 * Draw the buttons at the end of `$parent`.
	 *
	 *   today      YYYY-MM-DD from the server; the viewer's clock is only a fallback
	 *   apply      (from, to) => void — the page sets its From/To and reloads
	 *   get_range  () => {from, to} | null — the page's current dates, used to
	 *              highlight the matching button; null means "no date range in use"
	 *
	 * Returns { refresh() } for the page to call whenever its dates change, so the
	 * highlight follows a date typed or picked by hand too.
	 */
	function mount({ $parent, today, apply, get_range }) {
		add_styles();
		const $box = $('<div class="ag-quick-dates"></div>');
		const base_today = () => today || local_today();

		PRESETS.forEach((preset) => {
			$(`<button type="button" class="btn btn-default btn-sm ag-quick-date-btn"></button>`)
				.text(typeof __ === "function" ? __(preset.label) : preset.label)
				.on("click", () => {
					const t = base_today();
					apply(preset.from(t), t);
					refresh();
				})
				.appendTo($box);
		});

		$parent.append($box);

		function refresh() {
			const t = base_today();
			const range = get_range ? get_range() : null;
			$box.find(".ag-quick-date-btn").each(function (i) {
				const active = !!range && range.to === t && range.from === PRESETS[i].from(t);
				$(this).toggleClass("btn-primary", active).toggleClass("btn-default", !active);
			});
		}

		refresh();
		return { refresh };
	}

	window.ag_portal_quick_dates = { mount };
})();
