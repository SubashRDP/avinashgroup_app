"""CI guard: confirm the runtime-critical third-party deps are importable in the
interpreter PyInstaller will build with. Run as `python k40_bridge/ci_check_deps.py`
so there's no shell-quoting surface (an inline `python -c "...; print()"` gets
mangled by PowerShell on the Windows runner).

cryptography is intentionally excluded: it's a binary package whose 32-bit Rust
wheel can fail to import on the x86 runner, and the bridge degrades gracefully
without it (CRYPTO_AVAILABLE -> plaintext fallback). The crash we must prevent is
a missing pure-Python dep (e.g. requests), so only those are gated here.
"""
import importlib
import sys

CRITICAL = ["requests", "urllib3", "certifi", "charset_normalizer", "idna", "zk"]

bad = []
for mod in CRITICAL:
    try:
        importlib.import_module(mod)
        print("ok  ", mod)
    except Exception as exc:  # noqa: BLE001 - report any import failure
        print("FAIL", mod, "->", repr(exc))
        bad.append(mod)

if bad:
    print("::error::critical deps not importable:", ", ".join(bad))
    sys.exit(1)
print("all critical deps import OK")
