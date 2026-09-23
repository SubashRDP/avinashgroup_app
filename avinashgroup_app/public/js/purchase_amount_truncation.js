/**
 * Buying-side item amounts are CUT to 2 decimals, never rounded — browser half.
 *
 * The server does the real work (custom_code/common/purchase_amount_truncation.py,
 * see its docstring for the rule and its boundary). ERPNext's form recomputes
 * item amounts client-side with a normal round, so without this the form
 * previews 120.15700 x 1 as 120.16 and the saved doc then shows 120.15.
 *
 * erpnext.taxes_and_totals is the base class of every transaction form
 * controller, so both wrappers (item amounts, header-discount spread) are
 * scoped to the four buying doctypes and are a no-op everywhere else (Sales
 * Invoice keeps the normal round).
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

    // Shared with purchase_taxes_common.js (line VAT preview).
    frappe.provide("avinashgroup.purchase");
    avinashgroup.purchase.truncate = truncate;

    // Mirrors TruncatingTaxesAndTotals.apply_discount_amount on the server:
    // every row's share of a header discount is cut, the last row takes the
    // paisa left over so rows still foot to the discounted net total.
    function discount_spread_inputs(ctrl) {
        const doc = ctrl.frm.doc;
        const items = ctrl.frm._items || [];
        if (!flt(doc.discount_amount) || !items.length) return null;
        if (doc.apply_discount_on == "Grand Total" && doc.is_cash_or_non_trade_discount) return null;
        const total_for_discount = ctrl.get_total_for_discount_amount();
        if (!total_for_discount) return null;
        return {
            discount: flt(doc.discount_amount),
            total_for_discount,
            rows: items.map((item) => [item, flt(item.net_amount)]),
        };
    }

    function respread_discount(ctrl, spread) {
        const { discount, total_for_discount, rows } = spread;
        const target = rows.reduce((sum, [item]) => sum + flt(item.net_amount), 0);
        const cut = rows.map(([item, before]) =>
            truncate(before - discount * before / total_for_discount, precision("net_amount", item)));
        const last = rows[rows.length - 1][0];
        const others = cut.slice(0, -1).reduce((a, b) => a + b, 0);
        cut[cut.length - 1] = flt(target - others, precision("net_amount", last));
        if (rows.every(([item], i) => flt(item.net_amount) === cut[i])) return;

        const conversion_rate = flt(ctrl.frm.doc.conversion_rate) || 1;
        rows.forEach(([item], i) => {
            item.net_amount = cut[i];
            item.net_rate = item.qty ? flt(cut[i] / item.qty, precision("net_rate", item)) : 0;
            item.base_net_amount = truncate(cut[i] * conversion_rate, precision("base_net_amount", item));
            ctrl.set_in_company_currency(item, ["net_rate"]);
        });
        ctrl._calculate_taxes_and_totals();
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

        const original_discount = proto.apply_discount_amount;
        proto.apply_discount_amount = function () {
            const doc = this.frm && this.frm.doc;
            if (!doc || !BUYING_DOCTYPES.has(doc.doctype)) return original_discount.apply(this, arguments);
            const spread = discount_spread_inputs(this);
            const result = original_discount.apply(this, arguments);
            if (spread && this.discount_amount_applied) respread_discount(this, spread);
            return result;
        };
        proto._purchase_truncation_patched = true;
    }

    patch();
})();
