/**
 * Buying-side money lands on 2 decimals rounded HALF-UP — browser half.
 *
 * The rule and its boundary live in the server module's docstring
 * (custom_code/common/purchase_paisa_rounding.py). In short: rates keep 5
 * decimals; every amount (line amount, VAT / TDS / Excise, header-discount
 * shares) keeps 2, and a third decimal of 5 or more rounds up.
 *
 * This file provides:
 * - avinashgroup.purchase.round_half_up, used by purchase_taxes_common.js for
 *   the VAT and excise previews and by material_request.js;
 * - wrappers on erpnext.taxes_and_totals.calculate_item_values and
 *   .apply_discount_amount so the form previews the same line amounts and
 *   discount shares the server saves. The class is the base of every
 *   transaction form controller, so the wrappers are scoped to the four buying
 *   doctypes and are a no-op everywhere else.
 */
(function () {
    const BUYING_DOCTYPES = new Set([
        "Purchase Invoice", "Purchase Order", "Purchase Receipt", "Supplier Quotation",
    ]);
    // Same as FLOAT_NOISE_PRECISION on the server: strips binary noise
    // (24.025 * 5 = 120.12499999999999) before rounding.
    const FLOAT_NOISE_PRECISION = 9;

    function round_half_up(value, precision) {
        const cleaned = flt(value, FLOAT_NOISE_PRECISION);
        const factor = Math.pow(10, precision);
        // Round the magnitude so a tie goes away from zero on both signs
        // (Math.round alone would send -11.505 to -11.50).
        const scaled = flt(Math.abs(cleaned) * factor, FLOAT_NOISE_PRECISION - precision);
        return flt(Math.sign(cleaned) * Math.round(scaled) / factor, precision);
    }

    frappe.provide("avinashgroup.purchase");
    avinashgroup.purchase.round_half_up = round_half_up;

    // Mirrors HalfUpTaxesAndTotals.calculate_item_values on the server:
    // each line amount is rounded half-up instead of the site's Banker's Rounding.
    function reround_item_amounts(ctrl) {
        const doc = ctrl.frm.doc;
        const conversion_rate = flt(doc.conversion_rate) || 1;
        for (const item of doc.items || []) {
            let qty = flt(item.qty);
            // Mirrors ERPNext's zero-qty credit/debit note cases.
            if (!qty && (doc.is_return || doc.is_debit_note)) {
                qty = doc.is_debit_note ? 1 : -1;
                if (doc.doctype !== "Purchase Receipt" && doc.is_return === 1) qty = 0;
            }

            const amount = round_half_up(flt(item.rate) * qty, precision("amount", item));
            const base_amount = round_half_up(amount * conversion_rate, precision("base_amount", item));
            item.amount = item.net_amount = amount;
            item.base_amount = item.base_net_amount = base_amount;
        }
    }

    // Mirrors HalfUpTaxesAndTotals.apply_discount_amount on the server:
    // every row's share of a header discount is rounded half-up, the last row
    // takes the paisa left over so rows still foot to the discounted net total.
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
        const shares = rows.map(([item, before]) =>
            round_half_up(before - discount * before / total_for_discount, precision("net_amount", item)));
        const last = rows[rows.length - 1][0];
        const others = shares.slice(0, -1).reduce((a, b) => a + b, 0);
        shares[shares.length - 1] = flt(target - others, precision("net_amount", last));
        if (rows.every(([item], i) => flt(item.net_amount) === shares[i])) return;

        const conversion_rate = flt(ctrl.frm.doc.conversion_rate) || 1;
        rows.forEach(([item], i) => {
            item.net_amount = shares[i];
            item.net_rate = item.qty ? flt(shares[i] / item.qty, precision("net_rate", item)) : 0;
            item.base_net_amount = round_half_up(shares[i] * conversion_rate, precision("base_net_amount", item));
            ctrl.set_in_company_currency(item, ["net_rate"]);
        });
        ctrl._calculate_taxes_and_totals();
    }

    function patch() {
        const proto = erpnext.taxes_and_totals && erpnext.taxes_and_totals.prototype;
        if (!proto || proto._purchase_rounding_patched) return;

        const original_item_values = proto.calculate_item_values;
        proto.calculate_item_values = function () {
            const result = original_item_values.apply(this, arguments);
            const doc = this.frm && this.frm.doc;
            if (doc && BUYING_DOCTYPES.has(doc.doctype) && !this.discount_amount_applied) {
                reround_item_amounts(this);
            }
            return result;
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
        proto._purchase_rounding_patched = true;
    }

    patch();
})();
