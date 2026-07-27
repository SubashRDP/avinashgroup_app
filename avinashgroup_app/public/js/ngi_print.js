// The Nepal Gas continuous-form invoices are mm-exact overlays that only hold
// when rendered by the chrome pdf_generator (custom_code/printing/chrome_pdf.py).
// The desk Print button instead browser-prints the preview HTML on whatever
// paper the dialog defaults to (A4 portrait), which rotates and rescales the
// whole form. For these formats, route Print to the same download_pdf URL the
// PDF button uses; chrome_pdf.download_pdf forces the chrome generator
// server-side. render_pdf() is avoided on purpose: it calls
// is_wkhtmltopdf_valid(), which msgprints a warning on every print because
// this server ships the unpatched-Qt wkhtmltopdf.

(function () {
	// Fallback only, for a format doc that hasn't reached locals yet. The real
	// routing rule is the format's own pdf_generator field (see is_chrome_format)
	// — the same rule company_print.js uses — so new chrome formats need no edit
	// here. This list once claimed to mirror CHROME_PRINT_FORMATS in
	// custom_code/printing/chrome_pdf.py and had drifted from it; that is the
	// bug that sent the seven A5 Overlay formats to the browser dialog.
	const NGI_FORMATS = [
		"Nepal Gas Invoice Pre-Printed",
		"Nepal Gas Invoice Plain Paper",
		"Nepal Gas Invoice A4 Proof",
		"Nepal Gas Invoice A4 Portrait",
		"Avinash Invoice Pre-Printed",
		"Grishma Invoice Pre-Printed",
	];

	function is_chrome_format(view) {
		const format = view.selected_format();
		const doc = view.get_print_format ? view.get_print_format(format) : null;
		if (doc && doc.pdf_generator) return doc.pdf_generator === "chrome";
		return NGI_FORMATS.includes(format);
	}

	function patch(cls) {
		if (!cls || cls.prototype._ngi_patched) return cls;
		const orig = cls.prototype.printit;
		cls.prototype.printit = function () {
			if (is_chrome_format(this)) {
				// `_ts` is a cache buster: the URL is otherwise identical on every
				// print of an invoice, so Chrome serves its cached PDF and never
				// reaches the server. Frappe filters call kwargs to the handler's
				// signature, so the extra param never reaches the render.
				this.render_page(
					"/api/method/frappe.utils.print_format.download_pdf?_ts=" + Date.now() + "&"
				);
				frappe.show_alert(
					{
						message: __("PDF opened in a new tab."),
						subtitle: __(
							'Print it at 100% / Actual size on the 9.5" × 5.5" form — never "Fit to page".'
						),
						indicator: "blue",
					},
					8
				);
				return;
			}
			// Raw ESC/P formats: stock printit() sends these over QZ Tray. QZ is
			// gone — route through the Print Bridge instead (same transport the
			// form printer icon uses), so the Print view button behaves the same
			// and never launches QZ. Non-raw formats keep the stock dialog.
			if (
				this.is_raw_printing &&
				this.is_raw_printing() &&
				window.avinash &&
				avinash.print_bridge
			) {
				avinash.print_bridge.print_raw_doc(
					this.frm.doc.doctype,
					this.frm.doc.name,
					this.selected_format()
				);
				return;
			}
			return orig.apply(this, arguments);
		};
		cls.prototype._ngi_patched = true;
		return cls;
	}

	// print/print.js loads lazily on first visit to the print page and assigns
	// frappe.ui.form.PrintView then; intercept the assignment so the patch is
	// applied no matter when (or whether) that script loads.
	let PV = patch(frappe.ui.form.PrintView);
	Object.defineProperty(frappe.ui.form, "PrintView", {
		get() {
			return PV;
		},
		set(cls) {
			PV = patch(cls);
		},
		configurable: true,
	});
})();
