// Login popup for customer portal users — shown once per browser session, on the
// first page after login, on BOTH the desk and the website portal.
//
// The server (Portal Announcement.get_login_popups) returns nothing for Guests and for
// any login not listed in a Customer's Portal Users table, so this script can be
// loaded everywhere without widening what anyone sees. Content is admin-entered
// (System Manager / Accounts Manager) and rendered as-is.

(function () {
	var SEEN_KEY = "ag_portal_announcement_shown"; // sessionStorage: once per browser session
	var METHOD =
		"avinashgroup_app.avinash_group_app.doctype.portal_announcement.portal_announcement.get_login_popups";

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

	function seen() {
		try {
			return !!sessionStorage.getItem(SEEN_KEY);
		} catch (e) {
			return false;
		}
	}
	function mark_seen() {
		try {
			sessionStorage.setItem(SEEN_KEY, "1");
		} catch (e) {
			/* private mode / storage blocked */
		}
	}

	whenReady(function () {
		if (frappe.session.user === "Guest") return;
		if (seen()) return;

		frappe.call({
			method: METHOD,
			callback: function (r) {
				var popups = (r && r.message) || [];
				// only burn the once-per-session flag once something actually shows
				if (popups.length) {
					mark_seen();
					render(popups);
				}
			},
		});
	});

	function inject_style() {
		if (document.getElementById("ag-popup-style")) return;
		var css =
			".ag-popup-backdrop{position:fixed;inset:0;z-index:2000;display:flex;" +
			"align-items:flex-start;justify-content:center;padding:24px;overflow-y:auto;" +
			"background:rgba(14,24,54,.55);}" +
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
			".ag-popup-body{padding:26px 24px 20px;}" +
			".ag-popup-card.is-custom .ag-popup-body{padding:0;}" +
			".ag-popup-title{margin:0 0 12px;font-size:19px;font-weight:600;color:#22357F;" +
			"padding-right:26px;}" +
			".ag-popup-card.is-custom .ag-popup-title{margin:0;padding:22px 40px 10px 24px;}" +
			".ag-popup-img{display:block;width:100%;height:auto;border-radius:10px;margin:12px 24px 14px;" +
			"width:calc(100% - 48px);}" +
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
				img +
				'<div class="ag-popup-body">' +
				title +
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
