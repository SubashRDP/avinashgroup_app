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
	// A print may legitimately take far longer than a probe: the agent
	// self-heals a missing queue with PowerShell (5-10s) before spooling —
	// exactly the "installed without the printer, first print" path. Aborting
	// at 2s showed tills "signal is aborted without reason" while the job went
	// on to print fine behind the abort — and a retry printed it twice.
	const PRINT_TIMEOUT_MS = 60000;

	let probe = null; // cached availability probe

	function req(path, options, timeout_ms) {
		const ctl = new AbortController();
		const timer = setTimeout(() => ctl.abort(), timeout_ms || TIMEOUT_MS);
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
		return req(
			"/print",
			{
				method: "POST",
				headers: { "Content-Type": "application/json" },
				body: JSON.stringify({ printer: printer, data_b64: data_b64 }),
			},
			PRINT_TIMEOUT_MS
		)
			.then((r) => {
				if (!r.ok || !r.body.ok) {
					throw new Error(r.body.error || __("Print bridge rejected the job"));
				}
				return r.body;
			})
			.catch((err) => {
				if (err && err.name === "AbortError") {
					// Aborting the request does NOT cancel the job server-side.
					throw new Error(
						__(
							"No answer from the Print Bridge after {0} seconds. The invoice may still print — wait for the printer before trying again, or a duplicate copy can come out.",
							[PRINT_TIMEOUT_MS / 1000]
						)
					);
				}
				throw err;
			});
	};

	// ------------------------------------------------- failure diagnosis ----
	// Invisible while printing works. When it doesn't, work out WHICH way it is
	// broken and show numbered fix steps for that case only — a till operator
	// gets one box that tells them (or IT) exactly what to do, not a generic
	// "not installed" for every possible cause.

	const LOG_PATH = "C:\\ProgramData\\AvinashPrintBridge\\print_bridge.log";
	const CONFIG_PATH = "C:\\ProgramData\\AvinashPrintBridge\\config.json";
	// Direct asset link, updated per print-bridge release. NOT releases/latest:
	// that repo-wide slot belongs to K40 Bridge (its releases default
	// make_latest, ours sets false), so "latest" serves the wrong product.
	const DOWNLOAD_URL =
		"https://github.com/SubashRDP/avinashgroup_app/releases/download/print-bridge-v0.5.2/PrintBridgeSetup.exe";

	// Resolves true if ANYTHING is listening on the port. mode:'no-cors' is the
	// one probe a page can make that separates "connection refused" (rejects)
	// from "answered but CORS/origin blocked us" (resolves opaque) — a normal
	// fetch rejects identically in both cases.
	function listener_exists() {
		const ctl = new AbortController();
		const timer = setTimeout(() => ctl.abort(), TIMEOUT_MS);
		return fetch(BASE + "/ping", { mode: "no-cors", signal: ctl.signal })
			.then(() => true)
			.catch(() => false)
			.finally(() => clearTimeout(timer));
	}

	let _problem_shown = false;
	function show_problem(title, html) {
		if (_problem_shown) return; // don't stack on repeated clicks
		_problem_shown = true;
		setTimeout(() => (_problem_shown = false), 4000);
		frappe.msgprint({ title: title, indicator: "orange", message: html });
	}

	function show_unreachable() {
		show_problem(
			__("Print Bridge is not running on this computer"),
			__(
				"Raw invoices print through the Avinash Print Bridge agent, and nothing is answering on this computer (127.0.0.1:8663).<br><br><b>1.</b> Open Task Manager (Ctrl+Shift+Esc) → Details, look for <b>print_bridge.exe</b>.<br><b>2.</b> Not there → start it: Start menu → <b>Avinash Print Bridge</b>, then print again.<br><b>3.</b> Still not there after starting → it is not installed (or crashing): <a href='{0}' target='_blank' rel='noopener'>install the latest PrintBridgeSetup.exe</a>, then reload this page.<br><b>4.</b> If it keeps dying, send the log: <code>{1}</code> — and check <code>PORT_CONFLICT.txt</code> in the same folder: if present, another program is occupying the port and that file has the exact steps.",
				[DOWNLOAD_URL, LOG_PATH]
			)
		);
	}

	function show_blocked() {
		show_problem(
			__("Something is blocking the Print Bridge on this computer"),
			__(
				"Port 8663 answered, but this site cannot talk to it. Two possible causes — check in order:<br><br><b>A. Another program is using port 8663.</b><br>&nbsp;&nbsp;1. Task Manager → Details: is <b>print_bridge.exe</b> running? If NOT, but the port still answers, it is a foreign program.<br>&nbsp;&nbsp;2. Command Prompt (as administrator): <code>netstat -ano | findstr :8663</code> — the last column is the PID; find it in Task Manager → Details to see which program.<br>&nbsp;&nbsp;3. Close/reconfigure that program, then start <b>Avinash Print Bridge</b> from the Start menu.<br><br><b>B. This site is not on the Print Bridge allow-list.</b> (Only applies if print_bridge.exe IS running.)<br>&nbsp;&nbsp;1. Open <code>{0}</code> in Notepad.<br>&nbsp;&nbsp;2. Add <code>{1}</code> to <code>allowed_origins</code>.<br>&nbsp;&nbsp;3. Restart the agent (Start menu → Avinash Print Bridge).<br><br>If the browser showed a <b>local network access</b> permission prompt, choose Allow and print again. Still stuck → send the log: <code>{2}</code>",
				[CONFIG_PATH, window.location.origin, LOG_PATH]
			)
		);
	}

	function show_print_failed(err_message) {
		// The agent is reachable — ask it what is actually wrong and word the
		// box for the specific finding.
		req("/diag")
			.then(function (r) {
				const d = (r.ok && r.body.ok && r.body.diag) || {};
				if (d.queue_exists === false && d.epson_seen === false) {
					show_problem(
						__("Printer not connected"),
						__(
							"The Epson LQ-310 is not visible to Windows.<br><br><b>1.</b> Check the printer's power switch and both cable ends (power + USB).<br><b>2.</b> Print again — the print queue sets itself up automatically once the printer is seen. No reinstall needed.<br><br>If it is plugged in and on but this message persists, try a different USB port, then send the log: <code>{0}</code>",
							[LOG_PATH]
						)
					);
				} else if (d.queue_exists === false) {
					show_problem(
						__("Print queue missing"),
						__(
							"Windows sees the Epson, but the <b>{0}</b> queue is missing and the agent could not recreate it (it usually needs to be running elevated — the auto-start task does this).<br><br><b>1.</b> Restart this computer, then print again (the boot task runs the agent with the rights to fix the queue).<br><b>2.</b> If it still fails, re-run <a href='{1}' target='_blank' rel='noopener'>PrintBridgeSetup.exe</a> with the printer attached and on.<br><b>3.</b> Still stuck → send the log: <code>{2}</code><br><br>Agent said: {3}",
							[d.default_printer || "LQ310-RAW", DOWNLOAD_URL, LOG_PATH, frappe.utils.escape_html(err_message || "")]
						)
					);
				} else {
					show_problem(
						__("Print failed"),
						__(
							"The Print Bridge is running and the print queue exists, but the job failed:<br><br><b>{0}</b><br><br><b>1.</b> Check the printer is online (no blinking error light, paper loaded).<br><b>2.</b> Print again.<br><b>3.</b> If it keeps failing, send the log: <code>{1}</code>",
							[frappe.utils.escape_html(err_message || ""), LOG_PATH]
						)
					);
				}
			})
			.catch(function () {
				// /diag itself unreachable (agent died between print and now, or
				// pre-/diag agent version) — fall back to the raw error.
				show_problem(
					__("Print failed"),
					__("<b>{0}</b><br><br>If this repeats, send the log: <code>{1}</code>", [
						frappe.utils.escape_html(err_message || ""),
						LOG_PATH,
					])
				);
			});
	}

	// One place every raw-print entry point lands (form printer icon, Print
	// view button, print-on-submit). QZ Tray is gone: if the agent is not on
	// this machine we diagnose and instruct, we never launch QZ. Kept under the
	// old name for the callers that already use it.
	avinash.print_bridge.show_not_installed = function () {
		listener_exists().then(function (exists) {
			if (exists) show_blocked();
			else show_unreachable();
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
							show_print_failed(err.message);
						});
				});
			},
		});
	};
})();
