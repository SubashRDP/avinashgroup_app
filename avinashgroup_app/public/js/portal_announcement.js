// Announcement popup for customer portal users, on BOTH the desk and the website
// portal. It appears on exactly two occasions:
//
//   1. a fresh login — the "sid" session cookie differs from the one we last
//      showed for, so logging out and back in brings it up again;
//   2. a browser reload (F5 / the reload button).
//
// Clicking through to another portal page is an ordinary navigation and does NOT
// re-show it, which is the whole point of the two checks below.
//
// The server (Portal Announcement.get_login_popups) returns nothing for Guests and for
// any login not listed in a Customer's Portal Users table, so this script can be
// loaded everywhere without widening what anyone sees. Content is admin-entered
// (System Manager / Accounts Manager) and rendered as-is.

(function () {
	var METHOD =
		"avinashgroup_app.avinash_group_app.doctype.portal_announcement.portal_announcement.get_login_popups";
	var KEY = "ag_portal_announcement_session"; // localStorage: session_key last shown for

	// "reload" only when the user actually reloaded. A link click is "navigate",
	// the back/forward buttons are "back_forward".
	function is_reload() {
		try {
			var entries = performance.getEntriesByType("navigation");
			if (entries && entries.length) return entries[0].type === "reload";
			// pre-Navigation-Timing-2 browsers
			if (performance.navigation) return performance.navigation.type === 1;
		} catch (e) {
			/* timing API unavailable */
		}
		return false;
	}

	function read_key() {
		try {
			return localStorage.getItem(KEY);
		} catch (e) {
			return null;
		}
	}
	function write_key(key) {
		try {
			localStorage.setItem(KEY, key);
		} catch (e) {
			/* private mode / storage blocked */
		}
	}

	// Loaded from both app_include_js (desk) and web_include_js (portal). On the
	// desk this file can parse before frappe.call exists, so wait for it rather
	// than bailing once.
	function whenReady(fn, tries) {
		tries = tries || 0;
		if (
			window.frappe &&
			frappe.session &&
			frappe.session.user &&
			typeof frappe.call === "function" &&
			document.body
		) {
			return fn();
		}
		if (tries > 150) return; // ~30s, then give up
		setTimeout(function () {
			whenReady(fn, tries + 1);
		}, 200);
	}

	whenReady(function () {
		if (frappe.session.user === "Guest") return;
		if (document.querySelector(".ag-popup-backdrop")) return; // already open on this page

		var reloaded = is_reload(); // read before the call — it describes this page load

		frappe.call({
			method: METHOD,
			callback: function (r) {
				var data = (r && r.message) || {};
				var key = data.session_key || "";
				var popups = data.popups || [];

				// a key we have not recorded yet means this is a login we have not
				// greeted — including one made right after a logout
				var fresh_login = !!key && read_key() !== key;
				if (key) write_key(key);

				if ((fresh_login || reloaded) && popups.length) render(popups);
			},
		});
	});

	function inject_style() {
		if (document.getElementById("ag-popup-style")) return;
		var css =
			".ag-popup-backdrop{position:fixed;inset:0;z-index:2000;display:flex;" +
			"align-items:flex-start;justify-content:center;padding:24px;overflow-y:auto;" +
			"background:rgba(14,24,54,.5);" +
			"-webkit-backdrop-filter:blur(14px);backdrop-filter:blur(14px);}" +
			".ag-popup-card{position:relative;width:100%;max-width:520px;margin:auto;" +
			"background:#fff;border-radius:14px;" +
			"box-shadow:0 30px 70px -24px rgba(14,24,54,.6);overflow:hidden;" +
			'font-family:"Barlow",system-ui,-apple-system,sans-serif;}' +
			// custom HTML sizes to its own content (email-style layouts run wide)
			".ag-popup-card.is-custom{width:auto;max-width:min(92vw,760px);}" +
			".ag-popup-close{position:absolute;top:10px;right:10px;width:30px;height:30px;" +
			"display:flex;align-items:center;justify-content:center;" +
			"border:1px solid rgba(0,0,0,.15);border-radius:50%;background:#fff;" +
			"font-size:18px;line-height:1;color:#000;cursor:pointer;z-index:2;}" +
			".ag-popup-close:hover{background:#000;color:#fff;border-color:#000;}" +
			".ag-popup-body{padding:16px 24px 20px;}" +
			".ag-popup-card.is-custom .ag-popup-body{padding:0;}" +
			// title sits at the very top of the card, above the image
			".ag-popup-title{margin:0;font-size:19px;font-weight:600;color:#22357F;" +
			"padding:20px 46px 12px 24px;}" +
			".ag-popup-img{display:block;width:calc(100% - 48px);height:auto;border-radius:10px;" +
			"margin:0 24px 4px;}" +
			// in custom mode the image is a full-bleed banner under the title
			".ag-popup-card.is-custom .ag-popup-img{border-radius:0;margin:0;width:100%;}" +
			// in custom mode the image is a full-bleed banner above the content
			".ag-popup-card.is-custom .ag-popup-img{border-radius:0;margin:0;width:100%;}" +
			".ag-popup-msg{font-size:14.5px;line-height:1.55;color:#0E1836;}" +
			".ag-popup-msg img{max-width:100%;height:auto;}" +
			// oversized Custom HTML (fixed-width email layouts) is scaled to fit the
			// viewport so it shows whole with no scrollbar — desktop and phone alike
			".ag-popup-scaler{overflow:hidden;margin:auto;}" +
			".ag-popup-scaled{width:max-content;transform-origin:top left;}" +
			"@media (max-width:600px){" +
			".ag-popup-backdrop{padding:10px;}" +
			".ag-popup-card{max-width:100%;}" +
			".ag-popup-title{font-size:17px;}" +
			".ag-popup-card.is-custom .ag-popup-title{padding:18px 40px 8px 16px;}" +
			"}";
		var s = document.createElement("style");
		s.id = "ag-popup-style";
		s.textContent = css;
		document.head.appendChild(s);
	}

	// Popups are shown one at a time: dismissing the current one (× / backdrop /
	// Esc) brings up the next, in priority order, until the queue is empty.
	function render(popups) {
		inject_style();

		var queue = popups.slice();

		function next() {
			var p = queue.shift();
			if (!p) return;

			var img = p.image
				? '<img class="ag-popup-img" src="' + encodeURI(p.image) + '">'
				: "";
			var title = p.title ? '<h3 class="ag-popup-title"></h3>' : "";
			var bodyInner = p.custom
				? '<div class="ag-popup-scaler"><div class="ag-popup-scaled">' +
				  (p.html || "") +
				  "</div></div>"
				: p.html || "";

			var backdrop = document.createElement("div");
			backdrop.className = "ag-popup-backdrop";
			backdrop.innerHTML =
				'<div class="ag-popup-card' +
				(p.custom ? " is-custom" : "") +
				'" role="dialog" aria-modal="true">' +
				'<button class="ag-popup-close" aria-label="Close">×</button>' +
				title +
				img +
				'<div class="ag-popup-body">' +
				bodyInner +
				"</div>" +
				"</div>";

			if (p.title)
				backdrop.querySelector(".ag-popup-title").textContent = p.title;

			// scale an oversized Custom HTML down so it fits the screen with no
			// horizontal scroll (re-run on rotate / resize)
			var scaled = backdrop.querySelector(".ag-popup-scaled");
			var scaler = backdrop.querySelector(".ag-popup-scaler");
			function fit() {
				if (!scaled || !scaler) return;
				scaled.style.transform = "none";
				scaler.style.width = scaler.style.height = "";
				var natural = scaled.scrollWidth || scaled.offsetWidth;
				if (!natural) return;
				var vw = document.documentElement.clientWidth || window.innerWidth;
				var avail = Math.min(760, vw - 24);
				var s = Math.min(1, avail / natural);
				scaled.style.transform = "scale(" + s + ")";
				scaler.style.width = Math.ceil(natural * s) + "px";
				scaler.style.height = Math.ceil(scaled.offsetHeight * s) + "px";
			}
			var fitTimer;
			function onResize() {
				clearTimeout(fitTimer);
				fitTimer = setTimeout(fit, 120);
			}

			function close() {
				backdrop.remove();
				document.removeEventListener("keydown", onKey);
				window.removeEventListener("resize", onResize);
				window.removeEventListener("orientationchange", onResize);
				next();
			}
			function onKey(e) {
				if (e.key === "Escape") close();
			}

			backdrop.querySelector(".ag-popup-close").addEventListener("click", close);
			backdrop.addEventListener("click", function (e) {
				if (e.target === backdrop) close();
			});
			document.addEventListener("keydown", onKey);
			window.addEventListener("resize", onResize);
			window.addEventListener("orientationchange", onResize);

			document.body.appendChild(backdrop);
			fit();
		}

		next();
	}
})();
