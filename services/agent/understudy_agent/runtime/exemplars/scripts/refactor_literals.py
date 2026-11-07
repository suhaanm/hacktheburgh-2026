"""Vetted template: a behaviour-preserving refactor. In each file under src, a number written three or more times
(other than 0, 1, 2, 10, 100, 0.0, 1.0) becomes a named constant at the top of the module. Edits the working tree only;
the patch draft is computed by code from the diff. Writes result.json and out/refactor_notes.json."""
import glob
import io
import json
import os
import re
import tokenize

SKIP = {"0", "1", "2", "10", "100", "0.0", "1.0"}
candidates = []
for path in sorted(glob.glob("src/**/*.py", recursive=True)):
    text = open(path, encoding="utf-8").read()
    try:
        toks = list(tokenize.generate_tokens(io.StringIO(text).readline))
    except (tokenize.TokenError, IndentationError):
        continue
    nums = [t for t in toks if t.type == tokenize.NUMBER and t.string not in SKIP]
    counts = {}
    for t in nums:
        counts[t.string] = counts.get(t.string, 0) + 1
    rep = [(n, s) for s, n in counts.items() if n >= 3]
    if not rep:
        continue
    n, lit = max(rep)
    const = "CONST_" + re.sub(r"[^0-9A-Za-z]", "_", lit)
    lines = text.splitlines(keepends=True)
    for t in sorted((t for t in nums if t.string == lit), key=lambda t: t.start, reverse=True):
        r, c = t.start
        lines[r - 1] = lines[r - 1][:c] + const + lines[r - 1][t.end[1]:]
    at = next((i for i, l in enumerate(lines) if re.match(r"(def|class) ", l)), len(lines))
    lines[at:at] = [const + " = " + lit + "\n", "\n", "\n"]
    open(path, "w", encoding="utf-8").write("".join(lines))
    candidates.append({"path": path, "literal": lit, "occurrences": n, "constant": const})
result = {"candidates": candidates, "files_changed": len(candidates)}
os.makedirs("out", exist_ok=True)
json.dump(result, open("result.json", "w", encoding="utf-8"))
json.dump(result, open("out/refactor_notes.json", "w", encoding="utf-8"), indent=1)
print("refactored", len(candidates), "files")
