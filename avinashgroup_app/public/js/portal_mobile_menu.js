// Portal pages in the phone ☰ menu on custom portal pages.
//
// Frappe lists the portal pages (Orders, Invoices, ...) in the ☰ menu only on
// pages with show_sidebar on. Our custom pages keep it off, so their ☰ menu
// opened empty. This adds the same list, with the same markup Frappe uses
// (navbar_items.html), on any page that doesn't already have it. The block is
// "d-lg-none", so it only shows on phones/tablets, like Frappe's own.
// Server side: avinashgroup_app/portal_menu.py.
$(function () {
	if (!frappe.is_user_logged_in || !frappe.is_user_logged_in()) return;

	const $nav = $("#navbarSupportedContent ul.ml-auto.navbar-nav");
	if (!$nav.length) return;
	// Frappe already rendered the list on this page (show_sidebar pages)
	if ($nav.find(".d-lg-none .nav-link").length) return;

	frappe.call({
		method: "avinashgroup_app.portal_menu.get_portal_menu",
		callback: function (r) {
			const items = r.message || [];
			if (!items.length) return;

			const $block = $('<div class="d-block d-lg-none portal-mobile-menu"><hr></div>');
			items.forEach(function (item) {
				const current = window.location.pathname === item.route;
				const $a = $('<a class="nav-link"></a>')
					.attr("href", item.route)
					.addClass(current ? "text-dark" : "text-muted")
					.text(item.title);
				if (item.target) $a.attr("target", item.target);
				$block.append($('<li class="nav-item"></li>').append($a));
			});
			$block.append("<hr>");

			// same place as Frappe's list: just before the account dropdown
			const $login = $nav.children("#website-post-login");
			if ($login.length) $block.insertBefore($login);
			else $nav.append($block);
		}
	});
});
