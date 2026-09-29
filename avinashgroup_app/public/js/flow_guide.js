/*
 * Buying Flow Guide
 * -----------------
 * A sticky "what do I do now" panel for staff who are new to the job. It rides
 * along on every document of the purchase chain
 *
 *     Material Request -> Request for Quotation -> Supplier Quotation
 *     -> (comparison report) -> Purchase Order -> Purchase Receipt
 *     -> Purchase Invoice -> Payment Entry
 *
 * and answers three questions on the form the user is looking at: where this
 * paper sits in the chain, what to fill in right now, and which button makes
 * the next paper. The text is deliberately plain and short - it is read by
 * people doing the entry, not by accountants.
 *
 * Loaded globally through app_include_js and bound to the generic
 * `form-refresh` event, so no doctype_js entry and no per-doctype file is
 * needed; a doctype gets a guide the moment it is added to STEPS below.
 *
 * window.avinash.flow_guide.panel() is the reusable panel itself - the
 * Custom Supplier Quotation Comparison report draws its own help with it.
 */

(function () {
	window.avinash = window.avinash || {};
	if (window.avinash.flow_guide) return;

	const STORAGE_KEY = "avinash_flow_guide_open";

	// ---------------------------------------------------------------- panel

	function inject_style() {
		if ($("#avinash-flow-guide-style").length) return;
		$("head").append(`<style id="avinash-flow-guide-style">
			.av-guide {
				position: fixed; top: 110px; right: 16px; width: 330px; z-index: 5;
				max-height: calc(100vh - 140px); display: flex; flex-direction: column;
				background: var(--card-bg, #fff); color: var(--text-color, #1f272e);
				border: 1px solid var(--border-color, #d1d8dd);
				border-radius: var(--border-radius-md, 6px);
				box-shadow: var(--shadow-lg, 0 4px 16px rgba(0,0,0,.12)); font-size: 12px;
			}
			.av-guide .av-guide-head {
				display: flex; align-items: center; justify-content: space-between;
				padding: 8px 12px; font-weight: 600;
				border-bottom: 1px solid var(--border-color, #d1d8dd);
				background: var(--subtle-fg, #f4f5f6);
				border-radius: var(--border-radius-md, 6px) var(--border-radius-md, 6px) 0 0;
			}
			.av-guide .av-guide-close { cursor: pointer; font-size: 16px; line-height: 1; opacity: .6; }
			.av-guide .av-guide-close:hover { opacity: 1; }
			.av-guide .av-guide-body { overflow-y: auto; padding: 4px 12px 12px; }
			.av-guide .av-guide-title { font-weight: 600; margin: 10px 0 4px; }
			.av-guide ul { padding-left: 16px; margin: 0; }
			.av-guide li { margin-bottom: 4px; line-height: 1.5; }
			.av-guide-open-btn {
				position: fixed; bottom: 18px; right: 18px; z-index: 5; cursor: pointer;
				padding: 6px 12px; font-size: 12px; font-weight: 600;
				background: var(--card-bg, #fff); color: var(--text-color, #1f272e);
				border: 1px solid var(--border-color, #d1d8dd); border-radius: 20px;
				box-shadow: var(--shadow-base, 0 1px 4px rgba(0,0,0,.12));
			}
			.av-guide-open-btn:hover { background: var(--subtle-fg, #f4f5f6); }
			/* where-am-I chips */
			.av-guide-chips { display: flex; flex-wrap: wrap; gap: 4px; margin: 8px 0 2px; }
			.av-guide-chip {
				padding: 2px 7px; border-radius: 10px; font-size: 11px; white-space: nowrap;
				background: var(--subtle-fg, #f4f5f6); color: var(--text-muted, #8d99a6);
			}
			.av-guide-chip.done { color: var(--green-600, #38a160); }
			.av-guide-chip.now {
				background: var(--blue-100, #cce3f7); color: var(--blue-700, #1361a6); font-weight: 600;
			}
			.av-guide-note {
				margin-top: 10px; padding: 6px 8px; line-height: 1.5;
				background: var(--yellow-50, #fffbe6); color: var(--text-color, #1f272e);
				border-left: 3px solid var(--yellow-500, #f0b429);
				border-radius: 0 3px 3px 0;
			}
			@media (max-width: 1400px) {
				.av-guide { top: auto; bottom: 16px; right: 16px; width: 310px; max-height: 62vh; }
			}
			@media (max-width: 768px) {
				.av-guide { left: 12px; right: 12px; width: auto; }
			}
		</style>`);
	}

	function is_open() {
		try {
			return (localStorage.getItem(STORAGE_KEY) || "1") === "1";
		} catch (e) {
			return true; // storage blocked (private window) - just show it
		}
	}

	function set_open(open) {
		try {
			localStorage.setItem(STORAGE_KEY, open ? "1" : "0");
		} catch (e) {
			// ignore
		}
	}

	/**
	 * Draw the sticky panel inside `$wrapper` (a page wrapper, so the panel is
	 * hidden together with the page when the user routes away).
	 * Re-calling it on the same wrapper replaces the previous panel.
	 */
	function panel($wrapper, opts) {
		inject_style();
		$wrapper = $($wrapper);
		$wrapper.find(".av-guide, .av-guide-open-btn").remove();
		if (!opts || !opts.body) return;

		const $panel = $(`<div class="av-guide">
			<div class="av-guide-head">
				<span>${opts.title || __("Guide")}</span>
				<span class="av-guide-close" title="${__("Close")}">&times;</span>
			</div>
			<div class="av-guide-body">${opts.body}</div>
		</div>`).appendTo($wrapper);

		const $btn = $(
			`<div class="av-guide-open-btn">${opts.open_label || __("Help / Guide")}</div>`
		).appendTo($wrapper);

		const apply = (open) => {
			$panel.toggleClass("hidden", !open);
			$btn.toggleClass("hidden", open);
			set_open(open);
		};
		apply(is_open());

		$panel.find(".av-guide-close").on("click", () => apply(false));
		$btn.on("click", () => apply(true));

		return $panel;
	}

	// helpers for building the body
	const list = (title, items) =>
		items && items.length
			? `<div class="av-guide-title">${title}</div><ul>${items
					.map((t) => `<li>${t}</li>`)
					.join("")}</ul>`
			: "";
	const note = (text) => (text ? `<div class="av-guide-note">${text}</div>` : "");

	// ------------------------------------------------------------- the flow

	// One entry per stop on the purchase chain. `short` is what goes in the
	// chip row, `what` is the one-line "why does this paper exist".
	const STEPS = [
		{
			doctype: "Material Request",
			short: __("1. Request"),
			what: __("You write down what the office or plant needs."),
		},
		{
			doctype: "Request for Quotation",
			short: __("2. Ask price"),
			what: __("You ask two or three suppliers what they will charge."),
		},
		{
			doctype: "Supplier Quotation",
			short: __("3. Supplier price"),
			what: __("You enter the price each supplier gave you."),
		},
		{
			doctype: "__compare",
			short: __("4. Compare"),
			what: __("You compare the prices side by side and choose one supplier."),
		},
		{
			doctype: "Purchase Order",
			short: __("5. Order"),
			what: __("You order the goods from the supplier you chose."),
		},
		{
			doctype: "Purchase Receipt",
			short: __("6. Goods in"),
			what: __("You write down what actually came into the store."),
		},
		{
			doctype: "Purchase Invoice",
			short: __("7. Bill"),
			what: __("You enter the supplier's bill so we owe him the money."),
		},
		{
			doctype: "Payment Entry",
			short: __("8. Pay"),
			what: __("You pay the supplier and record it."),
		},
	];

	function chips(current_doctype) {
		const idx = STEPS.findIndex((s) => s.doctype === current_doctype);
		return `<div class="av-guide-chips">${STEPS.map((s, i) => {
			const cls = i < idx ? "done" : i === idx ? "now" : "";
			return `<span class="av-guide-chip ${cls}">${s.short}</span>`;
		}).join("")}</div>`;
	}

	// Per-doctype advice. `frm` lets each one look at the state of the paper in
	// front of the user, so a draft and a submitted document say different things.
	const ADVICE = {
		"Material Request": (frm) => {
			const purchase = frm.doc.material_request_type === "Purchase";
			if (frm.is_new()) {
				return {
					now: [
						__("Choose the <b>Company</b>."),
						__("<b>Purpose</b> = <b>Purchase</b> (this is what buying starts with)."),
						__("Put the <b>Required By</b> date."),
						__("Add the items - item code, quantity, warehouse."),
						__("Press <b>Save</b>."),
					],
					careful: __("Buying should always start from here. If you skip this paper, the comparison report stays empty later."),
				};
			}
			if (frm.doc.docstatus === 0) {
				return {
					now: [
						__("Read the item list once more - right item, right quantity?"),
						__("Press <b>Submit</b>. Nothing moves ahead until you submit."),
					],
				};
			}
			if (frm.doc.docstatus === 1 && purchase) {
				return {
					now: [
						__("Press <b>Create &gt; Request for Quotation</b> and pick two or three suppliers."),
						__("Already have the supplier prices on paper? Then press <b>Create &gt; Supplier Quotation</b> instead, one for each supplier."),
					],
				};
			}
			if (frm.doc.docstatus === 1) {
				return {
					now: [__("This request is not for buying, so there is no supplier step. Use <b>Create</b> to make the stock entry or transfer.")],
				};
			}
			return { now: [__("This request is cancelled. Make a new one - do not use this.")] };
		},

		"Request for Quotation": (frm) => {
			if (frm.is_new()) {
				return {
					now: [
						__("Better: make this from the submitted <b>Material Request</b> (<b>Create &gt; Request for Quotation</b>)."),
						__("Add the suppliers you want to ask."),
						__("Use <b>Get Items From &gt; Material Request</b> to pull the item list."),
						__("<b>Save</b>, then <b>Submit</b> - the supplier gets the mail."),
					],
				};
			}
			if (frm.doc.docstatus === 0) {
				return { now: [__("Check the supplier list and the items, then press <b>Submit</b>.")] };
			}
			if (frm.doc.docstatus === 1) {
				return {
					now: [
						__("Wait for the suppliers to answer with their price."),
						__("For each answer press <b>Create &gt; Supplier Quotation</b> - one quotation per supplier."),
					],
					careful: __("Make the quotation from here or from the Material Request. Made this way, the item rows keep the Material Request link, which the comparison needs."),
				};
			}
			return { now: [__("Cancelled. Make a fresh Request for Quotation from the Material Request.")] };
		},

		"Supplier Quotation": (frm) => {
			const linked = (frm.doc.items || []).some((r) => r.material_request);
			if (frm.is_new()) {
				return {
					now: [
						__("Choose the <b>Supplier</b> and the <b>Company</b>."),
						__("Press <b>Get Items From &gt; Material Request</b> and pick the request. <b>Do not type the items by hand.</b>"),
						__("Enter the <b>Rate</b> the supplier quoted, and VAT / Excise / TDS."),
						__("<b>Save</b>, then <b>Submit</b>."),
					],
					careful: __("Items typed by hand carry no Material Request link, and a quotation without that link <b>never shows up in the comparison report</b>."),
				};
			}
			if (frm.doc.docstatus === 0) {
				return {
					now: [
						__("Check the rate, the quantity and the tax figures against the supplier's paper."),
						__("Tick <b>Preferred Quotation</b> if this one should come in the comparison."),
						__("Press <b>Submit</b>."),
					],
					careful: !linked
						? __("<b>Warning:</b> no item row here points to a Material Request, so this quotation will not appear in the comparison report. Use <b>Get Items From &gt; Material Request</b>.")
						: "",
				};
			}
			if (frm.doc.docstatus === 1) {
				return {
					now: [
						__("Do the same for the other suppliers - one quotation each."),
						__("Then open the report <b>Custom Supplier Quotation Comparison</b> and compare the prices."),
						__("On the supplier you choose, press <b>Create &gt; Purchase Order</b>."),
					],
					careful: !frm.doc.custom_preferred_quotation
						? __("<b>Preferred Quotation</b> is not ticked here. The comparison report shows only ticked quotations unless that filter is switched off.")
						: "",
				};
			}
			return { now: [__("Cancelled. Ask the supplier again and enter a fresh quotation.")] };
		},

		"Purchase Order": (frm) => {
			const from_sq = (frm.doc.items || []).some((r) => r.supplier_quotation);
			if (frm.is_new()) {
				return {
					now: [
						__("Best way: open the supplier quotation you chose and press <b>Create &gt; Purchase Order</b>. Then everything is filled already."),
						__("Making it blank? Choose <b>Supplier</b>, <b>Company</b>, the <b>Required By</b> date, then the items with rate and quantity."),
						__("<b>Save</b>."),
					],
					careful: __("An order made blank, without a Material Request behind it, cannot be checked in the comparison report afterwards."),
				};
			}
			if (frm.doc.docstatus === 0) {
				return {
					now: [
						__("Check supplier, rate, quantity, tax and the delivery date."),
						__("Press <b>Submit</b>. If the order needs approval, it goes to the approver now - do not make a second one."),
					],
					careful: !from_sq
						? __("This order did not come from a supplier quotation. Compare the prices first if that was not already done.")
						: "",
				};
			}
			if (frm.doc.docstatus === 1) {
				return {
					now: [
						__("Send the order to the supplier."),
						__("When the goods arrive: <b>Create &gt; Purchase Receipt</b>."),
						__("When the supplier's bill arrives: <b>Create &gt; Purchase Invoice</b>."),
					],
					careful: __("Want to see the prices you compared for this order? Open <b>Custom Supplier Quotation Comparison</b> and put this order number in the <b>Purchase Order</b> filter."),
				};
			}
			return { now: [__("This order is cancelled. Do not send it to the supplier.")] };
		},

		"Purchase Receipt": (frm) => {
			if (frm.is_new()) {
				return {
					now: [
						__("Make this from the submitted <b>Purchase Order</b> (<b>Create &gt; Purchase Receipt</b>) so the items come by themselves."),
						__("Write the quantity that <b>really</b> came, not the ordered quantity."),
						__("Put the correct <b>Warehouse</b>."),
					],
					careful: __("Anything short or damaged goes in the <b>Rejected</b> quantity, not the accepted one."),
				};
			}
			if (frm.doc.docstatus === 0) {
				return {
					now: [
						__("Count once more against the supplier's challan."),
						__("Press <b>Submit</b>. Stock goes up only after submit."),
					],
				};
			}
			if (frm.doc.docstatus === 1) {
				return { now: [__("When the bill comes, press <b>Create &gt; Purchase Invoice</b>.")] };
			}
			return { now: [__("Cancelled - the stock has been taken back out.")] };
		},

		"Purchase Invoice": (frm) => {
			if (frm.is_new()) {
				return {
					now: [
						__("Make it from the <b>Purchase Receipt</b> or the <b>Purchase Order</b>, so the amount matches by itself."),
						__("Enter the supplier's <b>Bill No</b> and <b>Bill Date</b> exactly as printed."),
						__("Check VAT, Excise and TDS."),
					],
					careful: __("Do not type a bill twice. Search the supplier's bill number first."),
				};
			}
			if (frm.doc.docstatus === 0) {
				return {
					now: [
						__("Match the total with the supplier's bill, paisa to paisa."),
						__("Press <b>Submit</b>."),
					],
				};
			}
			if (frm.doc.docstatus === 1) {
				return { now: [__("When you pay, press <b>Create &gt; Payment</b> from this bill.")] };
			}
			return { now: [__("Cancelled. Check with accounts before entering it again.")] };
		},

		"Payment Entry": (frm) => {
			if (frm.is_new()) {
				return {
					now: [
						__("Best way: open the <b>Purchase Invoice</b> and press <b>Create &gt; Payment</b>, so it is set against that bill."),
						__("Choose the bank or cash account and the amount."),
						__("For a cheque, fill the cheque number and cheque date."),
					],
					careful: __("A payment made without picking the bill sits unadjusted in the supplier's account."),
				};
			}
			if (frm.doc.docstatus === 0) {
				return { now: [__("Check the amount and the bank account, then press <b>Submit</b>.")] };
			}
			if (frm.doc.docstatus === 1) {
				return { now: [__("Done. This purchase is finished.")] };
			}
			return { now: [__("Cancelled - the payment has been reversed.")] };
		},
	};

	function build_body(frm, step) {
		const advice = ADVICE[frm.doctype](frm) || {};
		return [
			chips(frm.doctype),
			`<div style="margin-top:6px;line-height:1.5">${step.what}</div>`,
			list(__("Do this now"), advice.now),
			note(advice.careful),
		].join("");
	}

	$(document).on("form-refresh", function (e, frm) {
		if (!frm || !ADVICE[frm.doctype] || !frm.page) return;
		const step = STEPS.find((s) => s.doctype === frm.doctype);
		panel($(frm.page.wrapper), {
			title: __("Step {0} - {1}", [STEPS.indexOf(step) + 1, __(frm.doctype)]),
			body: build_body(frm, step),
			open_label: __("Help / Guide"),
		});
	});

	window.avinash.flow_guide = { panel, chips, list, note, STEPS };
})();
