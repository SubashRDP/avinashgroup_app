// Sign QZ Tray requests so the "Allow" prompt can be remembered / suppressed.
//
// Frappe's qz integration (frappe/form/print_utils.js) never calls
// qz.security.*, so every request reaches QZ Tray anonymous and QZ re-prompts
// each session ("Remember this decision" needs an identity to remember).
// This wraps frappe.ui.form.qz_init and, once the qz object exists, points
// certificate + signature at custom_code/printing/qz_security.py.
//
// With the site cert also installed as QZ's override certificate
// (override.crt in the QZ install dir) the connection is fully trusted and
// no prompt appears at all.

(function () {
	function wire() {
		if (!window.qz || qz.__avinash_signed) return;
		qz.security.setCertificatePromise(function (resolve, reject) {
			frappe
				.call("avinashgroup_app.custom_code.printing.qz_security.certificate")
				.then((r) => (r.message ? resolve(r.message) : reject("no qz certificate on site")))
				.catch(reject);
		});
		if (qz.security.setSignatureAlgorithm) {
			qz.security.setSignatureAlgorithm("SHA512");
		}
		qz.security.setSignaturePromise(function (toSign) {
			return function (resolve, reject) {
				frappe
					.call({
						method: "avinashgroup_app.custom_code.printing.qz_security.sign",
						args: { request: toSign },
					})
					.then((r) => (r.message ? resolve(r.message) : reject("qz signing failed")))
					.catch(reject);
			};
		});
		qz.__avinash_signed = true;
	}

	$(document).on("app_ready", function () {
		const orig = frappe.ui.form.qz_init;
		if (!orig || orig.__avinash_patched) return;
		frappe.ui.form.qz_init = function () {
			return orig.apply(this, arguments).then((r) => {
				wire();
				return r;
			});
		};
		frappe.ui.form.qz_init.__avinash_patched = true;
	});
})();
