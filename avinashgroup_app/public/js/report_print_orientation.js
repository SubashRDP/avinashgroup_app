/*
 * Global Report Print Orientation Helper
 *
 * Three pieces of plumbing that work together:
 *
 * 1. window.askPrintOrientation(callback)
 *    Side-by-side Portrait/Landscape button dialog. Neither pre-selected.
 *    User clicks one — callback fires with the chosen orientation string.
 *
 * 2. Global hook on frappe.ui.Page.prototype.add_inner_button
 *    Any report registering a "Download PDF" inner button is wrapped so
 *    that on click, the captured download URL is held back, the orientation
 *    dialog is shown, and the URL is re-opened with &orientation=... appended.
 *    Works for every current and future report that uses the standard
 *    add_inner_button("Download PDF", ...) + window.open(url) pattern. No
 *    per-report JS edit required.
 *
 * 3. window.open shim
 *    a. Injects report_print_portrait.css into blank popup windows
 *       (Frappe's render_grid + custom print_report overrides write HTML
 *       into a blank popup that does NOT inherit app_include_css).
 *    b. Cooperates with (2): in capture mode it stashes the URL instead
 *       of opening, so the dialog can rewrite it.
 */

(function () {

	const PRINT_PORTRAIT_CSS = "/assets/avinashgroup_app/css/report_print_portrait.css?v=4";

	// ─────────────────────────────────────────────────────────────────
	// 1) Side-by-side orientation dialog
	// ─────────────────────────────────────────────────────────────────

	window.askPrintOrientation = function (callback) {
		if (typeof callback !== "function") return;

		const d = new frappe.ui.Dialog({
			title: __("Choose Orientation"),
			fields: [
				{ fieldname: "portrait", label: __("Portrait"), fieldtype: "Check", default: 0 },
				{ fieldname: "col_break", fieldtype: "Column Break" },
				{ fieldname: "landscape", label: __("Landscape"), fieldtype: "Check", default: 0 },
			],
			primary_action_label: __("Download"),
			primary_action(values) {
				let orient = null;
				if (values.portrait && !values.landscape) orient = "Portrait";
				else if (values.landscape && !values.portrait) orient = "Landscape";
				if (!orient) {
					frappe.msgprint(__("Please tick exactly one orientation"));
					return;
				}
				d.hide();
				callback(orient);
			},
		});

		// Mutual exclusion: ticking one unticks the other
		d.fields_dict.portrait.df.onchange = function () {
			if (d.get_value("portrait")) d.set_value("landscape", 0);
		};
		d.fields_dict.landscape.df.onchange = function () {
			if (d.get_value("landscape")) d.set_value("portrait", 0);
		};

		d.show();
	};

	// ─────────────────────────────────────────────────────────────────
	// 3) window.open shim — capture mode + blank-popup CSS injection
	// ─────────────────────────────────────────────────────────────────

	let _captureNextUrl = false;
	let _capturedUrl = null;

	function injectPrintCss(win) {
		if (!win || win.closed) return;
		try {
			if (!win.document || !win.document.head) return;
			if (win._rdpPrintCssInjected) return;
			const link = win.document.createElement("link");
			link.rel = "stylesheet";
			link.href = PRINT_PORTRAIT_CSS;
			win.document.head.appendChild(link);
			win._rdpPrintCssInjected = true;
		} catch (e) {
			// Cross-origin or other access error — ignore silently
		}
	}

	/**
	 * Browser-independent "fit to page width" for the popup preview.
	 * If a table inside .print-format is wider than its container, scale
	 * it down via CSS transform so it visually fits. Mimics Chrome's
	 * "Fit to page width" so the preview matches the eventual print
	 * regardless of which browser the user has.
	 */
	function fitContentToPage(win) {
		if (!win || win.closed) return;
		try {
			if (!win.document) return;
			const printFormat = win.document.querySelector(".print-format:not(.landscape)");
			if (!printFormat) return;

			const tables = printFormat.querySelectorAll("table");
			tables.forEach(function (table) {
				if (table._rdpFitted) return;
				const parent = table.parentElement;
				if (!parent) return;

				const naturalWidth = table.scrollWidth;
				const containerWidth = parent.clientWidth;
				if (!naturalWidth || !containerWidth) return;
				if (naturalWidth <= containerWidth) return;

				const scale = containerWidth / naturalWidth;
				if (scale >= 0.99) return;

				table.style.transformOrigin = "top left";
				table.style.transform = "scale(" + scale + ")";
				table.style.width = naturalWidth + "px";

				const naturalHeight = table.scrollHeight;
				const heightDiff = naturalHeight - (naturalHeight * scale);
				if (heightDiff > 0) {
					table.style.marginBottom = "-" + heightDiff + "px";
				}

				table._rdpFitted = true;
			});
		} catch (e) {
			// Cross-origin or other access error — ignore silently
		}
	}

	function processPopup(win) {
		injectPrintCss(win);
		fitContentToPage(win);
	}

	const _origOpen = window.open;
	window.open = function (url, target, features) {
		if (_captureNextUrl && typeof url === "string" && url && url !== "about:blank") {
			_capturedUrl = url;
			return null;
		}
		const w = _origOpen.call(window, url, target, features);
		if (w && (!url || url === "" || url === "about:blank")) {
			setTimeout(function () { processPopup(w); }, 50);
			setTimeout(function () { processPopup(w); }, 250);
			setTimeout(function () { processPopup(w); }, 700);
			setTimeout(function () { processPopup(w); }, 1500);
		}
		return w;
	};

	// ─────────────────────────────────────────────────────────────────
	// 2) Global hook — wrap any "Download PDF" inner button
	// ─────────────────────────────────────────────────────────────────

	function wrapDownloadAction(originalAction) {
		return function () {
			const ctx = this;
			const args = arguments;

			_captureNextUrl = true;
			_capturedUrl = null;
			try {
				originalAction.apply(ctx, args);
			} catch (e) {
				_captureNextUrl = false;
				_capturedUrl = null;
				throw e;
			}
			_captureNextUrl = false;

			const url = _capturedUrl;
			_capturedUrl = null;

			if (!url) return;

			window.askPrintOrientation(function (orientation) {
				const sep = url.indexOf("?") !== -1 ? "&" : "?";
				const newUrl = url + sep + "orientation=" + encodeURIComponent(orientation);
				_origOpen.call(window, newUrl);
			});
		};
	}

	function looksLikeDownloadPdfLabel(label) {
		if (!label) return false;
		const s = String(label).toLowerCase();
		return s.indexOf("download") !== -1 && s.indexOf("pdf") !== -1;
	}

	function installAddInnerButtonHook() {
		if (!frappe || !frappe.ui || !frappe.ui.Page || !frappe.ui.Page.prototype) return false;
		if (frappe.ui.Page.prototype._rdpInnerButtonHooked) return true;

		const _orig = frappe.ui.Page.prototype.add_inner_button;
		frappe.ui.Page.prototype.add_inner_button = function (label, action) {
			let wrappedAction = action;
			if (typeof action === "function" && looksLikeDownloadPdfLabel(label)) {
				wrappedAction = wrapDownloadAction(action);
			}
			const rest = Array.prototype.slice.call(arguments, 2);
			return _orig.apply(this, [label, wrappedAction].concat(rest));
		};

		frappe.ui.Page.prototype._rdpInnerButtonHooked = true;
		return true;
	}

	if (!installAddInnerButtonHook()) {
		const retry = setInterval(function () {
			if (installAddInnerButtonHook()) clearInterval(retry);
		}, 200);
		setTimeout(function () { clearInterval(retry); }, 15000);
	}

})();
