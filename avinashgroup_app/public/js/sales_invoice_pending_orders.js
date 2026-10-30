// Sales Invoice: point the billing clerk at the Sales Order before they type.
//
// Customers order through the portal, but invoices kept being keyed in by hand
// instead of pulled from the order. Three nudges on a draft invoice:
//
// 1. Customer picked -> if that customer has pending orders, a popup lists them
//    with Fill (one) / Fill selected. Once per customer per form.
// 2. A glass tab on the right edge, "Pending orders (n)". Click it or swipe it
//    left and a drawer slides in with the company's pending orders, searchable,
//    narrowable to this customer, each with Fill. Swipe right / Esc / clicking
//    anywhere on the form closes it.
//    The same tab and drawer sit on the Sales Invoice and Sales Order list,
//    report and dashboard views, on the Selling / Accounting workspaces, and
//    on any Sales Invoice that is not an open draft (submitted, cancelled,
//    returns, a new one with no company yet).
//    There it covers every company the user may read (User Permissions on
//    Company decide), with a chip per company, and each order has Make
//    Invoice — a new invoice from that order.
// 3. A new, empty invoice opens that drawer by itself — once per browser
//    session, so it nudges without nagging.
//
// The drawer must never get between the clerk and the form: it has no
// backdrop, it does not take focus when it opens on its own, a click on the
// form closes it AND still reaches the field, and while closed it is
// visibility:hidden so Tab cannot wander into it. An earlier version broke all
// four and made the invoice feel like it would not take input.
//
// Fill is the same request ERPNext's Get Items From > Sales Order makes
// (map_docs + make_sales_invoice), so rates, taxes and the sales_order links
// on the rows are stock behaviour. An order for a different customer than an
// invoice that already has items opens as a new invoice instead.
//
// Rows: pending_orders.get_pending_orders. Styles: css/sales_pending_orders.css.
// Loaded from app_include_js, like sales_invoice_so_picker.js.

