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
	// Must mirror CHROME_PRINT_FORMATS in custom_code/printing/chrome_pdf.py.
	const NGI_FORMATS = [
		"Nepal Gas Invoice Pre-Printed",
		"Nepal Gas Invoice Plain Paper",
		"Nepal Gas Invoice A4 Proof",
		"Avinash Invoice Pre-Printed",
	];

	function patch(cls) {
		if (!cls || cls.prototype._ngi_patched) return cls;
		const orig = cls.prototype.printit;
		cls.prototype.printit = function () {
			if (NGI_FORMATS.includes(this.selected_format())) {
				this.render_page("/api/method/frappe.utils.print_format.download_pdf?");
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
