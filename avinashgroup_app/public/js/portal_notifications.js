// A notification bell for the customer portal.
//
// Portal users have no desk, so the Notification Log entries raised for them on
// Sales Order, Delivery Note and Sales Invoice submit were unreadable. This puts
// a bell in the portal navbar on every website page.
//
// The server pins every query to frappe.session.user, so there is no customer
// to pass and nothing here can widen what it reads.

frappe.ready(function () {
	if (!frappe.session || frappe.session.user === "Guest") return;

	const $navbar = $(".navbar .navbar-nav").last();
	if (!$navbar.length || $navbar.find(".ag-bell").length) return;

	$("<style>").text(`
		.ag-bell-wrap { position: relative; display: flex; align-items: center; }
		.ag-bell {
			position: relative; display: grid; place-items: center;
			width: 34px; height: 34px; padding: 0;
			color: #22357F; background: transparent;
			border: none; border-radius: 8px; cursor: pointer;
		}
		.ag-bell:hover { background: #EDF0F7; }
		.ag-bell svg { width: 19px; height: 19px; }
		.ag-bell-dot {
			position: absolute; top: 2px; right: 2px;
			min-width: 16px; height: 16px; padding: 0 4px;
			font: 600 10px/16px "Barlow", system-ui, sans-serif;
			color: #fff; background: #DA1E28;
			border-radius: 999px; text-align: center;
		}
		.ag-bell-panel {
			position: absolute; top: calc(100% + 8px); right: 0; z-index: 1050;
			width: 340px; max-height: 420px; overflow-y: auto;
			background: #fff; border: 1px solid #DCE1EE; border-radius: 10px;
			box-shadow: 0 20px 44px -22px rgba(14,24,54,.55);
		}
		.ag-bell-panel[hidden] { display: none; }
		.ag-bell-head {
			padding: 11px 14px; border-bottom: 1px solid #EDF0F7;
			font: 600 11.5px/1 "Barlow", system-ui, sans-serif;
			letter-spacing: .14em; text-transform: uppercase; color: #22357F;
		}
		.ag-bell-item { display: block; padding: 12px 14px; border-bottom: 1px solid #EDF0F7; }
		.ag-bell-item:last-child { border-bottom: none; }
		.ag-bell-item.is-unread { background: #F7F9FD; }
		.ag-bell-subject { font: 600 14px/1.3 "Barlow", system-ui, sans-serif; color: #0E1836; }
		.ag-bell-msg { margin-top: 3px; font-size: 13px; line-height: 1.45; color: #5C6785; }
		.ag-bell-when {
			margin-top: 5px; font-size: 11px; letter-spacing: .04em;
			text-transform: uppercase; color: #97A2C2;
		}
		.ag-bell-empty { padding: 26px 14px; text-align: center; font-size: 13.5px; color: #97A2C2; }
		@media (max-width: 480px) { .ag-bell-panel { width: calc(100vw - 24px); right: -8px; } }
	`).appendTo("head");

	const $wrap = $(`
		<li class="nav-item ag-bell-wrap">
			<button class="ag-bell" type="button" aria-label="Notifications" aria-expanded="false">
				<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"
					stroke-linecap="round" stroke-linejoin="round">
					<path d="M18 8a6 6 0 1 0-12 0c0 7-3 9-3 9h18s-3-2-3-9"/>
					<path d="M13.7 21a2 2 0 0 1-3.4 0"/>
				</svg>
			</button>
			<div class="ag-bell-panel" hidden>
				<div class="ag-bell-head">Notifications</div>
				<div class="ag-bell-list"><div class="ag-bell-empty">Loading…</div></div>
			</div>
		</li>
	`).prependTo($navbar);

	const $btn = $wrap.find(".ag-bell");
	const $panel = $wrap.find(".ag-bell-panel");
	const $list = $wrap.find(".ag-bell-list");

	function badge(count) {
		$wrap.find(".ag-bell-dot").remove();
		if (count > 0) {
			$(`<span class="ag-bell-dot">${count > 9 ? "9+" : count}</span>`).appendTo($btn);
		}
	}

	function render(items) {
		$list.empty();
		if (!items.length) {
			$list.append('<div class="ag-bell-empty">Nothing yet.<br>Orders and invoices will show up here.</div>');
			return;
		}
		items.forEach(function (n) {
			$("<div>")
				.addClass("ag-bell-item" + (n.read ? "" : " is-unread"))
				.append($("<div class='ag-bell-subject'>").text(n.subject || "Update"))
				.append($("<div class='ag-bell-msg'>").text(n.message || ""))
				.append($("<div class='ag-bell-when'>").text(n.when || ""))
				.appendTo($list);
		});
	}

	function load(then) {
		frappe.call({
			method: "avinashgroup_app.portal_notifications.get_my_notifications",
			callback: function (r) {
				const d = (r && r.message) || { unread: 0, items: [] };
				badge(d.unread);
				render(d.items || []);
				if (then) then(d);
			}
		});
	}

	$btn.on("click", function (e) {
		e.stopPropagation();
		const opening = $panel.prop("hidden");
		$panel.prop("hidden", !opening);
		$btn.attr("aria-expanded", opening ? "true" : "false");
		if (!opening) return;

		load(function (d) {
			// opening the panel is reading them
			if (!d.unread) return;
			frappe.call({
				method: "avinashgroup_app.portal_notifications.mark_all_read",
				callback: function () { badge(0); }
			});
		});
	});

	$(document).on("click", function (e) {
		if (!$(e.target).closest(".ag-bell-wrap").length) {
			$panel.prop("hidden", true);
			$btn.attr("aria-expanded", "false");
		}
	});

	load();   // badge on page load
});
