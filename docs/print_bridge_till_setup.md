# Print Bridge — Till Setup & Fix Guide

**Give this to whoever is at the Windows till.** Follow it top to bottom. It fixes
the two errors you've seen:

- **"Windows cannot access the specified device, path, or file"** when running the
  installer.
- **"Print Bridge not installed on this computer"** popup when printing.

Both mean the same thing: **the Print Bridge agent isn't running on this PC** —
either it never installed (Windows blocked the installer) or it didn't start.
This guide gets it installed and running, and keeps it running after a reboot.

---

## What the Print Bridge is

A tiny background program that lets the ERP (in Chrome/Edge) print raw invoices
to the **Epson LQ-310** dot-matrix printer. It replaces QZ Tray. Once installed
correctly it runs by itself from every startup — no login, no daily setup.

The ERP itself is already updated on all 4 sites (ng-group + the 3 test sites).
The **only** thing left is getting this agent running on each till PC.

---

## STEP 1 — Download the installer

On the till, open this link in the browser and download **`PrintBridgeSetup.exe`**:

**https://github.com/SubashRDP/avinashgroup_app/releases/latest**

(Use the **latest** version — **v0.3.5 or newer**. Older versions have a bug
where the agent doesn't come back after a **shutdown** — if that's your
symptom, just installing the latest version over the old one is the fix.)

---

## STEP 2 — Get past "Windows cannot access…" (this is the recurring error)

Windows blocks freshly-downloaded, unsigned installers. Clear it **in this order**:

1. **Unblock the file:**
   - Right-click **`PrintBridgeSetup.exe`** → **Properties**.
   - On the **General** tab, at the bottom, if there's an **"Unblock"** checkbox →
     tick it → **Apply → OK**.

2. **Run as administrator:**
   - Right-click **`PrintBridgeSetup.exe`** → **Run as administrator** → **Yes** to
     the UAC prompt.

3. **If a blue "Windows protected your PC" box appears:**
   - Click **More info** → **Run anyway**.

4. **If it STILL won't run — antivirus is quarantining it:**
   - Open **Windows Security** (Start → type "Windows Security").
   - **Virus & threat protection → Protection history** — if `PrintBridgeSetup.exe`
     is listed as blocked/quarantined → click it → **Actions → Allow / Restore**.
   - Or add an exclusion: **Virus & threat protection → Manage settings →
     Exclusions → Add or remove exclusions → Add an exclusion → File** → pick the
     exe.
   - Then **re-download** (the antivirus may have deleted it) and run again.

> This is not a broken file. It's unsigned, so Windows/antivirus is cautious.
> Steps 1–2 clear it 90% of the time.

---

## STEP 3 — Install

1. Click through the wizard to the end. (Having the Epson LQ-310 attached and ON
   is nice but **not required** — install with or without the printer.)
2. If the Epson isn't attached, the installer shows an information note saying
   the print queue will be created automatically later — that's normal, click OK.
   The first time you print with the printer connected and switched on, the
   queue sets itself up and that same print goes through.
3. Only a **red error** box ("could not be created" with the printer attached
   and on) means something is actually wrong — see Troubleshooting.

---

## STEP 4 — Confirm the agent is running

1. Open **Task Manager** (Ctrl+Shift+Esc) → **Details** tab.
2. Look for **`print_bridge.exe`** in the list.
   - **There →** good, it's running. Go to Step 5.
   - **Not there →** open it manually once: **Start menu → "Avinash Print Bridge"**.
     Then check Task Manager again. If it's now there, continue. If it still isn't,
     see Troubleshooting.

---

## STEP 5 — Print a test invoice

1. In the browser, **reload the invoice page** (Ctrl+Shift+R).
2. Open an invoice → **Print** → pick the dot-matrix format.
3. Expect a green **"Printing via LQ310-RAW"** message and the Epson prints.
   - If you see **"Print Bridge not installed on this computer"** → the agent
     isn't running; go back to Step 4.

---

## STEP 6 — The shutdown test (this is the real goal)

1. **Shut down the PC completely** (Start → Power → **Shut down** — not Restart),
   wait a few seconds, then power it back on and sign in.
2. **Print without starting anything** — it should just work. (The agent starts
   at boot and again at sign-in; "Shut down" and "Restart" take different paths
   in Windows, which is why we test Shut down specifically.)
3. **Unplug the Epson, try to print → clear "attach the printer" message.
   Plug it back in, print again → it recovers by itself, no reinstall.**

If Step 6 works, the till is done.

---

## Troubleshooting

**Log file (send this if you're stuck):**
`C:\ProgramData\AvinashPrintBridge\print_bridge.log`
(paste that path into File Explorer's address bar; send the last ~15 lines.)

| What you see | What it means / fix |
|---|---|
| "Windows cannot access the specified device, path, or file" | Installer blocked. Do **Step 2** (Unblock → Run as administrator → antivirus Allow). |
| "Print Bridge not installed on this computer" (in browser) | Agent not running. **Step 4** — start it, or reinstall the latest version. |
| Worked right after install, but **dead after every shutdown** | Old version only started at boot, and a Windows "Shut down" isn't a boot. **Install v0.3.4 or newer over it** — it also starts at sign-in. |
| "The auto-start task could not be registered" (during install) | v0.3.3 only — its registration needed PowerShell, which some tills can't find. **Install v0.3.4 or newer**; if it still appears, send `C:\ProgramData\AvinashPrintBridge\task_register.log`. |
| "The LQ310-RAW print queue could not be created" (during install) | On v0.3.5+ this only appears for a *real* error (no-printer is just an info note now — nothing to do, first print sets it up). Old versions showed it whenever the Epson was absent: safe to ignore, or install the latest. If it appears **with the printer attached and on**, send the log. |
| `print_bridge.exe` not in Task Manager even after starting it | Send me the log file above — the agent is crashing on start. |
| Printer moved to a different USB socket after a reboot | Handled automatically — the agent repairs the queue's port on the next startup. |
| Prints nothing but says success | Job went to the Epson's own driver queue, not LQ310-RAW. Reinstall the latest version with the printer attached. |

---

## What to report back

Tell me **which STEP it stops at** and:
1. The exact error text (or a screenshot).
2. Whether **`print_bridge.exe`** is in Task Manager.
3. The last ~15 lines of `C:\ProgramData\AvinashPrintBridge\print_bridge.log`.

That's enough for me to pinpoint and fix whatever's left.
