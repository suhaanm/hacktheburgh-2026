"""Vetted template: commit statistics from gitlog.json (written by the git_log tool). Runs in the sandbox.
A giant commit changes more than 450 lines (added plus deleted). A fix chain is a fix by the same author within 120
minutes of that author's previous fix. Writes result.json and out/commit_stats.json."""
import json
import os

GIANT = 450
log = json.load(open("gitlog.json", encoding="utf-8"))
cs = sorted(log["commits"], key=lambda c: (c["ts"], c["sha"]))
giants = sorted(({"sha": c["sha"], "lines": c["add"] + c["del"], "files": c["n_files"]}
                 for c in cs if c["add"] + c["del"] > GIANT), key=lambda g: (-g["lines"], g["sha"]))[:20]
by_class = {}
for c in cs:
    by_class[c["klass"]] = by_class.get(c["klass"], 0) + 1
chains, last_fix = 0, {}
for c in cs:
    if c["klass"] == "fix":
        prev = last_fix.get(c["author"])
        if prev is not None and c["ts"] - prev <= 7200:
            chains += 1
        last_fix[c["author"]] = c["ts"]
n = len(cs)
result = {"n_commits": n, "n_authors": log["n_authors"], "giant_threshold": GIANT, "giant_commits": giants,
          "test_touch_share": round(sum(1 for c in cs if c["touches_test"]) / n, 3) if n else 0.0,
          "reverts": by_class.get("revert", 0), "fix_after_fix_chains": chains, "by_class": by_class}
os.makedirs("out", exist_ok=True)
json.dump(result, open("result.json", "w", encoding="utf-8"))
json.dump(result, open("out/commit_stats.json", "w", encoding="utf-8"), indent=1)
print("analysed", n, "commits")
