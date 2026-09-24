// Copyright (c) 2026, Avinash Group and contributors
// For license information, please see license.txt

/**
 * Buttons on the customer portal's Orders pages.
 *
 *   /orders          (the list)      "Place Order" (primary, → /place_order)
 *                                    and "Customer Statement" in the page header
 *   /orders/<name>   (one order)     "Customer Statement" in the page's Actions
 *                                    dropdown, next to Print
 *
 * The order's link is /customer_statement?order=<name>: the statement opens on
 * that order's company and customer. customer_statement.py resolves the order
 * server-side and only preselects when the customer belongs to the logged-in
 * user, so nothing here is trusted.
 *
 * Injected client-side because both pages are stock templates (Frappe's
 * www/list.html, ERPNext's templates/pages/order.html); overriding either
 * would fork the whole page for one link.
 */
frappe.ready(function () {
	const path = window.location.pathname.replace(/\/+$/, "");
	const label = __("Customer Statement");

	if (path === "/orders") {
		const $wrap = $(".page-header-wrapper").first();
		if (!$wrap.length || $wrap.find(".ag-cs-link").length) return;
		// list.html only renders the actions block when there is a "New" button.
		let $block = $wrap.find(".page-header-actions-block");
		if (!$block.length) $block = $('<div class="page-header-actions-block"></div>').appendTo($wrap);
		$('<a class="btn btn-primary btn-sm ag-po-link">')
			.attr("href", "/place_order")
			.text(__("Place Order"))
			.appendTo($block);
		$('<a class="btn btn-secondary btn-sm ag-cs-link ml-2">')
			.attr("href", "/customer_statement")
			.text(label)
			.appendTo($block);
		return;
	}

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
