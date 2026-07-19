// Suppress ERPNext's informational negative-stock notifications in the desk UI.
//
// When a warehouse goes negative (e.g. an Update-Stock Sales Invoice with
// allow_negative_stock on), ERPNext core emits two *informational* messages
// that we never want the operators to see:
//
//   1. Blue popup  "Warning on Negative Stock"  -> stock_ledger.py:772
//        "The stock for the item ... was negative on the ... You should create
//         a positive entry ... to post the correct valuation rate."
//   2. Green toast "Item valuation reposting in progress. Report might show
//        incorrect item valuation."            -> stock/utils.py:555
//
// Both are server-side frappe.msgprint / show_alert calls; they are only
// *rendered* client-side, so wrapping the render functions and dropping the
// matching payload hides them without touching Python core. The document has
// already been saved/submitted by the time these arrive -- suppressing them
// changes nothing about the transaction, only what the user sees.
//
// NOTE: this does NOT touch the red blocking "Insufficient Stock" error. That
// is a server-side frappe.throw that rejects the submit before anything renders
// -- hiding it in JS would only make the submit fail silently. Allowing that
// case is controlled by `allow_negative_stock` in Stock Settings, not here.

(function () {
	// Distinctive fragments of the two informational messages. Matching the
	// message body (not just the translated title) keeps this working even if
	// the title is localised.
	const SUPPRESS_PATTERNS = [
		/warning on negative stock/i,
		/was negative on the/i,
		/to post the correct valuation rate/i,
		/item valuation reposting in progress/i,
		/report might show incorrect item valuation/i,
	];

	function text_of(payload) {
		if (payload == null) return "";
		if (typeof payload === "string") return payload;
		// msgprint data object / show_alert object
		const parts = [];
		if (payload.title) parts.push(String(payload.title));
		if (payload.message) parts.push(String(payload.message));
		if (payload.indicator && !payload.title && !payload.message) {
			parts.push(String(payload.indicator));
		}
		return parts.join(" ");
	}

	function should_suppress(payload) {
		const t = text_of(payload);
		if (!t) return false;
		return SUPPRESS_PATTERNS.some((re) => re.test(t));
	}

	function wrap(fn_name) {
		const original = frappe[fn_name];
		if (typeof original !== "function") return;
		if (original.__avinash_negstock_wrapped) return;

		const wrapped = function (msg, ...rest) {
			try {
				// msgprint accepts a plain object or a string; when a string
				// begins with "{" it is JSON -- normalise before matching.
				let candidate = msg;
				if (typeof msg === "string" && msg.trim().charAt(0) === "{") {
					try {
						candidate = JSON.parse(msg);
					} catch (e) {
						candidate = msg;
					}
				}
				if (should_suppress(candidate)) {
					return; // drop silently
				}
			} catch (e) {
				// never let the filter break normal messaging
			}
			return original.call(this, msg, ...rest);
		};
		wrapped.__avinash_negstock_wrapped = true;
		// preserve aliases (frappe.toast === frappe.show_alert)
		frappe[fn_name] = wrapped;
		return wrapped;
	}

	if (window.frappe) {
		const new_show_alert = wrap("show_alert");
		wrap("msgprint");
		// frappe.toast and window.msgprint are aliases set at load time; re-point
		// them at the wrapped versions so server messages routed through either
		// are filtered too.
		if (new_show_alert) {
			frappe.toast = frappe.show_alert;
		}
		if (frappe.msgprint) {
			window.msgprint = frappe.msgprint;
		}
	}
})();
