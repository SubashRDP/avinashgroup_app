// Auto-fill custom_fiscal_year from the posting / transaction date.
//
// custom_fiscal_year feeds the Numbering Configuration "Group Document No. By"
// table (per-fiscal-year Document No. sequences). The numbering engine can
// derive the year from the date on its own, but the field is shown on the form
// — so keep it populated and in sync with the date the user picks.
//
// UI-only and graceful: doctypes without the field are skipped, a locked
// (post-numbering) field is left untouched, and imports/API still work because
// the engine falls back to the posting date when the field is blank.

const FY_DATE_DOCTYPES = ["Journal Entry", "Payment Entry", "Purchase Invoice", "Purchase Receipt"];
const _fy_by_date = {}; // memoize: date string -> fiscal year name (or null)

async function _resolve_fiscal_year(date) {
	if (!date) return null;
	if (date in _fy_by_date) return _fy_by_date[date];
	let fy = null;
	try {
		const rows = await frappe.db.get_list("Fiscal Year", {
			filters: [["year_start_date", "<=", date], ["year_end_date", ">=", date]],
			fields: ["name"],
			limit: 1,
		});
		fy = rows && rows.length ? rows[0].name : null;
	} catch (e) {
		fy = null; // no read access / lookup failed -> leave the field alone
	}
	_fy_by_date[date] = fy;
	return fy;
}

function _sync_fiscal_year(frm) {
	const f = frm.fields_dict && frm.fields_dict.custom_fiscal_year;
	if (!f) return; // field not on this doctype
	if (f.df && f.df.read_only) return; // locked after numbering -> don't touch
	const date = frm.doc.posting_date || frm.doc.transaction_date;
	if (!date) return;
	_resolve_fiscal_year(date).then((fy) => {
		// guard against a stale async result: only apply if the date is still
		// the one we looked up (rapid date changes could otherwise land an
		// earlier date's fiscal year on the field).
		const current = frm.doc.posting_date || frm.doc.transaction_date;
		if (fy && date === current && frm.doc.custom_fiscal_year !== fy) {
			frm.set_value("custom_fiscal_year", fy);
		}
	});
}

FY_DATE_DOCTYPES.forEach((dt) => {
	frappe.ui.form.on(dt, {
		posting_date(frm) { _sync_fiscal_year(frm); },
		transaction_date(frm) { _sync_fiscal_year(frm); },
		refresh(frm) {
			// populate on load for a new doc (posting_date defaults to today)
			if (frm.is_new() && !frm.doc.custom_fiscal_year) _sync_fiscal_year(frm);
		},
	});
});
