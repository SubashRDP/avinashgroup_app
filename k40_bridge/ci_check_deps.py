"""CI diagnostic: actually run `pip install -r requirements.txt` and capture its
full output, plus interpreter + resulting pip list + per-module import results,
into depcheck.txt — published as a release asset so the real failure (which
package fails to install on the 32-bit runner) is readable without GitHub auth.
Always exits 0 so the asset always uploads.
"""
import importlib
import os
import subprocess
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
REQ = os.path.join(HERE, "requirements.txt")
MODS = ["requests", "urllib3", "certifi", "charset_normalizer", "idna", "zk",
        "cryptography", "cffi", "pystray", "PIL", "sv_ttk", "win32com", "pywintypes"]

out = []
out.append("== interpreter ==")
out.append("sys.executable: " + sys.executable)
out.append("sys.version: " + sys.version.replace("\n", " "))
out.append("platform: " + sys.platform + "  maxsize=" + str(sys.maxsize))


def run(cmd):
    out.append("")
    out.append("$ " + " ".join(cmd))
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
        out.append("[exit %s]" % r.returncode)
        if r.stdout:
            out.append(r.stdout.strip())
        if r.stderr:
            out.append("STDERR:\n" + r.stderr.strip())
    except Exception as exc:  # noqa: BLE001
        out.append("command crashed: " + repr(exc))


out.append("")
out.append("== pip install -r requirements.txt (verbose) ==")
run([sys.executable, "-m", "pip", "install", "-r", REQ])

out.append("")
out.append("== pip list (after) ==")
run([sys.executable, "-m", "pip", "list"])

out.append("")
out.append("== imports ==")
for mod in MODS:
    try:
        importlib.import_module(mod)
        out.append("ok   " + mod)
    except Exception:  # noqa: BLE001
        out.append("FAIL " + mod)
        out.append(traceback.format_exc().strip())

report = "\n".join(out)
print(report)
with open("depcheck.txt", "w", encoding="utf-8") as fh:
    fh.write(report + "\n")
