// "Audit Trail" in the ⋯ menu of every form whose doctype records changes.
//
// Opens /app/document-audit-trail for the open document (see
// avinash_group_app/page/document_audit_trail). A menu entry rather than a
// button so it adds nothing to the form's toolbar for day-to-day users.
// Loaded from app_include_js in hooks.py.

(function () {
	// must match ALLOWED_ROLES in document_audit_trail.py — the page refuses others
	const ROLES = ["Auditor", "System Manager", "Accounts Manager"];
	const LABEL = "Audit Trail";

	$(document).on("form-refresh", function (e, frm) {
		if (!frm || frm.is_new() || !frm.meta.track_changes || frm.meta.issingle) return;
		if (!ROLES.some((role) => frappe.user.has_role(role))) return;
		// the menu is rebuilt on most refreshes, but not all of them
		if (frm.page.menu.find(`[data-label="${encodeURIComponent(__(LABEL))}"]`).length) return;
		frm.page.add_menu_item(__(LABEL), () =>
			frappe.set_route("document-audit-trail", frm.doctype, frm.docname)
		);
	});
})();
