// Copyright (c) 2026, Avinash Group and contributors
// For license information, please see license.txt

/**
 * "Customer Statement" in the Actions dropdown of /orders/<name>, next to Print.
 * The /orders list has its own header now (www/Sales Order.html).
 *
 * The order's link is /customer_statement?order=<name>: the statement opens on
 * that order's company and customer. customer_statement.py resolves the order
 * server-side and only preselects when the customer belongs to the logged-in
 * user, so nothing here is trusted.
 *
 * Injected client-side because the page is a stock template (ERPNext's
 * templates/pages/order.html); overriding it would fork the whole page for one
 * link.
 */
frappe.ready(function () {
	const path = window.location.pathname.replace(/\/+$/, "");
	const label = __("Customer Statement");

	const m = path.match(/^\/orders\/([^/]+)$/);
	if (m) {
		const $menu = $(".page-header-actions-block .dropdown-menu").first();
		if (!$menu.length || $menu.find(".ag-cs-link").length) return;
		$('<a class="dropdown-item ag-cs-link">')
			.attr("href", "/customer_statement?order=" + encodeURIComponent(decodeURIComponent(m[1])))
			.text(label)
			.appendTo($menu);
	}
});
