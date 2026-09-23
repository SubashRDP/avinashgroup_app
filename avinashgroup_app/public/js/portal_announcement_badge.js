// Copyright (c) 2026, Avinash Group and contributors
// For license information, please see license.txt

/**
 * Unread badge on the portal sidebar's Announcements link — "Announcements (2)".
 *
 * The count is fetched with frappe.call rather than rendered into the sidebar by
 * the server on purpose: website pages are cached by path and language, not by
 * user, so a count baked into the HTML would be handed to whoever loads that page
 * next. Fetching it here keeps it per-viewer on a cached page.
 *
 * Deliberately narrow: this only decorates a link that Portal Settings already
 * shows. It does not add the menu entry — that is a Portal Settings row.
 */
(function () {
	// The portal route the badge attaches to, matched against each sidebar link's
	// pathname so a trailing slash or a full URL still matches.
	const ANNOUNCEMENTS_ROUTE = "/portal_announcement_history";
	const BADGE_CLASS = "ag-ann-badge";

	function sidebarLinks() {
		return Array.from(document.querySelectorAll("a[href]")).filter((a) => {
			let path;
			try {
				path = new URL(a.href, window.location.origin).pathname;
			} catch (e) {
				return false;
			}
			return path.replace(/\/+$/, "") === ANNOUNCEMENTS_ROUTE;
		});
	}

	function render(count) {
		sidebarLinks().forEach((link) => {
			const existing = link.querySelector("." + BADGE_CLASS);
			if (existing) {
				existing.remove();
			}
			if (!count) {
				return;
			}
			const badge = document.createElement("span");
			badge.className = BADGE_CLASS;
			badge.textContent = " (" + count + ")";
			badge.style.fontWeight = "600";
			link.appendChild(badge);
		});
	}

	function refresh() {
		if (!sidebarLinks().length) {
			// The link is not on this page — nothing to decorate, so skip the call.
			return;
		}
		if (!window.frappe || !frappe.call) {
			return;
		}
		frappe.call({
			method:
				"avinashgroup_app.avinash_group_app.doctype.portal_announcement_read.portal_announcement_read.get_unread_count",
			callback: function (r) {
				render(parseInt(r && r.message, 10) || 0);
			},
			// A failed count must never surface an error dialog on a portal page.
			error: function () {},
		});
	}

	if (document.readyState === "loading") {
		document.addEventListener("DOMContentLoaded", refresh);
	} else {
		refresh();
	}
})();
