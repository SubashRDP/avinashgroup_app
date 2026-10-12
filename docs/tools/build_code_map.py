"""Rebuild docs/salary-code-map.md and .tours/salary-calculation.tour from the template.

The map links every step of the salary calculation to its exact line. Line
numbers move whenever code is edited, so they are never typed by hand: the
template names each target as @@path::symbol@@ (a function, class or constant;
@@path::=text@@ for an exact line of text), and this script finds the one line
that defines it. A symbol that matches no line, or more than one, stops the
build. The link check that follows opens every target and confirms it holds the
named symbol.

Run after changing any code the map points at:

    python3 docs/tools/build_code_map.py

Paths in the template are relative to this repo's root; the sibling apps are
../hrms and ../rdp_common_app.
"""

import json, os, re, sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
TMPL = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "salary-code-map.tmpl.md")
src = open(TMPL).read()
errors = []

def resolve(path, sym):
    full = os.path.normpath(os.path.join(ROOT, path))
    lines = open(full).read().split("\n")
    hits = []
    if sym.startswith("="):
        lit = sym[1:]
        hits = [i for i, l in enumerate(lines, 1) if lit in l]
    else:
        pat = re.compile(r"^\s*(?:async\s+)?(?:def|class)\s+%s\b|^%s\s*=" % (re.escape(sym), re.escape(sym)))
        hits = [i for i, l in enumerate(lines, 1) if pat.search(l)]
    if len(hits) != 1:
        errors.append(f"{path}::{sym} -> {hits}")
    return hits[0] if hits else 0

def link_target(path, line):
    rel = "../" + path  # from docs/
    return f"{rel}#L{line}"

def repl(m):
    path, sym = m.group(1), m.group(2)
    n = resolve(path, sym)
    return f"\x00{path}\x01{n}\x02"

tmp = re.sub(r"@@(.+?)::(.+?)@@", repl, src)

# Links already wrapped as [`name`](TOKEN) -> just the target
tmp = re.sub(r"\(\x00(.+?)\x01(\d+)\x02\)", lambda m: "(" + link_target(m.group(1), m.group(2)) + ")", tmp)
# Bare tokens -> [file:N](target)
tmp = re.sub(r"\x00(.+?)\x01(\d+)\x02",
             lambda m: f"[{os.path.basename(m.group(1))}:{m.group(2)}]({link_target(m.group(1), m.group(2))})", tmp)

if errors:
    print("UNRESOLVED/AMBIGUOUS:\n" + "\n".join(errors)); sys.exit(1)

open(os.path.join(ROOT, "docs/salary-code-map.md"), "w").write(tmp)

# CodeTour from stage tables
steps = []
stage = None
for line in tmp.split("\n"):
    h = re.match(r"^## (\d+)\. (.+)", line)
    if h:
        stage = f"{h.group(1)}. {h.group(2)}"
        continue
    if h is None and line.startswith("## "):
        stage = None
    if not stage or not line.startswith("| ") or line.startswith("| #") or line.startswith("|---"):
        continue
    cells = [c.strip() for c in line.strip().strip("|").split("|")]
    num, func, filecell, what, reads = cells[:5]
    lm = re.search(r"\]\((.+?)#L(\d+)\)", filecell)
    path = lm.group(1)[3:]  # drop leading ../ -> repo-root relative
    desc = what
    if reads and reads != "—":
        desc += f"\n\nReads: {reads}"
    steps.append({"file": path, "line": int(lm.group(2)), "title": f"{num} {func.strip('`')}", "description": desc})

tour = {
    "$schema": "https://aka.ms/codetour-schema",
    "title": "Salary calculation: punch to journal",
    "description": "Every function that turns a biometric punch into a salary slip and its journal, in the order it runs. Same steps as docs/salary-code-map.md.",
    "isPrimary": False,
    "steps": [{"file": "docs/salary-code-map.md", "line": 1, "title": "Salary code map",
               "description": "The overview page for this tour: the pipeline picture, the same steps as tables, and the settings that change the result."}] + steps,
}
os.makedirs(os.path.join(ROOT, ".tours"), exist_ok=True)
with open(os.path.join(ROOT, ".tours/salary-calculation.tour"), "w") as f:
    json.dump(tour, f, indent=2, ensure_ascii=False)
    f.write("\n")
print("steps", len(steps))


# ── link check ──────────────────────────────────────────────────────────────
md = open(os.path.join(ROOT, "docs/salary-code-map.md")).read()

def symbol_of(text):
    s = text.strip().strip("`").split(".")[-1].strip("()")
    return s

def check(path_abs, line, sym):
    if not os.path.isfile(path_abs):
        return f"missing file {path_abs}"
    lines = open(path_abs).read().split("\n")
    if line < 1 or line > len(lines):
        return f"line {line} out of range"
    if sym not in lines[line - 1]:
        return f"line {line} lacks {sym!r}: {lines[line-1].strip()!r}"
    return None

fails, n = [], 0
for row in md.split("\n"):
    for m in re.finditer(r"\[([^\]]+)\]\(([^)#\s]+)#L(\d+)\)", row):
        n += 1
        text, rel, line = m.group(1), m.group(2), int(m.group(3))
        if "`" in text:
            sym = symbol_of(text)
        else:
            cells = [c.strip() for c in row.strip().strip("|").split("|")]
            sym = symbol_of(cells[1])
        err = check(os.path.normpath(os.path.join(ROOT, "docs", rel)), line, sym)
        if err: fails.append(f"MD {text} -> {err}")
# also make sure no link lacks an anchor or is malformed
bare = re.findall(r"\]\((\.\./[^)#]+)\)", md)
for b in bare: fails.append(f"MD link without line anchor: {b}")

tour = json.load(open(os.path.join(ROOT, ".tours/salary-calculation.tour")))
t = 0
for s in tour["steps"]:
    t += 1
    sym = symbol_of(s["title"].split(" ", 1)[1])
    if s["file"] == "docs/salary-code-map.md":
        sym = "Salary code map"
    err = check(os.path.normpath(os.path.join(ROOT, s["file"])), s["line"], sym)
    if err: fails.append(f"TOUR {s['title']} -> {err}")
print(f"markdown links checked: {n}; tour steps checked: {t}")
print("\n".join(fails) if fails else "ALL OK")
sys.exit(1 if fails else 0)
