"""Vetted template: source files that keep changing without a test, from gitlog.json. Runs in the sandbox.
A gap is a source file changed in at least 3 commits that touched no test file, where those commits are at least 70
percent of all the commits that changed the file. Writes result.json and out/test_gaps.json."""
import json
import os

CODE = (".py", ".js", ".ts", ".go", ".rs", ".java", ".rb", ".c", ".cpp", ".swift", ".kt")
log = json.load(open("gitlog.json", encoding="utf-8"))
changes, untested = {}, {}
for c in log["commits"]:
    for f in c["files"]:
        p = f["path"]
        if f["test"] or not p.endswith(CODE):
            continue
        changes[p] = changes.get(p, 0) + 1
        if not c["touches_test"]:
            untested[p] = untested.get(p, 0) + 1
gaps = [{"path": p, "changes": changes[p], "untested_changes": untested.get(p, 0)} for p in changes
        if untested.get(p, 0) >= 3 and untested.get(p, 0) / changes[p] >= 0.7]
gaps = sorted(gaps, key=lambda g: (-g["untested_changes"], g["path"]))[:20]
result = {"n_commits": len(log["commits"]), "min_untested_changes": 3, "gaps": gaps}
os.makedirs("out", exist_ok=True)
json.dump(result, open("result.json", "w", encoding="utf-8"))
json.dump(result, open("out/test_gaps.json", "w", encoding="utf-8"), indent=1)
print("found", len(gaps), "gaps")
