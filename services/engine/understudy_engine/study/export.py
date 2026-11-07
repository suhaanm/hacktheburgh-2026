"""``study export``: the per-participant results file, in exactly the format ``evals/study/analyze.py`` reads.

Everything that can come from the system's own records does: block windows from ``data/study/log.jsonl``, practice and
post-test seconds and the nudge counts from the person's events, and the post-test score from the sandbox state saved
under ``evals/study/results/raw/`` (scored by analyze.score_post_test, not by watching). What only the facilitator knows
(exclusion, notes) comes from ``data/study/sessions.json``. A value the records cannot give is left blank and listed in
the problems, never invented. The file is written only when the facilitator runs this; nothing calls it automatically.
"""
from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path

from ..store import EventStore
from ..store.paths import repo_root
from .state import StudyError, read_log, sessions_path

PRACTICE_CAP_S = 300.0
POST_CAP_S = 240.0


def study_dir() -> Path:
    return repo_root() / "evals" / "study"


def results_dir() -> Path:
    return study_dir() / "results"


def load_analyze():
    p = study_dir() / "analyze.py"
    if not p.is_file():
        raise StudyError(f"{p} is missing; the export needs the analysis script it feeds.")
    spec = importlib.util.spec_from_file_location("understudy_study_analyze", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def load_sessions() -> dict:
    p = sessions_path()
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def _windows(entries: list[dict]) -> list[dict]:
    """[{block_no, kind: practice|post, t0, t1, mode}] from the mode-change log of one person."""
    entries = sorted((e for e in entries if not e.get("cleared")), key=lambda e: e["t"])
    out: list[dict] = []
    block_no = 0
    prev_block = None
    for i, e in enumerate(entries):
        nxt = entries[i + 1] if i + 1 < len(entries) else None
        t1 = nxt["t"] if nxt else None
        kind = "post" if e["block"] == "post_test" else "practice"
        if kind == "practice":
            reset = e["block"] == "off" and nxt is not None and nxt["block"] == "train" and prev_block in (None, "post_test")
            if reset:
                prev_block = e["block"]
                continue                                  # an "off" right before a train is only a reset between blocks
            if e.get("block_no"):
                block_no = int(e["block_no"])
            elif prev_block in (None, "post_test"):
                block_no += 1
        out.append({"block_no": block_no, "kind": kind, "t0": e["t"], "t1": t1, "mode": e["block"], "skill_on": e.get("skill_on")})
        prev_block = e["block"]
    return out


def _seconds(events, t0: str, t1: str | None) -> float | None:
    """From the first calculator opened in the window to the last thing the worker did in it."""
    sel = [e for e in events if e.source != "coach" and e.t.strftime("%Y-%m-%dT%H:%M:%S.%f")[:23] + "Z" >= t0 and (t1 is None or e.t.strftime("%Y-%m-%dT%H:%M:%S.%f")[:23] + "Z" < t1)]
    opens = [e for e in sel if e.type == "nav" and e.meta.get("zone") == "calc_site"]
    if not opens or not sel:
        return None
    return round(max(e.t for e in sel).timestamp() - min(e.t for e in opens).timestamp(), 1)


def build_rows(store: EventStore | None = None, raw_dir: Path | None = None, partition: str = "both") -> tuple[list[dict], list[str]]:
    an = load_analyze()
    store = store or EventStore()
    raw_dir = raw_dir or results_dir() / "raw"
    assignments = json.loads((study_dir() / "assignments.json").read_text(encoding="utf-8"))
    sessions, log = load_sessions(), read_log()
    rows: list[dict] = []
    problems: list[str] = []
    for pid, sess in sorted(sessions.items()):
        plan = assignments["participants"].get(pid)
        person = sess.get("person")
        if not plan or not person:
            problems.append(f"{pid}: needs an entry in assignments.json and a person in sessions.json (study session set {pid} --person p_xxx)")
            continue
        events = []
        for part in ("real", "synthetic") if partition == "both" else (partition,):
            events += store.read(part, person=person)
        events.sort(key=lambda e: e.t)
        wins = _windows([e for e in log if e.get("person") == person])
        for b in plan["blocks"]:
            n = b["block"]
            pr = next((w for w in wins if w["block_no"] == n and w["kind"] == "practice"), None)
            po = next((w for w in wins if w["block_no"] == n and w["kind"] == "post"), None)
            row = {c: "" for c in an.COLUMNS}
            row.update(participant=pid, sequence=plan["sequence"], block=n, skill=b["skill"], condition=b["condition"],
                       practice_case=b["practice_case"], post_case=b["post_case"], post_checks_possible=an.POSSIBLE[b["skill"]],
                       exclusion=sess.get("exclusion", ""), notes=(sess.get("notes") or {}).get(str(n), ""))
            if pr:
                ps = _seconds(events, pr["t0"], pr["t1"])
                if ps is not None:
                    row["practice_seconds"], row["practice_capped"] = ps, "yes" if ps >= PRACTICE_CAP_S else "no"
                coach = [e for e in events if e.source == "coach" and e.meta.get("block") == "train"
                         and pr["t0"] <= e.t.strftime("%Y-%m-%dT%H:%M:%S.%f")[:23] + "Z" and (pr["t1"] is None or e.t.strftime("%Y-%m-%dT%H:%M:%S.%f")[:23] + "Z" < pr["t1"])]
                row["nudges_shown"] = sum(1 for e in coach if e.type == "coach_shown")
                row["nudges_followed"] = sum(1 for e in coach if e.type == "coach_followed")
                row["nudges_dismissed"] = sum(1 for e in coach if e.type == "coach_dismissed")
            else:
                problems.append(f"{pid} block {n}: no practice window in data/study/log.jsonl (use `mode` for every block)")
            if po:
                ps = _seconds(events, po["t0"], po["t1"])
                if ps is not None:
                    row["post_seconds"], row["post_capped"] = ps, "yes" if ps >= POST_CAP_S else "no"
            else:
                problems.append(f"{pid} block {n}: no post-test window in data/study/log.jsonl")
            raw = raw_dir / f"{pid}-block{n}-post.json"
            if raw.is_file():
                done, possible = an.score_post_test(b["skill"], json.loads(raw.read_text(encoding="utf-8")))
                row["post_checks_done"], row["post_checks_possible"] = done, possible
            else:
                problems.append(f"{pid} block {n}: {raw.name} is missing, so post_checks_done is blank (save the sandbox state right after the post-test)")
            for k in ("practice_seconds", "post_seconds"):
                if row[k] == "":
                    problems.append(f"{pid} block {n}: {k} could not be read from the events; enter it from the stopwatch")
            rows.append(row)
    return rows, problems


def write_csv(rows: list[dict], path: Path) -> None:
    an = load_analyze()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=an.COLUMNS)
        w.writeheader()
        w.writerows(rows)
