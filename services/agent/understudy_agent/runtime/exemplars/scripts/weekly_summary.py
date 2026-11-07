"""Vetted template: a short weekly write-up from digest records (input/digests.json). Runs in the sandbox.
The draft cites digest ids only, in square brackets, and names categories only from the fixed vocabulary. Writes
result.json and out/weekly.md."""
import json
import os

data = json.load(open("input/digests.json", encoding="utf-8"))["digests"]
order = ["feature", "fix", "refactor", "test", "docs", "chore", "revert", "other"]
groups = {}
for d in data:
    groups.setdefault(d["category"], []).append(d["id"])
parts = []
for cat in order:
    ids = groups.get(cat)
    if ids:
        parts.append(str(len(ids)) + " " + cat + " " + " ".join("[" + i + "]" for i in ids[:3]))
draft = "This week had " + str(len(data)) + " changes: " + "; ".join(parts) + "."
cited = [i for cat in order for i in groups.get(cat, [])[:3]]
os.makedirs("out", exist_ok=True)
json.dump({"draft": draft, "cited": cited}, open("result.json", "w", encoding="utf-8"))
open("out/weekly.md", "w", encoding="utf-8").write("# Week in review\n\n" + draft + "\n")
print("drafted", len(cited), "citations")
