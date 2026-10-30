// Sales Invoice — show whether each row's rate is today's price.
//
// A row's rate is fetched once, when the item or UOM is picked, so a form left
// open across a price change (or an invoice from a Delivery Note, or an old
// draft) can carry yesterday's price without anything saying so. The server
// (custom_code/SalesInvoice/rate_check.py) compares every row with today's Item
// Price, and the answer is drawn in one line above the Items table.
//
// Only a check: it never changes a rate and never blocks a save. Drafts only.
//
// Loaded globally (app_include_js), not doctype_js, for the same reason as
// sales_invoice.js. Its own line, not the dashboard headline — that belongs to
// the credit banner.

const RATE_CHECK_METHOD = "avinashgroup_app.custom_code.SalesInvoice.rate_check.check_rates";

frappe.ui.form.on("Sales Invoice", {
    refresh: (frm) => queue_rate_check(frm),
    selling_price_list: (frm) => queue_rate_check(frm),
    posting_date: (frm) => queue_rate_check(frm),
    customer: (frm) => queue_rate_check(frm),
});

frappe.ui.form.on("Sales Invoice Item", {
    item_code: (frm) => queue_rate_check(frm),
    uom: (frm) => queue_rate_check(frm),
    rate: (frm) => queue_rate_check(frm),
    discount_percentage: (frm) => queue_rate_check(frm),
    items_remove: (frm) => queue_rate_check(frm),
});

// Picking an item fires item_code, uom and rate within a few hundred ms; wait
// for them to settle and ask the server once.
function queue_rate_check(frm) {
    clearTimeout(frm.__rate_check_timer);
    frm.__rate_check_timer = setTimeout(() => run_rate_check(frm), 500);
}

function run_rate_check(frm) {
    // Decoration only: nothing here may break the form's own handlers.
    try {
        if (frm.doc.docstatus !== 0 || frm.doc.is_return || !(frm.doc.items || []).length) {
            draw_rate_check(frm, null);
            return;
        }

        // Only the newest answer may paint; an older one landing late would
        // show rates the user has since changed.
        const seq = (frm.__rate_check_seq = (frm.__rate_check_seq || 0) + 1);
        frappe.call({
            method: RATE_CHECK_METHOD,
            args: { doc: frm.doc },
            callback: (r) => {
                if (seq !== frm.__rate_check_seq) return;
                draw_rate_check(frm, r.message || null);
            },
        });
    } catch (e) {
        console.error("Rate check failed", e);
    }
}

function rate_check_box(frm) {
    const $wrapper = frm.fields_dict.items && frm.fields_dict.items.$wrapper;
    if (!$wrapper) return null;
    let $box = $wrapper.find(".ag-rate-check");
    if (!$box.length) {
        $box = $('<div class="ag-rate-check" style="border-radius:4px;padding:6px 10px;margin-bottom:8px;font-size:.85rem;"></div>');
        $wrapper.prepend($box);
    }
    return $box;
}

// result null = nothing to show (submitted, return, no rows).
function draw_rate_check(frm, result) {
    try {
        const $box = rate_check_box(frm);
        if (!$box) return;
        if (!result || (!result.checked && !result.mismatched.length)) {
            $box.hide();
            return;
        }

        const money = (v) => format_currency(v, frm.doc.currency, 5);
        let html;
        if (result.mismatched.length) {
            const lines = result.mismatched.map((m) =>
                `Row ${m.idx} · ${frappe.utils.escape_html(m.item_name)} ${frappe.utils.escape_html(m.uom || "")}: ` +
                `rate <b>${money(m.rate)}</b>, today's price <b>${money(m.price)}</b>`
            );
            html = `⚠️ ${__("Rate is not today's price")}<br>${lines.join("<br>")}`;
            $box.css({ background: "var(--bg-orange)", color: "var(--text-on-orange)", "border-left": "4px solid var(--orange-500)" });
        } else {
            html = `✅ ${__("All rates match today's price list")}`;
            $box.css({ background: "var(--bg-green)", color: "var(--text-on-green)", "border-left": "4px solid var(--green-500)" });
        }
        $box.html(html).show();
    } catch (e) {
        console.error("Rate check failed to draw", e);
    }
}
