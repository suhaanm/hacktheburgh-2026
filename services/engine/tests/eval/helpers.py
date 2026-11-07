"""Shared builders for the study tests: a private copy of evals/study with made-up numbers (for the tests only), with or without provenance."""
from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
MANIFEST_OK = {"origin": "human", "consent_ref": "consent form v1, signed 8 Nov (kept by the facilitator)", "collected_by": "facilitator", "n_participants": 4, "date": "2026-11-08"}


def study_dir(tmp_path: Path, done: dict, post: dict | None = None, practice: dict | None = None, exclusion: dict | None = None, *, manifest: dict | bool | None = True,
              ids: dict[str, str] | None = None, extra_columns: dict[str, str] | None = None) -> Path:
    """A private evals/study with the platform's analyze.py and assignments.json and a made-up participants.csv.

    ``manifest``: True writes a valid hand-written manifest, a dict writes that dict, None/False writes none.
    ``ids`` renames participants (P1 -> p_sim01); ``extra_columns`` adds columns with a constant value (the simulated harness's schema)."""
    src = REPO / "evals" / "study"
    d = tmp_path / "evals" / "study"
    (d / "results").mkdir(parents=True)
    shutil.copy(src / "analyze.py", d / "analyze.py")
    shutil.copy(src / "assignments.json", d / "assignments.json")
    asg = json.loads((src / "assignments.json").read_text())
    possible = {"cliff": 2, "reconcile": 1}
    cols = ["participant", "sequence", "block", "skill", "condition", "practice_case", "post_case", "practice_seconds", "practice_capped", "post_seconds",
            "post_capped", "post_checks_done", "post_checks_possible", "nudges_shown", "nudges_followed", "nudges_dismissed", "exclusion", "notes"]
    all_cols = cols + list(extra_columns or {})
    with (d / "results" / "participants.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, all_cols)
        w.writeheader()
        for p, plan in asg["participants"].items():
            for b in plan["blocks"]:
                key = (p, b["condition"])
                row = {"participant": (ids or {}).get(p, p), "sequence": plan["sequence"], "block": b["block"], "skill": b["skill"], "condition": b["condition"],
                       "practice_case": b["practice_case"], "post_case": b["post_case"], "practice_seconds": (practice or {}).get(key, 300),
                       "practice_capped": "no", "post_seconds": (post or {}).get(key, 200), "post_capped": "no",
                       "post_checks_done": min(done.get(key, 0), possible[b["skill"]]), "post_checks_possible": possible[b["skill"]],
                       "nudges_shown": 6 if b["condition"] == "coached" else 0, "nudges_followed": 4 if b["condition"] == "coached" else 0,
                       "nudges_dismissed": 1 if b["condition"] == "coached" else 0, "exclusion": (exclusion or {}).get(p, ""), "notes": ""}
                row.update(extra_columns or {})
                w.writerow(row)
    if manifest:
        (d / "results" / "MANIFEST.json").write_text(json.dumps(MANIFEST_OK if manifest is True else manifest))
    return d


GOOD_DONE = {("P1", "coached"): 2, ("P1", "uncoached"): 0, ("P2", "coached"): 1, ("P2", "uncoached"): 0, ("P3", "coached"): 2, ("P3", "uncoached"): 1,
             ("P4", "coached"): 1, ("P4", "uncoached"): 0}
