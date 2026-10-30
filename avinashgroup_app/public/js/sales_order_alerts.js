// New-order cards for sales staff — bottom right of the desk, chat style.
//
// When a Sales Order is submitted, customer_notifications.py writes a bell
// entry for the company's Sales Persons and pushes "avinash_new_sales_order"
// to each of them. This file turns that push into a glass card with Make
// Invoice (a new invoice filled from the order) and View
// Order. Either, or ×, marks the bell entry read.
//
// A card shows for 20 seconds, with a bar running down along its foot. The
// clock stops while the pointer is on the card and while the tab is out of
// view, so it cannot vanish under a hand reaching for Make Invoice or while
// nobody is looking. When it runs out the card goes, the bell entry stays
// unread, and the card does not come back for the rest of the browser session
// (sessionStorage) — reloads included.
//
// Staff who were offline get the same cards on their next desk load from
// pending_orders.get_order_alerts — unread entries whose order is still
// unbilled. The same call is the fallback while the live connection is down
// (every minute) and whenever the tab comes back into view: on demo-nggroup
// the socket silently failed to log in for a whole day (the server could not
// reach its own public address), and cards only ever came on refresh.
// Styles: public/css/sales_pending_orders.css.

(function () {
	const ALERTS = "avinashgroup_app.custom_code.SalesInvoice.pending_orders.get_order_alerts";
	const MARK_READ = "frappe.desk.doctype.notification_log.notification_log.mark_as_read";
	const MAX_CARDS = 3; // more than this collapses into "+n more"
	const VISIBLE_SECONDS = 20;
	const SEEN_KEY = "ag_po_alerts_seen"; // timed-out cards, this browser session

	const esc = (v) => frappe.utils.escape_html(String(v == null ? "" : v));
	const shown = new Set(); // order names with a card on screen
	const dismissed = new Set(); // dealt with here; a catch-up must not bring them back
	const queue = []; // alerts waiting for a free slot
	let $stack;

	function stack() {
		if (!$stack) $stack = $(`<div class="ag-po-alerts" aria-live="polite"></div>`).appendTo(document.body);
		return $stack;
	}

	function initials(name) {
		return (name || "?").split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]).join("").toUpperCase();
	}

	function seen_this_session() {
		try {
			return new Set(JSON.parse(sessionStorage.getItem(SEEN_KEY) || "[]"));
		} catch (e) {
			return new Set();
		}
	}

	function remember_seen(name) {
		try {
			const seen = seen_this_session();
			seen.add(name);
			sessionStorage.setItem(SEEN_KEY, JSON.stringify([...seen].slice(-200)));
		} catch (e) {
			// storage blocked: the card may show again after a reload, nothing worse
		}
	}

	function add(alert) {
		if (!alert || shown.has(alert.name) || dismissed.has(alert.name)) return;
		if (seen_this_session().has(alert.name)) return;
		shown.add(alert.name);
		if (stack().children(".ag-po-alert").length >= MAX_CARDS) {
			queue.push(alert);
			render_more();
			return;
		}
		render(alert);
	}

	function render(a) {
		const amount = format_currency(a.grand_total, a.currency);
		const $card = $(`
			<div class="ag-po-alert ag-po-glass" role="status">
				<div class="ag-po-alert__avatar">${esc(initials(a.customer_name))}</div>
				<div class="ag-po-alert__who" title="${esc(a.customer_name)}">${esc(a.customer_name)}</div>
				<div class="ag-po-alert__when">${esc(frappe.datetime.prettyDate(a.when, true))}</div>
				<div class="ag-po-alert__msg">
					${__("New order {0} for {1}", [`<b>${esc(a.name)}</b>`, `<b>${esc(amount)}</b>`])}
					<br>${esc(a.company)}
				</div>
				<div class="ag-po-alert__actions">
					<button class="ag-po-btn ag-po-btn--primary" data-act="invoice">${__("Make Invoice")}</button>
					<button class="ag-po-btn ag-po-btn--ghost" data-act="view">${__("View Order")}</button>
					<button class="ag-po-icon-btn" data-act="close" aria-label="${__("Dismiss")}">×</button>
				</div>
				<div class="ag-po-alert__timer" style="animation-duration: ${VISIBLE_SECONDS}s"></div>
			</div>`);

		// The bar's own animation is the clock: CSS pauses it on hover and while
		// the tab is hidden, and its end is the card's end.
		$card.find(".ag-po-alert__timer").on("animationend", () => {
			remember_seen(a.name);
			done($card, a, { read: false });
		});

		$card.on("click", "[data-act]", function () {
			const act = $(this).data("act");
			done($card, a);
			if (act === "invoice") {
				// same path as the drawer's Make Invoice — see sales_invoice_pending_orders.js
				avinash.make_invoice_from_order({ name: a.name, company: a.company });
			} else if (act === "view") {
				frappe.set_route("Form", "Sales Order", a.name);
			}
		});

		// "+n more" stays the top (last) item; the stack is column-reverse
		const $more = stack().children(".ag-po-alerts__more");
		$more.length ? $card.insertBefore($more) : stack().append($card);
	}

	function render_more() {
		stack().children(".ag-po-alerts__more").remove();
		if (!queue.length) return;
		$(`<button class="ag-po-btn ag-po-glass ag-po-alerts__more">
				${__("+{0} more new orders", [queue.length])}
			</button>`)
			.on("click", () => frappe.set_route("List", "Sales Order", { docstatus: 1, per_billed: ["<", 99.99] }))
			.appendTo(stack());
	}

	function done($card, a, { read = true } = {}) {
		if (read && a.notification) frappe.xcall(MARK_READ, { docname: a.notification }).catch(() => {});
		shown.delete(a.name);
		dismissed.add(a.name);
		$card.addClass("is-leaving");
		setTimeout(() => {
			$card.remove();
			// a free slot: bring the next queued order forward
			const next = queue.shift();
			if (next) render(next);
			render_more();
		}, 250);
	}

	$(document).on("app_ready", function () {
		frappe.realtime.on("avinash_new_sales_order", (alert) => {
			add(alert);
			frappe.utils.play_sound("alert");
		});

		catch_up();
		setInterval(() => socket_up() || catch_up(), 60 * 1000);
		document.addEventListener("visibilitychange", () => {
			const visible = document.visibilityState === "visible";
			stack().toggleClass("is-paused", !visible);
			if (visible) catch_up();
		});
	});

	function socket_up() {
		return !!(frappe.realtime.socket && frappe.realtime.socket.connected);
	}

	function catch_up() {
		frappe.xcall(ALERTS).then((alerts) => (alerts || []).forEach(add)).catch(() => {});
	}
})();
