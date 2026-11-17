// Copyright (c) 2026, Avinash Group and contributors
// For license information, please see license.txt
//
// Form for one dealer's portal login. The server does the work (see
// customer_portal_access.py); this file adds the password button, issues the
// first password right after the first save, and shows a password to the
// operator only when the SMS could not deliver it.

frappe.ui.form.on("Customer Portal Access", {
	refresh(frm) {
		frm.set_query("customer", "customers", () => ({ filters: { disabled: 0 } }));

		if (frm.is_new()) return;

		if (!(frm.doc.__onload || {}).login_with_mobile) {
			frm.dashboard.set_headline_alert(
				__("Login with mobile number is OFF in System Settings — the dealer must type {0} instead.",
					[frm.doc.user || ""]),
				"orange"
			);
		} else if (!frm.doc.password_sent_on) {
			frm.dashboard.set_headline_alert(__("No password has been issued yet."), "orange");
		}

		if (frm.doc.enabled) {
			frm.add_custom_button(__("Send New Password"), () => {
				frappe.confirm(
					__("Create a new password for {0}? The old password stops working at once.",
						[frm.doc.full_name.bold()]),
					() => issue_password(frm)
				);
			});
		}
		if (frm.doc.user) {
			frm.add_custom_button(__("Open User"), () => frappe.set_route("Form", "User", frm.doc.user), __("View"));
		}
		frm.add_custom_button(__("SMS Log"), () =>
			frappe.set_route("List", "Sparrow SMS Log", {
				reference_doctype: frm.doc.doctype,
				reference_name: frm.doc.name,
			}), __("View"));
	},

	after_save(frm) {
		// First save creates the User; give it a password straight away.
		if (frm.doc.enabled && frm.doc.user && !frm.doc.password_sent_on) {
			issue_password(frm);
		}
	},
});

function issue_password(frm) {
	frappe.call({
		method: "avinashgroup_app.avinash_group_app.doctype.customer_portal_access.customer_portal_access.issue_password",
		args: { name: frm.doc.name },
		freeze: true,
		freeze_message: __("Setting password and sending SMS..."),
		callback(r) {
			const res = r.message || {};
			if (res.sms_sent) {
				frappe.show_alert({ message: res.message, indicator: "green" }, 7);
			} else if (res.password) {
				show_password_once(frm, res);
			}
			frm.reload_doc();
		},
	});
}

function show_password_once(frm, res) {
	const d = new frappe.ui.Dialog({
		title: __("Give this password to the dealer"),
		fields: [{
			fieldtype: "HTML",
			options: `
				<p class="text-muted">${frappe.utils.escape_html(res.message)}</p>
				<table class="table table-bordered" style="font-size: 16px">
					<tr><td>${__("Mobile No")}</td><td><b>${frappe.utils.escape_html(frm.doc.mobile_no)}</b></td></tr>
					<tr><td>${__("Password")}</td><td><b style="font-family: monospace; font-size: 20px">${frappe.utils.escape_html(res.password)}</b></td></tr>
				</table>
				<p class="text-muted small">${__("This is shown only once. It cannot be looked up later — use Send New Password if it is lost.")}</p>`,
		}],
		primary_action_label: __("Copy and Close"),
		primary_action() {
			frappe.utils.copy_to_clipboard(`${__("Mobile")}: ${frm.doc.mobile_no}  ${__("Password")}: ${res.password}`);
			d.hide();
		},
	});
	d.show();
}
