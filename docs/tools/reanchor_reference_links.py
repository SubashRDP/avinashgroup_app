"""Re-point broken #L links in docs/system-reference to the line now holding their symbol.

After a code change moves lines: python3 docs/tools/reanchor_reference_links.py, then
python3 docs/tools/check_reference_links.py. Prefers the def/class line nearest the old one.
"""
import os, re, glob, sys

D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "system-reference")
LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
def sym_of(text):
    m = re.search(r"`([^`]+)`", text)
    if not m: return None
    s = m.group(1).strip()
    s = re.split(r"::|\.", s.rstrip("()"))[-1] if not s.startswith('"') else s
    return s.rstrip("()").strip()
fixed = unresolved = 0
for md in sorted(glob.glob(os.path.join(D, "*.md"))):
    global changed
    base = os.path.dirname(md); out = []; changed = False
    for row in open(md, encoding="utf-8"):
        def repl(m):
            global fixed, unresolved, changed
            text, target = m.group(1), m.group(2)
            path, _, anchor = target.partition("#")
            if not anchor.startswith("L") or re.match(r"^[a-z]+://", target): return m.group(0)
            full = os.path.normpath(os.path.join(base, path)); s = sym_of(text)
            if not s or not os.path.exists(full): return m.group(0)
            try: old = int(anchor[1:].split("-")[0])
            except ValueError: return m.group(0)
            lines = open(full, encoding="utf-8", errors="replace").read().split("\n")
            if 1 <= old <= len(lines) and s in lines[old - 1]: return m.group(0)
            cands = [i + 1 for i, l in enumerate(lines) if s in l]
            if not cands: unresolved += 1; print("UNRESOLVED", os.path.basename(md), text, target); return m.group(0)
            defs = [i for i in cands if re.search(rf"(def|class)\s+{re.escape(s)}\b|^\s*{re.escape(s)}\s*[:=]", lines[i - 1])]
            pool = defs or cands
            new = min(pool, key=lambda i: abs(i - old))
            fixed += 1; changed = True
            return f"[{text}]({path}#L{new})"
        out.append(LINK.sub(repl, row))
    if changed: open(md, "w", encoding="utf-8").write("".join(out))
print("fixed", fixed, "unresolved", unresolved)
