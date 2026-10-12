"""Link checker for docs/system-reference/*.md.

Every link of the form [text](relative/path#L<n>) must:
  * resolve to an existing file (relative to the .md file),
  * have line n within range,
  * and, when the link text has a symbol in backticks, that symbol must
    occur on line n.  Symbol = text inside backticks, last part after '.'
    or '::' , trailing '()' removed.  Link text without backticks gets
    a range-only check and is reported as WEAK.
Links without #L to local files must exist.
Usage: python3 check_links.py [dir]
"""
import os, re, sys, glob

D = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "system-reference")
LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
fails, weak, n = [], [], 0

def sym_of(text):
    m = re.search(r"`([^`]+)`", text)
    if not m:
        return None
    s = m.group(1).strip()
    s = re.split(r"::|\.", s.rstrip("()"))[-1] if not s.startswith('"') else s
    return s.rstrip("()").strip()

for md in sorted(glob.glob(os.path.join(D, "*.md"))):
    base = os.path.dirname(md)
    in_code = False
    for ln, row in enumerate(open(md, encoding="utf-8"), 1):
        if row.lstrip().startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        for m in LINK.finditer(row):
            text, target = m.group(1), m.group(2)
            if re.match(r"^[a-z]+://", target) or target.startswith("#") or target.startswith("mailto:"):
                continue
            path, _, anchor = target.partition("#")
            full = os.path.normpath(os.path.join(base, path))
            if not os.path.exists(full):
                fails.append(f"{os.path.basename(md)}:{ln} missing file {target}")
                continue
            if not anchor.startswith("L"):
                continue
            n += 1
            try:
                line = int(anchor[1:].split("-")[0])
            except ValueError:
                fails.append(f"{os.path.basename(md)}:{ln} bad anchor {target}"); continue
            lines = open(full, encoding="utf-8", errors="replace").read().split("\n")
            if line < 1 or line > len(lines):
                fails.append(f"{os.path.basename(md)}:{ln} {target} line out of range ({len(lines)})"); continue
            s = sym_of(text)
            if s is None:
                weak.append(f"{os.path.basename(md)}:{ln} {text} -> {target}")
            elif s not in lines[line - 1]:
                fails.append(f"{os.path.basename(md)}:{ln} [{text}] {target}: line lacks {s!r}: {lines[line-1].strip()[:100]!r}")
print(f"line-anchored links checked: {n}; weak (no symbol): {len(weak)}; failures: {len(fails)}")
for w in weak: print("WEAK", w)
for f in fails: print("FAIL", f)
sys.exit(1 if fails else 0)
