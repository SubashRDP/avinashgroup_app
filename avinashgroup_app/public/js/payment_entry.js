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

		if (frm.doc.docstatus === 1) add_cheque_bounce_buttons(frm);
	},
	company: function (frm) {
		frm.trigger("setup_party_query");
	},
	party_type: function (frm) {
		frm.trigger("setup_party_query");
	},
});

// Cheque bounce on a submitted Payment Entry, through the PDC module: the dialog
// asks for date, reason and charges; a PDC Cheque record then carries Re-present,
// Replace and Undo. Server side: avinashgroup_app/pdc/payment_entry_bounce.py.
const PE_BOUNCE_API = "avinashgroup_app.pdc.payment_entry_bounce";

function add_cheque_bounce_buttons(frm) {
	if (!["Receive", "Pay"].includes(frm.doc.payment_type)) return;
	if (!["Customer", "Supplier"].includes(frm.doc.party_type)) return;

	if (frm.doc.pdc_cheque) {
		frm.add_custom_button(__("Cheque Record"), () => frappe.set_route("Form", "PDC Cheque", frm.doc.pdc_cheque), __("Cheque"));
	}
	if (frm.doc.custom_cheque_bounce === "Cheque Bounced") {
		if (frm.doc.pdc_cheque) {
			frm.add_custom_button(__("Replace With New Payment"), () => replace_with_payment(frm), __("Cheque"));
			if (frappe.user.has_role(["Accounts Manager", "System Manager"]))
				frm.add_custom_button(__("Undo Bounce"), () => undo_bounce(frm), __("Cheque"));
		}
		return;
	}
	frm.add_custom_button(__("Cheque Bounced"), () => bounce_payment_dialog(frm), __("Cheque"));
}

function bounce_payment_dialog(frm) {
	const received = frm.doc.payment_type === "Receive";
	const d = new frappe.ui.Dialog({
		title: __("Cheque Bounced: {0}", [frm.doc.reference_no || frm.doc.name]),
		fields: [
			{
				fieldtype: "HTML",
				options: `<p class="text-muted small">${__(
					"Posts one Journal Entry that reverses this payment on the bounce date: the invoices it paid become unpaid again and the bank is credited. This Payment Entry itself is not changed."
				)}</p>`,
			},
			{ fieldname: "posting_date", fieldtype: "Date", label: __("Bounce Date"), reqd: 1, default: frappe.datetime.get_today() },
			{
				fieldname: "reason",
				fieldtype: "Select",
				label: __("Reason"),
				reqd: 1,
				options: [
					"",
					"Insufficient Funds",
					"Signature Mismatch",
					"Signature Missing",
					"Stale Cheque",
					"Post Dated (Presented Early)",
					"Payment Stopped by Drawer",
					"Account Closed",
					"Amount in Words and Figures Differ",
					"Alteration / Overwriting",
					"Other",
				].join("\n"),
			},
			{ fieldname: "charges", fieldtype: "Currency", label: __("Bank Charges"), default: 0 },
			{
				fieldname: "jv_type",
				fieldtype: "Link",
				options: "JV Type",
				label: __("Journal Type"),
				reqd: 1,
				description: __("Numbering series of the bounce Journal Entry"),
			},
			{
				fieldname: "recover_charges",
				fieldtype: "Check",
				label: __("Recover Charges From Party"),
				hidden: received ? 0 : 1,
				description: __("Debit the customer for the charge instead of booking it as an expense"),
			},
		],
		primary_action_label: __("Record Bounce"),
		primary_action(values) {
			d.hide();
			frappe.call({
				method: `${PE_BOUNCE_API}.bounce`,
				args: Object.assign({ payment_entry: frm.doc.name }, values),
				freeze: true,
				freeze_message: __("Recording the bounce…"),
				callback: (r) => {
					if (r.exc) return;
					frm.reload_doc();
					frappe.show_alert({ message: __("Bounce recorded on {0}", [r.message]), indicator: "red" });
				},
			});
		},
	});
	d.show();
	set_default_jv_type(d);
}

// Journal Type defaults to PDC Settings → JV Type; the user may pick another.
function set_default_jv_type(d) {
	frappe.db.get_single_value("PDC Settings", "jv_type").then((v) => v && d.set_value("jv_type", v));
}

function undo_bounce(frm) {
	frappe.confirm(
		__("Undo the bounce of {0}? Its bounce Journal Entry is cancelled and the invoices are paid again.", [
			frm.doc.reference_no || frm.doc.name,
		]),
		() =>
			frappe.call({
				method: `${PE_BOUNCE_API}.undo_bounce`,
				args: { payment_entry: frm.doc.name },
				freeze: true,
				callback: (r) => {
					if (r.exc) return;
					frm.reload_doc();
					frappe.show_alert({ message: __("Bounce undone"), indicator: "green" });
				},
			})
	);
}

function replace_with_payment(frm) {
	frappe.call({
		method: `${PE_BOUNCE_API}.make_replacement_payment_entry`,
		args: { name: frm.doc.pdc_cheque },
		callback: (r) => {
			const doc = frappe.model.sync(r.message)[0];
			frappe.set_route("Form", doc.doctype, doc.name);
		},
	});
}