(function () {
	const API = "avinashgroup_app.custom_code.SalesInvoice.pending_orders.get_pending_orders";
	const MAKE_SI = "erpnext.selling.doctype.sales_order.sales_order.make_sales_invoice";
	const AUTO_KEY = "ag_po_drawer_auto_opened";

	const esc = (v) => frappe.utils.escape_html(String(v == null ? "" : v));

	// ---------- shared ----------

	function is_open_draft(frm) {
		return frm.doc.docstatus === 0 && !frm.doc.is_return && !!frm.doc.company;
	}

	function has_items(frm) {
		return (frm.doc.items || []).some((d) => d.item_code);
	}

	// Orders already mapped onto this invoice. Filling one again would add its
	// rows twice — map_docs has no such check; ERPNext's dialog does it itself.
	function linked_orders(frm) {
		return new Set((frm.doc.items || []).map((d) => d.sales_order).filter(Boolean));
	}

	function is_blank_invoice(frm) {
		return !!frm && frm.doctype === "Sales Invoice" && frm.is_new() && frm.doc.docstatus === 0
			&& !frm.doc.is_return && !has_items(frm);
	}

	function fetch_orders(frm, opts = {}) {
		return frappe.xcall(API, { company: frm.doc.company, ...opts });
	}

	// Make Invoice from outside an invoice (list views, the alert cards): open a
	// new invoice, give it the order's company, then Fill it like the form does.
	// Not open_mapped_doc: a site whose Sales Invoice "company" is No Copy
	// (avinasdemo has that Property Setter) maps the order onto an invoice with
	// no company and ERPNext throws "Please select a Company".
	let pending_fill = null;

	function make_invoice(order) {
		pending_fill = order;
		frappe.new_doc("Sales Invoice");
	}

	function fill_pending(frm) {
		const order = pending_fill;
		pending_fill = null;
		frm.__ag_po_filling = true; // no auto-open drawer over this one
		const go = () => fill(frm, [order]);
		if (frm.doc.company === order.company) go();
		else frm.set_value("company", order.company).then(go);
	}

	window.avinash = window.avinash || {};
	avinash.make_invoice_from_order = make_invoice;

	// Map orders onto this invoice — what erpnext.utils.map_current_doc's _map
	// does once the dialog has picked them.
	function fill(frm, orders) {
		const linked = linked_orders(frm);
		orders = orders.filter((o) => !linked.has(o.name));
		if (!orders.length) {
			frappe.show_alert({ message: __("That order is already on this invoice"), indicator: "orange" });
			return;
		}

		const customers = [...new Set(orders.map((o) => o.customer))];
		if (customers.length > 1) {
			frappe.msgprint(__("Pick orders of one customer at a time."));
			return;
		}
		if (frm.doc.customer && customers[0] !== frm.doc.customer && has_items(frm)) {
			// this invoice is somebody else's; give the order its own invoice
			frappe.model.open_mapped_doc({ method: MAKE_SI, source_name: orders[0].name });
			return;
		}

		if (frm.doc.items && frm.doc.items.length && !frm.doc.items[0].item_code) {
			frm.doc.items.splice(0, 1);
		}
		// filling sets the customer itself; don't pop the customer popup after
		frm.__ag_po_popup_for = customers[0];

		return frappe.call({
			type: "POST",
			method: "frappe.model.mapper.map_docs",
			args: {
				method: MAKE_SI,
				source_names: orders.map((o) => o.name),
				target_doc: frm.doc,
			},
			freeze: true,
			freeze_message: __("Filling from {0} ...", [orders.map((o) => o.name).join(", ")]),
			callback(r) {
				if (r.exc) return;
				frappe.model.sync(r.message);
				frm.dirty();
				frm.refresh();
				frappe.show_alert({ message: __("Filled from {0}", [orders.map((o) => o.name).join(", ")]), indicator: "green" });
			},
		});
	}

	function order_html(o, { check = false, action_label = __("Fill"), added = false, show_company = false } = {}) {
		const billed = Math.min(100, Math.max(0, o.per_billed || 0));
		const meta = [
			show_company ? `<span class="ag-po-chip-tag" title="${esc(o.company)}">${esc(o.company_abbr)}</span>` : "",
			`<a href="/app/sales-order/${encodeURIComponent(o.name)}" target="_blank">${esc(o.name)}</a>`,
			esc(o.miti),
			__("Qty {0}", [format_number(o.total_qty, null, 2)]),
		].filter(Boolean).join(" · ");
		return `
			<div class="ag-po-order ${check ? "" : "ag-po-order--nocheck"}" data-name="${esc(o.name)}">
				${check ? `<input type="checkbox" class="ag-po-order__check" aria-label="${esc(o.name)}">` : ""}
				<div class="ag-po-order__main">
					<div class="ag-po-order__title" title="${esc(o.customer_name)}">${esc(o.customer_name)}</div>
					<div class="ag-po-order__meta">${meta}</div>
				</div>
				<div class="ag-po-order__side">
					<div class="ag-po-order__amount">${esc(format_currency(o.grand_total, o.currency))}</div>
					${added
						? `<button class="ag-po-btn ag-po-btn--ghost" disabled>✓ ${__("Added")}</button>`
						: `<button class="ag-po-btn ag-po-btn--primary" data-act="fill">${esc(action_label)}</button>`}
				</div>
				${billed > 0 ? `
				<div class="ag-po-billed">
					<div class="ag-po-billed__track"><div class="ag-po-billed__bar" style="width:${billed}%"></div></div>
					<span>${__("{0}% billed", [Math.round(billed)])}</span>
				</div>` : ""}
				${o.remarks ? `<div class="ag-po-order__remarks" title="${esc(o.remarks)}">“${esc(o.remarks)}”</div>` : ""}
			</div>`;
	}

	// ---------- 1. popup when a customer is picked ----------

	function maybe_popup(frm) {
		const customer = frm.doc.customer;
		if (!customer || !is_open_draft(frm)) return;
		if (frm.__ag_po_popup_for === customer) return;
		if ((frm.doc.items || []).some((d) => d.sales_order)) return;
		frm.__ag_po_popup_for = customer;

		fetch_orders(frm, { customer }).then((r) => {
			// the clerk may have moved on while we asked
			if (!r || !r.orders.length || frm.doc.customer !== customer) return;
			show_popup(frm, r.orders);
		});
	}

	function show_popup(frm, orders) {
		const d = new frappe.ui.Dialog({
			title: __("{0} has {1} pending order(s)", [frm.doc.customer_name || frm.doc.customer, orders.length]),
			size: "large",
			fields: [{ fieldtype: "HTML", fieldname: "list" }],
			primary_action_label: __("Fill selected"),
			primary_action() {
				const picked = orders.filter((o) => d.$wrapper.find(`.ag-po-order[data-name="${CSS.escape(o.name)}"] .ag-po-order__check`).prop("checked"));
				if (!picked.length) {
					frappe.show_alert({ message: __("Tick at least one order"), indicator: "orange" });
					return;
				}
				d.hide();
				fill(frm, picked);
			},
			secondary_action_label: __("Skip, type it myself"),
			secondary_action() {
				d.hide();
			},
		});
		d.$wrapper.addClass("ag-po-dialog");

		const $list = $(`
			<div>
				<div class="ag-po-lead">${__("Fill the invoice from the order instead of typing it — items, rates and taxes come across as ordered.")}</div>
				${orders.map((o) => order_html(o, { check: true })).join("")}
			</div>`);
		$list.on("change", ".ag-po-order__check", function () {
			$(this).closest(".ag-po-order").toggleClass("is-checked", this.checked);
		});
		$list.on("click", "[data-act=fill]", function () {
			const name = $(this).closest(".ag-po-order").data("name");
			d.hide();
			fill(frm, orders.filter((o) => o.name === name));
		});
		d.fields_dict.list.$wrapper.empty().append($list);
		d.show();
	}

	// ---------- 2. edge tab + drawer ----------

	// One tab/drawer for the whole desk. Two modes:
	//   form — ui.frm is a draft Sales Invoice; its company only; Fill.
	//   list — ui.frm is null; every company the user may read, chips to
	//          narrow to one (ui.company); Make Invoice.
	const LIST_DOCTYPES = ["Sales Invoice", "Sales Order"]; // any view: List, Report, Dashboard ...
	const WORKSPACES = ["Selling", "Accounting", "Accounts"];

	const ui = {
		frm: null,
		company: null, // list mode: the picked chip, null = all
		orders: [],
		mine_only: false,
		search: "",
		tab_on: false, // this page should show the tab (reopens after the drawer closes)
		$tab: null,
		$drawer: null,
	};

	const in_list_mode = () => !ui.frm;

	function is_list_route(route = frappe.get_route() || []) {
		return (route[0] === "List" && LIST_DOCTYPES.includes(route[1]))
			|| (route[0] === "Workspaces" && WORKSPACES.includes(route[1]));
	}

	function build() {
		if (ui.$tab) return;

		ui.$tab = $(`
			<div class="ag-po-tab ag-po-glass is-hidden" role="button" tabindex="0"
				aria-label="${__("Pending sales orders")}">
				<span class="ag-po-tab__grip"></span>
				<span class="ag-po-tab__count">0</span>
				<span class="ag-po-tab__label">${__("Pending orders")}</span>
			</div>`).appendTo(document.body);

		ui.$drawer = $(`
			<aside class="ag-po-drawer ag-po-glass" aria-hidden="true">
				<div class="ag-po-drawer__head">
					<div>
						<h4 class="ag-po-drawer__title">${__("Pending orders")}</h4>
						<div class="ag-po-drawer__sub"></div>
					</div>
					<button class="ag-po-icon-btn" data-act="close" aria-label="${__("Close")}">×</button>
				</div>
				<div class="ag-po-drawer__tools">
					<input class="ag-po-search" type="search" placeholder="${__("Search order or customer")}">
					<div class="ag-po-seg">
						<button data-scope="all" class="is-active">${__("All customers")}</button>
						<button data-scope="mine"></button>
					</div>
					<div class="ag-po-chips"></div>
				</div>
				<div class="ag-po-drawer__list"></div>
				<div class="ag-po-drawer__foot">
					<span class="ag-po-drawer__count"></span>
					<a href="#" data-act="list">${__("Open Sales Order list")} →</a>
				</div>
			</aside>`).appendTo(document.body);

		// asked for by the clerk: put them straight into the search box
		const open_by_hand = () => open_drawer({ focus: true });
		ui.$tab.on("click", open_by_hand);
		ui.$tab.on("keydown", (e) => (e.key === "Enter" || e.key === " ") && open_by_hand());
		swipe(ui.$tab, (dx) => dx < -30 && open_by_hand());

		// Any press outside the drawer closes it — without swallowing the press,
		// so the field the clerk clicked gets it as normal. Alert cards and
		// dialogs are left alone.
		document.addEventListener("pointerdown", (e) => {
			if (!ui.$drawer.hasClass("is-open")) return;
			if ($(e.target).closest(".ag-po-drawer, .ag-po-tab, .ag-po-alerts, .modal").length) return;
			close_drawer();
		}, true);

		ui.$drawer.on("click", "[data-act=close]", close_drawer);
		ui.$drawer.on("click", "[data-act=list]", (e) => {
			e.preventDefault();
			const company = ui.frm ? ui.frm.doc.company : ui.company;
			close_drawer();
			frappe.set_route("List", "Sales Order", {
				...(company ? { company } : {}),
				docstatus: 1,
				per_billed: ["<", 99.99],
				status: ["not in", ["Closed", "On Hold", "Completed"]],
			});
		});
		ui.$drawer.on("click", "[data-scope]", function () {
			if (this.disabled) return;
			ui.mine_only = $(this).data("scope") === "mine";
			load();
		});
		ui.$drawer.on("click", "[data-company]", function () {
			ui.company = $(this).attr("data-company") || null;
			load();
		});
		ui.$drawer.on("input", ".ag-po-search", frappe.utils.debounce(function () {
			ui.search = this.value.trim();
			load();
		}, 300));
		ui.$drawer.on("click", "[data-act=fill]", function () {
			const name = $(this).closest(".ag-po-order").data("name");
			const order = ui.orders.find((o) => o.name === name);
			close_drawer();
			if (!order) return;
			if (ui.frm) fill(ui.frm, [order]);
			else if (is_blank_invoice(window.cur_frm)) {
				// a new invoice still waiting for its company: fill this one, not another
				pending_fill = order;
				fill_pending(cur_frm);
			} else make_invoice(order);
		});

		// drag the drawer to the right to close it
		swipe(ui.$drawer, (dx) => dx > 80 && close_drawer(), (dx) => {
			ui.$drawer.addClass("is-dragging").css("transform", `translateX(${Math.max(0, dx)}px)`);
		}, () => ui.$drawer.removeClass("is-dragging").css("transform", ""));

		$(document).on("keydown", (e) => e.key === "Escape" && ui.$drawer.hasClass("is-open") && close_drawer());
	}

	// Horizontal swipe on touch screens. on_end(dx) on release; on_move(dx) while dragging.
	function swipe($el, on_end, on_move, on_reset) {
		let x0 = null;
		let y0 = null;
		$el.on("touchstart", (e) => {
			const t = e.originalEvent.touches[0];
			x0 = t.clientX;
			y0 = t.clientY;
		});
		$el.on("touchmove", (e) => {
			if (x0 === null || !on_move) return;
			const t = e.originalEvent.touches[0];
			if (Math.abs(t.clientX - x0) > Math.abs(t.clientY - y0)) on_move(t.clientX - x0);
		});
		$el.on("touchend touchcancel", (e) => {
			if (x0 === null) return;
			const t = e.originalEvent.changedTouches[0];
			const dx = t.clientX - x0;
			x0 = null;
			on_reset && on_reset();
			on_end(dx);
		});
	}

	function set_count(n) {
		ui.$tab.find(".ag-po-tab__count").text(n > 99 ? "99+" : n);
		ui.$tab.toggleClass("is-empty", !n);
	}

	function show_tab() {
		ui.tab_on = true;
		ui.$tab.removeClass("is-hidden");
	}

	function hide_tab() {
		if (!ui.$tab) return;
		ui.tab_on = false;
		close_drawer();
		ui.$tab.addClass("is-hidden");
	}

	// Form mode: show the tab for this invoice and refresh its count.
	function attach(frm) {
		build();
		if (!is_open_draft(frm)) {
			// nothing to fill here; offer every company's orders instead
			attach_list();
			return Promise.resolve(0);
		}
		if (ui.frm !== frm) close_drawer();
		ui.frm = frm;
		show_tab();
		return fetch_orders(frm, { limit: 1 }).then((r) => {
			if (ui.frm !== frm) return 0;
			set_count(r.count);
			return r.count;
		});
	}

	// List mode: every company the user may read.
	function attach_list() {
		build();
		if (ui.frm) close_drawer();
		ui.frm = null;
		show_tab();
		frappe.xcall(API, { limit: 1 }).then((r) => {
			if (!ui.frm) set_count(r.count);
		});
	}

	function on_route() {
		// empty until the router's first pass — app_ready can come before it
		const route = frappe.get_route() || [];
		if (route[0] === "Form" && route[1] === "Sales Invoice") return; // the form's refresh attaches
		if (is_list_route(route)) attach_list();
		else hide_tab();
	}

	function open_drawer({ focus = false } = {}) {
		const frm = ui.frm;
		if (frm) {
			ui.$drawer.find("[data-scope=mine]")
				.text(frm.doc.customer_name || frm.doc.customer || __("This customer"))
				.prop("disabled", !frm.doc.customer);
			// with a customer already picked, start narrowed to them
			ui.mine_only = !!frm.doc.customer;
			ui.$drawer.find(".ag-po-drawer__sub").text(frm.doc.company);
		} else {
			ui.mine_only = false;
			ui.$drawer.find(".ag-po-drawer__sub").text(__("All your companies"));
		}
		ui.$drawer.find(".ag-po-seg").toggle(!!frm);
		ui.$drawer.find(".ag-po-chips").toggle(!frm);
		ui.$drawer.addClass("is-open").attr("aria-hidden", "false");
		$(document.body).addClass("ag-po-drawer-open");
		ui.$tab.addClass("is-hidden");
		load();
		if (focus) setTimeout(() => ui.$drawer.find(".ag-po-search").trigger("focus"), 320);
	}

	function close_drawer() {
		if (!ui.$drawer || !ui.$drawer.hasClass("is-open")) return;
		// focus inside a drawer that is about to be hidden would be lost
		if (ui.$drawer[0].contains(document.activeElement)) document.activeElement.blur();
		ui.$drawer.removeClass("is-open").attr("aria-hidden", "true");
		$(document.body).removeClass("ag-po-drawer-open");
		if (ui.tab_on) ui.$tab.removeClass("is-hidden");
	}

	function render_chips(companies) {
		const total = companies.reduce((n, c) => n + c.count, 0);
		const chip = (value, label, n, title) => `
			<button data-company="${esc(value)}" title="${esc(title)}"
				class="${(ui.company || "") === value ? "is-active" : ""}">
				${esc(label)} <span>${n}</span>
			</button>`;
		ui.$drawer.find(".ag-po-chips").html(
			chip("", __("All"), total, __("All your companies"))
			+ companies.map((c) => chip(c.company, c.abbr, c.count, c.company)).join("")
		);
	}

	function load() {
		const frm = ui.frm;
		ui.$drawer.find("[data-scope]").each(function () {
			$(this).toggleClass("is-active", ($(this).data("scope") === "mine") === ui.mine_only);
		});
		const $list = ui.$drawer.find(".ag-po-drawer__list");
		const args = { txt: ui.search || undefined };
		if (frm) {
			args.company = frm.doc.company;
			if (ui.mine_only && frm.doc.customer) args.customer = frm.doc.customer;
		} else {
			args.company = ui.company || undefined;
			args.with_companies = 1;
		}

		frappe.xcall(API, args).then((r) => {
			if (ui.frm !== frm) return;
			ui.orders = r.orders;
			if (!frm) {
				render_chips(r.companies || []);
				ui.$drawer.find(".ag-po-drawer__sub").text(ui.company || __("All your companies"));
			}
			ui.$drawer.find(".ag-po-drawer__count").text(
				r.count > r.orders.length
					? __("Showing {0} of {1}", [r.orders.length, r.count])
					: __("{0} order(s)", [r.count])
			);
			if (!r.orders.length) {
				$list.html(`<div class="ag-po-empty">${__("Nothing waiting to be invoiced.")}</div>`);
				return;
			}
			if (!frm) {
				$list.html(r.orders.map((o) => order_html(o, {
					action_label: __("Make Invoice"),
					show_company: !ui.company,
				})).join(""));
				return;
			}
			const linked = linked_orders(frm);
			$list.html(r.orders.map((o) => order_html(o, {
				added: linked.has(o.name),
				action_label: frm.doc.customer && o.customer !== frm.doc.customer && has_items(frm)
					? __("New invoice") : __("Fill"),
			})).join(""));
		});
	}

	// ---------- 3. auto-open once per session ----------

	function auto_open_once(frm, count) {
		if (!count || !frm.is_new() || frm.doc.customer || has_items(frm) || frm.__ag_po_filling) return;
		try {
			if (sessionStorage.getItem(AUTO_KEY)) return;
			sessionStorage.setItem(AUTO_KEY, "1");
		} catch (e) {
			return; // storage blocked: never auto-open rather than open every time
		}
		open_drawer();
	}

	frappe.ui.form.on("Sales Invoice", {
		refresh(frm) {
			if (pending_fill && frm.is_new() && frm.doc.docstatus === 0) fill_pending(frm);
			attach(frm).then((count) => auto_open_once(frm, count));
		},
		company(frm) {
			// the company is often filled in after the form opens
			attach(frm).then((count) => auto_open_once(frm, count));
		},
		customer(frm) {
			// let ERPNext's own customer handlers settle first
			setTimeout(() => maybe_popup(frm), 400);
		},
	});

	$(document).on("app_ready", function () {
		frappe.router.on("change", on_route);
		on_route();
	});
})();
