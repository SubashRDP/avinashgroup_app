"""CI guard: confirm the runtime deps are importable in the interpreter
PyInstaller builds with. Run as `python k40_bridge/ci_check_deps.py` (no inline
`python -c`, which PowerShell mangles on the Windows runner). Fails the build if
a dependency is missing — so a depless exe (which crashes at startup with
ModuleNotFoundError) can never be released again.
"""
import importlib
import sys

REQUIRED = ["requests", "urllib3", "certifi", "charset_normalizer", "idna",
            "zk", "cryptography"]

bad = []
for mod in REQUIRED:
    try:
        importlib.import_module(mod)
        print("ok  ", mod)
    except Exception as exc:  # noqa: BLE001
        print("FAIL", mod, "->", repr(exc))
        bad.append(mod)

if bad:
    print("::error::dependencies not importable (build would ship broken):", ", ".join(bad))
    sys.exit(1)
print("all required deps import OK")
