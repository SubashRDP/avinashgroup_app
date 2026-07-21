# Print Bridge — one install, all 4 sites (deployment & verification)

Goal: install **once** per print machine, and all four ERP sites print raw
dot-matrix invoices — no QZ Tray, no per-site setup, no browser prompt.

The four sites the bridge accepts out of the box (v0.2.0):

| Site | Origin | Role |
| --- | --- | --- |
| Nepal Gas group (all 7 companies) | `https://ng-group.raindropinc.com` | production |
| avinaslive1 | `https://avinaslive1.raindropinc.com` | test |
| sandbox | `https://sandboxavinas-demo.raindropinc.com` | test |
| demo | `https://avinasdemo.raindropinc.com` | test |

## Deploy the app update (ERP server, once)

QZ Tray was removed from the app in favour of the bridge (commit `b0ddcfe` on
`develop`). The print code lives on the **ERP server** that serves all four
sites — not on the till — so it must be deployed there before any browser sees
the QZ-free behaviour. On the bench that runs `ng-group.raindropinc.com` and the
three test sites:

```bash
cd /path/to/frappe-bench/apps/avinashgroup_app
git pull                       # pulls the QZ-removal commit on develop
cd /path/to/frappe-bench
bench build --app avinashgroup_app
bench --site all clear-cache
bench restart
```

Then **hard-reload** the browser (Ctrl+Shift+R) on each site. After this:
machines with the bridge print via LQ310-RAW; machines without it show a clear
"install PrintBridgeSetup.exe + reload" message instead of the old QZ error.

## Install (once per machine)

1. Download **`PrintBridgeSetup.exe`** from the
   [latest release](https://github.com/SubashRDP/avinashgroup_app/releases)
   (`print-bridge-v0.3.5` or newer) and run it. Accept the admin (UAC) prompt.
   The Epson doesn't have to be attached: with it on, the installer creates the
   `LQ310-RAW` queue immediately; without it, an info note says the queue will
   be created automatically on the first print with the printer connected.
2. That's all. No QZ Tray, no certificate, no browser configuration.

The installer: drops `print_bridge.exe`, creates the `LQ310-RAW` queue (now or
on first print — see above), pre-grants all four origins in the Chrome/Edge
local-network policy, and registers an autostart task that runs the agent as
SYSTEM at boot **and** at any user's sign-in (the sign-in trigger is what keeps
it alive across "Shut down" on Fast Startup machines — needs v0.3.4+).

## Verify all 4 sites print

For **each** of the four URLs above:

1. Open the site in Chrome/Edge and log in.
2. Open an invoice → **Print** → choose a raw/dot-matrix format.
3. Expect: a green toast *"Printing via LQ310-RAW"* and the Epson prints — **no
   "Allow local network" prompt**.

Tick them off:

- [ ] `ng-group.raindropinc.com` prints
- [ ] `avinaslive1.raindropinc.com` prints
- [ ] `sandboxavinas-demo.raindropinc.com` prints
- [ ] `avinasdemo.raindropinc.com` prints

If all four print from the single install, the goal is met.

## If something doesn't print

Log: `%PROGRAMDATA%\AvinashPrintBridge\print_bridge.log`

| Symptom | Cause / fix |
| --- | --- |
| Installer says the queue couldn't be created | Epson not attached / powered off. Connect it, re-run the installer. |
| One site prompts "Allow local network" | Policy key didn't apply (rare). Click Allow once — Chrome remembers. Or confirm the origin is in `allowed_origins`. |
| A site does nothing / falls back to QZ behaviour | Agent not running. Start "Avinash Print Bridge" from the Start menu, or reboot (the startup task relaunches it as SYSTEM). |
| Spooler says printed, nothing moves | Job went to the Epson driver queue, not `LQ310-RAW`. Check the printer mapping in Print view. |
| A **new** test site needs to print | Edit `%PROGRAMDATA%\AvinashPrintBridge\config.json` → add its `https://…` origin to `allowed_origins`, restart the agent. No reinstall. Chrome may ask once. |

## Config reference

`%PROGRAMDATA%\AvinashPrintBridge\config.json` (see `print_bridge/README.md`):

- `allowed_origins` — the four sites are pre-listed. `["*"]` allows **any** site
  (only for a dedicated till). Exact-match; a new public site must be added here.
- `allow_local_test_origins` — `true` auto-accepts `localhost` / `127.*` /
  private-IP dev sites without listing them.
