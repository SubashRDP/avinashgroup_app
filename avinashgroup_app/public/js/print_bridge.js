// Avinash Print Bridge client — raw ESC/P to the local agent, no QZ Tray.
//
// The ERP renders the ESC/P server-side; this carries it the last hop to the
// printer via the loopback agent (print_bridge/print_bridge.py). QZ Tray did
// this job but prompts on every session, needs a signing certificate and a
// per-machine override.crt, because it is a generic bridge any site may use.
// Our agent answers to this origin alone, so it needs none of that.
//
// 127.0.0.1, never "localhost": Firefox only exempted the localhost *name*
// from mixed-content in 84, but the IP literal has worked since 55. Chrome
// treats both as potentially trustworthy.
//
// Bytes go over as base64. btoa() wants a binary string — one char per byte,
// 0-255 — which is exactly what get_rendered_raw_commands returns. QZ Tray
// UTF-8-encoded that same string, mangling every byte over 127; that is why
// escp_invoice.py avoids ESC $ and caps ESC J at 127. Nothing here re-encodes.

frappe.provide("avinash.print_bridge");

(function () {
	const BASE = "http://127.0.0.1:8663";
	const TIMEOUT_MS = 2000;

	let probe = null; // cached availability probe

	function req(path, options) {
		const ctl = new AbortController();
		const timer = setTimeout(() => ctl.abort(), TIMEOUT_MS);
		return fetch(BASE + path, Object.assign({ signal: ctl.signal }, options || {}))
			.then((r) => r.json().then((body) => ({ ok: r.ok, body })))
			.finally(() => clearTimeout(timer));
	}

	// The agent's configured default queue, learned from /ping. Falls back to
	// LQ310-RAW (what the installer creates) until the probe answers.
	avinash.print_bridge.default_printer = "LQ310-RAW";

	// Resolves true when the agent answers. Cached: a machine either has the
	// agent or it does not, and re-probing on every print would add a round
	// trip to the hot path. Reload picks up a freshly installed agent.
	avinash.print_bridge.available = function () {
		if (!probe) {
			probe = req("/ping")
				.then((r) => {
					if (r.ok && r.body.ok) {
						if (r.body.default_printer)
							avinash.print_bridge.default_printer = r.body.default_printer;
						return true;
					}
					return false;
				})
				.catch(() => false); // not installed / not running
		}
		return probe;
	};

	avinash.print_bridge.printers = function () {
		return req("/printers")
			.then((r) => (r.ok && r.body.ok ? r.body.printers : []))
			.catch(() => []);
	};

	// raw_commands: binary string from get_rendered_raw_commands.
	avinash.print_bridge.print = function (printer, raw_commands) {
		let data_b64;
		try {
			data_b64 = btoa(raw_commands);
		} catch (e) {
			// btoa throws if any char is >255, which would mean the generator
			// emitted something that is not a byte stream. Surface it rather
			// than silently printing corrupted output.
			return Promise.reject(new Error(__("Print data is not a byte stream: {0}", [e.message])));
		}
		return req("/print", {
			method: "POST",
			headers: { "Content-Type": "application/json" },
			body: JSON.stringify({ printer: printer, data_b64: data_b64 }),
		}).then((r) => {
			if (!r.ok || !r.body.ok) {
				throw new Error(r.body.error || __("Print bridge rejected the job"));
			}
			return r.body;
		});
	};

	// One place every raw-print entry point lands (form printer icon, Print
	// view button, print-on-submit). QZ Tray is gone: if the agent is not on
	// this machine we tell the user to install it, we never launch QZ.
	let _not_installed_shown = false;
	avinash.print_bridge.show_not_installed = function () {
		if (_not_installed_shown) return; // don't stack on repeated clicks
		_not_installed_shown = true;
		setTimeout(() => (_not_installed_shown = false), 4000);
		frappe.msgprint({
			title: __("Print Bridge not installed on this computer"),
			indicator: "orange",
			message: __(
				"Raw invoices print through the Avinash Print Bridge, which isn't running on this computer yet.<br><br>1. Install <b>PrintBridgeSetup.exe</b> (printer attached &amp; switched on).<br>2. Reload this page.<br><br><a href='{0}' target='_blank' rel='noopener'>Download the installer</a>",
				["https://github.com/SubashRDP/avinashgroup_app/releases/latest"]
			),
		});
	};

	// Render (doctype, name) with print_format server-side, then send the exact
	// bytes to the agent. `printer` optional — defaults to the agent's queue.
	avinash.print_bridge.print_raw_doc = function (doctype, name, print_format, printer) {
		frappe.call({
			method: "frappe.www.printview.get_rendered_raw_commands",
			args: { doc: doctype, name: name, print_format: print_format },
			callback: function (r) {
				if (r.exc || !r.message) return;
				avinash.print_bridge.available().then(function (has_bridge) {
					if (!has_bridge) {
						avinash.print_bridge.show_not_installed();
						return;
					}
					const target = printer || avinash.print_bridge.default_printer;
					avinash.print_bridge
						.print(target, r.message.raw_commands)
						.then(function () {
							frappe.show_alert(
								{ message: __("Printing via {0}", [target]), indicator: "green" },
								5
							);
						})
						.catch(function (err) {
							frappe.show_alert(
								{ message: __("Print bridge: {0}", [err.message]), indicator: "red" },
								10
							);
						});
				});
			},
		});
	};
})();
