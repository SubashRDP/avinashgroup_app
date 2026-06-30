"""CI diagnostic: report the build interpreter and whether each dependency
imports, writing the result to depcheck.txt so it can be published as a release
asset and read without GitHub auth. Always exits 0 (diagnostic mode) so the
workflow proceeds and the asset gets uploaded.
"""
import importlib
import os
import subprocess
import sys
import traceback

MODS = ["requests", "urllib3", "certifi", "charset_normalizer", "idna", "zk",
        "cryptography", "cffi", "pystray", "PIL", "sv_ttk", "win32com", "pywintypes"]

lines = []
lines.append("== interpreter ==")
lines.append("sys.executable: " + sys.executable)
lines.append("sys.version: " + sys.version.replace("\n", " "))
lines.append("platform: " + sys.platform + "  maxsize=" + str(sys.maxsize))
lines.append("cwd: " + os.getcwd())

lines.append("")
lines.append("== pip list ==")
try:
    out = subprocess.run([sys.executable, "-m", "pip", "list"],
                         capture_output=True, text=True, timeout=120).stdout
    lines.append(out.strip())
except Exception as exc:  # noqa: BLE001
    lines.append("pip list failed: " + repr(exc))

lines.append("")
lines.append("== imports ==")
for mod in MODS:
    try:
        m = importlib.import_module(mod)
        lines.append("ok   {0:18} {1}".format(mod, getattr(m, "__file__", "?")))
    except Exception:  # noqa: BLE001
        lines.append("FAIL {0}".format(mod))
        lines.append(traceback.format_exc())

report = "\n".join(lines)
print(report)
with open("depcheck.txt", "w", encoding="utf-8") as fh:
    fh.write(report + "\n")
