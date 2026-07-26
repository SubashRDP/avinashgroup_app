// Copyright (c) 2026, Raindrop and contributors
// For license information, please see license.txt

// Calibration bench for the pre-printed A5 overlay invoice formats.
//
// Everything on this page is read from the site it is running on: the formats
// come from whatever is installed here, the invoice comes from a Link field
// searching live data, and the URLs are built against window.location.origin.
// Nothing is hardcoded, because a demo site and a live site legitimately hold
// different formats, different invoices and different routing.

frappe.pages["overlay-print-test"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Overlay Print Test"),
		single_column: true,
	});
	wrapper.overlay_print_test = new OverlayPrintTest(page);
};

const API = "avinashgroup_app.custom_code.printing.test_bench";

class OverlayPrintTest {
	constructor(page) {
		this.page = page;
		this.controls = {};
		this.formats = [];

		this.page.set_indicator(frappe.session.site_name || "", "blue");
		this.render_shell();
		this.make_controls();
		this.load();

		this.page.set_primary_action(__("Refresh"), () => this.load(), "refresh");
	}

	// ---------------------------------------------------------------- layout

	render_shell() {
		this.page.main.html(`
			<div class="opt-wrap">
				<div class="opt-controls"></div>
				<div class="opt-body">
					<div class="text-muted">${__("Loading…")}</div>
				</div>
				<div class="opt-help"></div>
			</div>
		`);
		this.$body = this.page.main.find(".opt-body");
		this.$help = this.page.main.find(".opt-help");
		this.inject_style();
	}

	inject_style() {
		if (document.getElementById("opt-style")) return;
		const css = `
			.opt-wrap { padding: 0 0 60px; }
			.opt-controls { display: grid; gap: 0 15px;
				grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
				margin-bottom: 12px; }
			.opt-table { width: 100%; border-collapse: collapse; margin-top: 4px; }
			.opt-table th { font-size: var(--text-xs); text-transform: uppercase;
				letter-spacing: .04em; color: var(--text-muted); font-weight: 600;
				text-align: left; padding: 8px 10px;
				border-bottom: 1px solid var(--border-color); }
			.opt-table td { padding: 10px; border-bottom: 1px solid var(--border-color);
				vertical-align: middle; }
			.opt-fmt { font-weight: 600; }
			.opt-meta { display: block; font-family: var(--font-stack-mono, monospace);
				font-size: var(--text-xs); color: var(--text-muted); margin-top: 2px; }
			.opt-btns { display: flex; gap: 6px; flex-wrap: wrap; }
			.opt-problem { display: block; margin-top: 4px; font-size: var(--text-xs);
				color: var(--red-600, #c0392b); }
			.opt-routed { font-size: var(--text-xs); color: var(--text-muted); }
			.opt-help { margin-top: 22px; }
			.opt-help ol { padding-left: 18px; }
			.opt-help li { margin-bottom: 6px; }
		`;
		$(`<style id="opt-style">${css}</style>`).appendTo(document.head);
	}

	make_controls() {
		const $parent = this.page.main.find(".opt-controls");

		const add = (fieldname, df) => {
			const $col = $('<div class="opt-col"></div>').appendTo($parent);
			const c = frappe.ui.form.make_control({
				parent: $col,
				df: Object.assign({ fieldname }, df),
				render_input: true,
			});
			c.refresh();
			this.controls[fieldname] = c;
			return c;
		};

		// Link field: searches this site's invoices live. No hardcoded names.
		add("invoice", {
			fieldtype: "Link",
			label: __("Invoice"),
			options: "Sales Invoice",
			// only submitted invoices can be printed for real
			get_query: () => ({ filters: { docstatus: 1 } }),
			change: () => this.draw(),
		});

		add("ox", {
			fieldtype: "Float",
			label: __("Shift right (mm)"),
			description: __("− for left"),
			change: () => this.draw(),
		});

		add("oy", {
			fieldtype: "Float",
			label: __("Shift down (mm)"),
			description: __("− for up"),
			change: () => this.draw(),
		});

		// Turns the print to cancel a driver that rotates it. Applies to every
		// button, so what you Print is what you previewed.
		add("rot", {
			fieldtype: "Select",
			label: __("Rotate"),
			options: ["0", "90", "180", "270"],
			default: "0",
			change: () => this.draw(),
		});

		// Server-side queues. Empty on a machine with no printer, which is the
		// normal case for a branch PC — the PDF button is for them.
		add("printer", {
			fieldtype: "Select",
			label: __("Printer (on the server)"),
			options: [],
		});
	}

