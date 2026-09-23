/**
 * Buying-side item amounts are CUT to 2 decimals, never rounded — browser half.
 *
 * The server does the real work (custom_code/common/purchase_amount_truncation.py,
 * see its docstring for the rule and its boundary). ERPNext's form recomputes
 * item amounts client-side with a normal round, so without this the form
 * previews 120.15700 x 1 as 120.16 and the saved doc then shows 120.15.
 *
 * erpnext.taxes_and_totals is the base class of every transaction form
 * controller, so the wrapper is scoped to the four buying doctypes and is a
 * no-op everywhere else (Sales Invoice keeps the normal round).
 */
(function () {
    const BUYING_DOCTYPES = new Set([
        "Purchase Invoice", "Purchase Order", "Purchase Receipt", "Supplier Quotation",
    ]);
    // Same as FLOAT_NOISE_PRECISION on the server: strips binary noise
    // (0.29 * 100 = 28.999999999999996) before cutting.
    const FLOAT_NOISE_PRECISION = 9;

    function truncate(value, precision) {
        const cleaned = flt(value, FLOAT_NOISE_PRECISION);
        const factor = Math.pow(10, precision);
        // Math.trunc cuts toward zero, so a return line mirrors its bill.
        return flt(Math.trunc(flt(cleaned * factor, FLOAT_NOISE_PRECISION - precision)) / factor, precision);
    }

    function patch() {
        const proto = erpnext.taxes_and_totals && erpnext.taxes_and_totals.prototype;
        if (!proto || proto._purchase_truncation_patched) return;
        const original = proto.calculate_item_values;

        proto.calculate_item_values = function () {
            original.apply(this, arguments);
            const doc = this.frm && this.frm.doc;
            if (!doc || !BUYING_DOCTYPES.has(doc.doctype) || this.discount_amount_applied) return;

            const conversion_rate = flt(doc.conversion_rate) || 1;
            for (const item of doc.items || []) {
                let qty = flt(item.qty);
                // Mirrors ERPNext's zero-qty credit/debit note cases.
                if (!qty && doc.is_return && doc.doctype !== "Purchase Receipt") qty = -1;
                else if (!qty && doc.is_debit_note) qty = 1;

                const amount = truncate(flt(item.rate) * qty, precision("amount", item));
                const base_amount = truncate(amount * conversion_rate, precision("base_amount", item));
                item.amount = item.net_amount = amount;
                item.base_amount = item.base_net_amount = base_amount;
            }
        };
        proto._purchase_truncation_patched = true;
    }

    patch();
})();
