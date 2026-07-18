# Avinash Print Bridge

Prints raw ESC/P invoices from the ERP to a dot-matrix printer. Replaces QZ Tray.

## Install

Download **`PrintBridgeSetup.exe`** from the
[latest release](https://github.com/SubashRDP/avinashgroup_app/releases) and run it.
Attach the Epson and switch it on **first** — the installer creates the print
queue on the printer's own port and will tell you if it can't find it.

That's everything. No QZ Tray, no certificate, no browser setup. Reload the ERP
and print an invoice.

## What the installer does

1. Installs `print_bridge.exe` to `C:\Program Files\AvinashPrintBridge`.
2. Creates the **LQ310-RAW** queue (Generic / Text Only driver on the Epson's
   port). The stock Epson ESC/P V4 driver *swallows* RAW jobs — the spooler
   reports success and the head never moves. Generic / Text Only is a pure byte
   pipe.
3. Pre-grants Chrome/Edge local network access for the ERP origin, so no
   permission prompt appears.
4. Registers a login task so the agent is always running.

Uninstall from Add/Remove Programs reverses all of it except `config.json` and
the log.

## How it works

    ERP renders ESC/P  ->  browser  ->  127.0.0.1:8663  ->  RAW spooler  ->  LQ-310

The ERP already builds the ESC/P byte stream server-side
(`custom_code/printing/escp_*.py`). This agent only carries it the last hop.

## Why not QZ Tray

QZ Tray is a *generic* bridge — any website may connect to it, so it must ask
"Allow?" and needs a signing certificate plus a per-machine `override.crt` to
remember the answer. This agent accepts one origin and refuses everything else,
so there is nothing to prompt about and no certificate to manage.

It is also byte-exact. QZ Tray UTF-8-encodes the command string, mangling every
byte over 127 — which is why `escp_invoice.py` avoids `ESC $` positioning and
caps `ESC J` feeds at 127. This agent sends base64 of the exact bytes.

Chrome 142 broke QZ Tray's loopback connection too
([qzind/tray#1368](https://github.com/qzind/tray/issues/1368)); the installer's
policy key handles that here.

## Troubleshooting

**Log:** `%LOCALAPPDATA%\AvinashPrintBridge\print_bridge.log`

| Symptom | Cause |
| --- | --- |
| Installer says the queue couldn't be created | Epson not attached / not powered on. Connect it and re-run. |
| Prints fall back to QZ Tray behaviour | Agent isn't running. Check the "Avinash Print Bridge" task, or start it from the Start menu. |
| Chrome asks for local network permission | Policy key missing (rare). Click Allow once — Chrome remembers. |
| Spooler says printed, nothing moves | Job went to the Epson driver queue, not LQ310-RAW. Check the printer mapping in Print view. |

## Config

`%LOCALAPPDATA%\AvinashPrintBridge\config.json`, created on first run:

```json
{
  "port": 8663,
  "default_printer": "LQ310-RAW",
  "allowed_origins": ["https://ng-group.raindropinc.com"]
}
```

`allowed_origins` is the entire security model — the agent refuses every other
origin. Adding one here does **not** update the browser policy key; that is set
by the installer.

## Development

```bash
python print_bridge.py --dry-run   # writes jobs to a file instead of a printer
```

Works off-Windows, so the HTTP/CORS layer can be exercised without a printer.
`--configure` (create the queue) is Windows-only and called by the installer.