	// ------------------------------------------------------------------ data

	load() {
		frappe.call({ method: `${API}.get_printers` }).then((p) => {
			const { printers = [], default: def } = p.message || {};
			this.printers = printers;
			const c = this.controls.printer;
			c.df.options = printers;
			c.refresh();
			if (def) c.set_value(def);
			else if (printers.length) c.set_value(printers[0]);
			this.draw();
		});

		frappe.call({ method: `${API}.get_overlay_formats` }).then((r) => {
			this.formats = r.message || [];
			if (!this.controls.invoice.get_value()) {
				frappe.call({ method: `${API}.get_sample_invoice` }).then((s) => {
					if (s.message) this.controls.invoice.set_value(s.message.name);
					else this.draw();
				});
			} else {
				this.draw();
			}
		});
	}

	// Send it to the server's printer. Nothing between here and the paper can
	// rescale it — no dialog, no "fit to page", no wrong tray.
	print_now(format, $btn) {
		const invoice = this.controls.invoice.get_value();
		if (!invoice) return;

		$btn.prop("disabled", true);
		frappe.call({
			method: `${API}.print_now`,
			args: Object.assign(this.params({ format }), {
				printer: this.controls.printer.get_value(),
			}),
			freeze: true,
			freeze_message: __("Sending to printer…"),
		})
			.then((r) => {
				if (!r.message) return;
				frappe.show_alert(
					{
						message: __("Sent to {0}", [r.message.printer]),
						subtitle: r.message.job || "",
						indicator: "green",
					},
					5
				);
			})
			.always(() => $btn.prop("disabled", false));
	}

	// ------------------------------------------------------------------ urls

	params(extra) {
		const p = Object.assign(
			{
				doctype: "Sales Invoice",
				name: this.controls.invoice.get_value() || "",
				no_letterhead: 1,
			},
			extra || {}
		);
		const ox = flt(this.controls.ox.get_value());
		const oy = flt(this.controls.oy.get_value());
		const rot = cint(this.controls.rot.get_value());
		if (ox) p.ox = ox;
		if (oy) p.oy = oy;
		if (rot) p.rot = rot;
		return p;
	}

	// On screen only. No trigger_print and no download cmd, so print_count.py's
	// is_actual_print() is false and the IRD counter does not move.
	preview_url(format) {
		const p = this.params({ format, trigger_print: 0 });
		return `/printview?${$.param(p)}`;
	}

	// The real PDF. This IS a print: cmd is in PRINT_OUTPUT_CMDS.
	pdf_url(format, extra) {
		const p = this.params(Object.assign({ format }, extra || {}));
		return `/api/method/frappe.utils.print_format.download_pdf?${$.param(p)}`;
	}

	// ---------------------------------------------------------------- render

	draw() {
		if (!this.formats.length) {
			this.$body.html(
				`<div class="text-muted">${__(
					"No overlay print formats are installed on this site."
				)}</div>`
			);
			return;
		}

		const invoice = this.controls.invoice.get_value();
		if (!invoice) {
			this.$body.html(
				`<div class="text-muted">${__("Pick an invoice to build the links.")}</div>`
			);
			return;
		}

		const rows = this.formats.map((f) => this.row(f)).join("");
		this.$body.html(`
			<table class="opt-table">
				<thead>
					<tr>
						<th>${__("Format / roll")}</th>
						<th>${__("Actions")}</th>
					</tr>
				</thead>
				<tbody>${rows}</tbody>
			</table>
		`);

		// Print is a server call, not a link, so it is wired after render.
		this.$body.find("[data-print]").on("click", (e) => {
			const $b = $(e.currentTarget);
			this.print_now($b.attr("data-print"), $b);
		});

		this.draw_help();
	}

