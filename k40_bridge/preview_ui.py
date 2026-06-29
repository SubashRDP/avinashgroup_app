"""Throwaway visual preview of the K40 Bridge control panel.

Opens the real ControlPanel UI populated with fake devices in every state so you
can SEE the v1.3.0 visuals — colored rows, header health roll-up, legend, live
progress cues and severity-tinted logs — WITHOUT any config, network, or real
device. Safe to run and safe to delete; it is not part of the shipped app.

    cd k40_bridge && python3 preview_ui.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import k40_bridge as kb

# Neutralize everything that would hit the network or spawn background work, so
# this is a pure UI preview.
kb.SyncEngine.start = lambda self: None
kb.ControlPanel._check_update_quiet = lambda self: None
kb.ControlPanel._periodic_update_check_loop = lambda self: None
kb.check_for_update = lambda: (None, False)

cfg = dict(kb.DEFAULT_CONFIG)
cfg["devices"] = [
    {"name": "K40-Reception", "type": "zkteco", "ip": "192.168.1.50", "port": 4370, "serial": "ZK-REC", "company": "Nepal Gas Udhyog"},
    {"name": "Gate-Hikvision", "type": "hikvision", "ip": "192.168.1.77", "port": 80, "serial": "HIK-GATE", "company": "Grishma Enterprises"},
    {"name": "HTMS-86", "type": "htms", "db_folder": r"E:\HTMS-86", "serial": "HTMS-86-V1", "company": "Sambriddhi Gas Udhyog"},
    {"name": "Plant-K20", "type": "zkteco", "ip": "192.168.1.60", "port": 4370, "serial": "ZK-PLANT", "company": "Grihalaxmi Metal"},
]

cp = kb.ControlPanel(cfg, primary_sock=None, start_hidden=True)
cp.root.deiconify()
cp.root.title("K40 Bridge v%s — UI PREVIEW (fake data)" % kb.VERSION)

# Paint a representative snapshot across all states.
cp._update_status("K40-Reception", "ok", "18 new, 4 skipped")
cp._update_status("Gate-Hikvision", "unreachable", "192.168.1.77 not on network")
cp._update_status("Plant-K20", "error", "2 errors (employee not found)")

for line in [
    "2026-06-29 09:00:00 INFO  [K40-Reception] sync_cycle: starting",
    "2026-06-29 09:00:02 INFO  [K40-Reception] fetched 220 records",
    "2026-06-29 09:00:05 INFO  [K40-Reception] sync_cycle: synced=18 skipped=4 errors=0",
    "2026-06-29 09:00:06 WARNING HTMS HAMS.mdb has 3 Emp_no value(s) shared by multiple employees",
    "2026-06-29 09:00:08 ERROR [Plant-K20] 2 punches: Employee not found having ID: 999",
]:
    cp._append_log(line)


# Animate HTMS-86 through a live sync so the progress cues are visible.
_steps = [
    ("syncing", "connecting…"),
    ("syncing", "fetched 1,204 record(s) — checking for new…"),
    ("syncing", "pushing 100/340…"),
    ("syncing", "pushing 200/340…"),
    ("syncing", "pushing 340/340…"),
    ("ok", "340 new, 12 skipped"),
]


def _animate(i=0):
    state, msg = _steps[i % len(_steps)]
    cp._update_status("HTMS-86", state, msg)
    cp.root.after(900, lambda: _animate(i + 1))


_animate()
cp.run()
