// Exact record names from the "Payment - Receipt Type" master (same on all sites)
const P_TYPE_TO_PAYMENT_TYPE = {
	"Bank Customers Receipt": "Receive",
	"Vendor Receipt": "Receive",
	"Customers/Suppliers Receipt": "Receive",
	"NOC Payment": "Pay",
	"Vendor Payment": "Pay",
	"Contra Voucher- cash to bank": "Internal Transfer",
};

// Fill the party-side account (Paid From on Receive, Paid To on Pay) of a
// Customer/Supplier entry from the party's Accounts table:
//   no invoice tagged -> party's Advance Account (Default Account if it has none)
//   invoice tagged    -> party's Default Account
// Runs after core's own party / reference handlers have finished, so it is not
// overwritten by the account core sets from get_party_details.
function set_party_account_from_party(frm) {
	const doc = frm.doc;
	if (doc.docstatus !== 0) return;
	if (!["Customer", "Supplier"].includes(doc.party_type)) return;
	if (!doc.party || !doc.company) return;

	let account_field;
	if (doc.payment_type === "Receive") account_field = "paid_from";
	else if (doc.payment_type === "Pay") account_field = "paid_to";
	else return;

	const party = doc.party;

	frappe.call({
		method: "avinashgroup_app.custom_code.payment_entry.party_account.get_party_accounts",
		args: { party_type: doc.party_type, party: party, company: doc.company },
		callback: function (r) {
			// Several of these calls can be in flight at once; read References when the
			// answer arrives, not when it was asked, so a slow earlier reply can't win.
			if (!r.message || frm.doc.party !== party) return;
			const has_tagged_bills = (frm.doc.references || []).some((row) => row.reference_name);
			const accounts = r.message;
			const account = has_tagged_bills
				? accounts.default_account
				: accounts.advance_account || accounts.default_account;

			if (account && frm.doc[account_field] !== account) {
				frm.set_value(account_field, account);
			}
		},
	});
}

// While core is filling the account from get_party_details it keeps
// frm.set_party_account_based_on_party true; wait for it to finish so core's
// account doesn't land on top of ours. Gives up waiting after ~10 seconds.
function set_party_account_after_core(frm, tries_left = 50) {
	if (frm.set_party_account_based_on_party && tries_left > 0) {
		setTimeout(() => set_party_account_after_core(frm, tries_left - 1), 200);
		return;
	}
	set_party_account_from_party(frm);
}

// Core calls frm.events.set_total_allocated_amount every time References change:
// a bill tagged or removed, an allocation edited, and at the end of
// "Get Outstanding Invoices". The total_allocated_amount field event is not
// reliable for this: Get Outstanding Invoices sets the total on the server, so
// the field often does not change in the browser. Wrapping the core function once
// per form catches every case.
function watch_references_for_party_account(frm) {
	if (frm.__party_account_watch) return;
	const core_set_total_allocated_amount = frm.events.set_total_allocated_amount;
	if (!core_set_total_allocated_amount) return;

	frm.events.set_total_allocated_amount = function (frm) {
		const result = core_set_total_allocated_amount.apply(this, arguments);
		set_party_account_after_core(frm);
		return result;
	};
	frm.__party_account_watch = true;
}

// A bill picked by hand in a References row: core only recalculates the total
// when its allocated amount actually changes, so react to the bill itself too.
frappe.ui.form.on("Payment Entry Reference", {
	reference_name: (frm) => set_party_account_after_core(frm),
});

frappe.ui.form.on("Payment Entry", {
	party: (frm) => set_party_account_after_core(frm),
	custom_p_type: function (frm) {
		const payment_type = P_TYPE_TO_PAYMENT_TYPE[frm.doc.custom_p_type];
		if (payment_type && frm.doc.payment_type !== payment_type) {
			frm.set_value("payment_type", payment_type);
		}
		// Bank Customers Receipt rarely carries a real cheque number at entry
		// time -- default it to "1" so the field isn't left blank. Track that
		// we set it ourselves so switching away can clear it again without
		// touching a cheque number the user actually typed in.
		if (frm.doc.custom_p_type === "Bank Customers Receipt") {
			if (!frm.doc.reference_no) {
				frm.set_value("reference_no", "1");
				frm.__auto_reference_no = true;
			}
		} else if (frm.__auto_reference_no) {
			frm.set_value("reference_no", "");
			frm.__auto_reference_no = false;
		}
	},
	setup_party_query: function (frm) {
		if (!frm.fields_dict.party) return;
		frm.set_query("party", function () {
			const party_type = frm.doc.party_type;
			const company = frm.doc.company;
			if (!party_type || !company) {
				return {};
			}
			return {
				query: "avinashgroup_app.custom_code.globalfilter.globalfilter.search_party",
				filters: {
					party_type: party_type,
					company: company,
				},
			};
		});
	},
	onload: function (frm) {
		frm.trigger("setup_party_query");
		watch_references_for_party_account(frm);
	},
	refresh: function (frm) {
		frm.trigger("setup_party_query");
		if (frm.doc.custom_cheque_bounce === "Cheque Bounced") {
			frm.page.set_indicator(__("Cheque Bounced"), "red");
		}

		if (frm.doc.docstatus === 1) {
			frm.add_custom_button(
				__("Cheque Bounce"),
				function () {
					frappe.confirm(
						__(
							"Are you sure you want to mark this as a Cheque Bounce? Reversed GL entries will be posted for <b>{0}</b>.",
							[frm.doc.name]
						),
						function () {
							frappe.call({
								method: "avinashgroup_app.custom_code.payment_entry.cheque_bounce.make_cheque_bounce_entry",
								args: { payment_entry_name: frm.doc.name },
								freeze: true,
								freeze_message: __("Posting Cheque Bounce GL Entries..."),
								callback: function (r) {
									if (!r.exc) {
										frm.reload_doc();
									}
								},
							});
						}
					);
				},
				__("Actions")
			);
		}
	},
	company: function (frm) {
		frm.trigger("setup_party_query");
	},
	party_type: function (frm) {
		frm.trigger("setup_party_query");
	},
});