	row(f) {
		const esc = frappe.utils.escape_html;
		const meta = [f.form ? `form='${f.form}'` : null, f.module]
			.filter(Boolean)
			.map(esc)
			.join("  ·  ");

		const routed = f.companies.length
			? `<span class="opt-routed">${__("routed for")}: ${esc(f.companies.join(", "))}</span>`
			: `<span class="opt-routed">${__("not routed to any company")}</span>`;

		const problems = f.problems
			.map((p) => `<span class="opt-problem">⚠ ${esc(p)}</span>`)
			.join("");

		const btn = (cls, label, href, title) =>
			`<a class="btn btn-xs ${cls}" href="${esc(href)}" target="_blank" rel="noopener" title="${esc(title)}">${esc(label)}</a>`;

		// Straight to the server's queue — no dialog, so nothing can rescale it.
		const print_btn = this.printers && this.printers.length
			? `<button class="btn btn-xs btn-primary" data-print="${esc(f.format)}"
				title="${esc(__("Send straight to the server's printer. Counts as a print."))}">${esc(__("Print"))}</button>`
			: `<button class="btn btn-xs btn-default" disabled
				title="${esc(__("No printer on the server — use PDF and print it yourself."))}">${esc(__("Print"))}</button>`;

		return `
			<tr>
				<td>
					<div class="opt-fmt">${esc(f.format)}</div>
					<span class="opt-meta">${meta}</span>
					${routed}
					${problems}
				</td>
				<td>
					<div class="opt-btns">
						${btn("btn-default", __("Preview"), this.preview_url(f.format), __("On-screen render. Free — does not count as a print."))}
						${btn("btn-default", __("PDF"), this.pdf_url(f.format), __("The real PDF, to print yourself at 100%. Counts as a print."))}
						${btn("btn-default", __("Guide"), this.pdf_url(f.format, { guide: 1 }), __("Outlines every field box and the sheet edge. Counts as a print."))}
						${print_btn}
					</div>
				</td>
			</tr>
		`;
	}

	draw_help() {
		this.$help.html(`
			<h5>${__("How to use this")}</h5>
			<ol>
				<li>${__(
					"<b>Preview</b> — on-screen render, free and unlimited. Check the data is right before spending a form."
				)}</li>
				<li>${__(
					"<b>PDF</b> — in the PDF tab press Ctrl+P and set Scale to <b>100% / Actual size</b> (never Fit to page), paper to <b>241.3 × 139.7 mm</b>, margins <b>None</b>."
				)}</li>
				<li>${__(
					"<b>Print</b> — goes straight to the server's printer with scaling forbidden, so nothing can shrink it. Only the server's own queues; a branch PC should use PDF."
				)}</li>
				<li>${__(
					"<b>Came out sideways?</b> Set Rotate to 90, 180 or 270 and print again on a scrap form. Keep whichever comes out upright — that becomes the permanent rot for this machine."
				)}</li>
				<li>${__(
					"<b>A few mm off?</b> Press <b>Guide</b> and print it on a real form — every field is outlined red, the sheet edge blue. Type millimetres into the shift boxes above and press Guide again until it lines up."
				)}</li>
			</ol>
			<p class="text-muted">${__(
				"Only ever change the shift values. Individual field positions are ruler measurements of the form and live in custom_code/printing/escp_*.py — editing one to fix a whole-sheet shift breaks that field for everybody."
			)}</p>
		`);
	}
}
