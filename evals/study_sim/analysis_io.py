"""CSV rows (the human format plus arm, persona, model), landing checks on the engine's stored events, and raw-output writers."""
from __future__ import annotations

import csv
import json
from pathlib import Path

from .design import EVALS, ParticipantSpec

STUDY = EVALS / "study"
HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"
EVENT_SCHEMA = EVALS.parent / "packages" / "schema" / "event.schema.json"

HUMAN_COLUMNS = ["participant", "sequence", "block", "skill", "condition", "practice_case", "post_case", "practice_seconds", "practice_capped",
                 "post_seconds", "post_capped", "post_checks_done", "post_checks_possible", "nudges_shown", "nudges_followed", "nudges_dismissed",
                 "exclusion", "notes"]
EXTRA_COLUMNS = ["arm", "persona", "model", "effort_unit", "actual_condition", "case_variant", "practice_actions", "post_actions", "practice_wall_s",
                 "post_wall_s", "practice_end", "post_end", "protocol_violation", "nudges_ignored", "false_nudges", "lag_prompts", "rings_drawn", "worker", "load1_start", "load1_end"]
COLUMNS = HUMAN_COLUMNS + EXTRA_COLUMNS


def shown_row(s) -> dict:
    """What is kept about a coach prompt: kinds, zones, step ids, outcome and timing. The message text is the coach's own template
    and is not stored per prompt."""
    return {"action": s.action, "zone": s.zone, "step": s.step, "skill": s.skill, "trigger": s.trigger, "level": s.level, "p_source": s.p_source,
            "ring_on_arrival": getattr(s, "ring_on_arrival", None), "ring_found": s.ring_found, "outcome": s.outcome, "false": s.false,
            "delay_s": s.delay_s}


def block_rows(spec: ParticipantSpec, cases: list, counts_by_block: dict, model_id: str, exclusion: str, wall_by_case=None) -> list[dict]:
    by = {(c.block, c.phase): c for c in cases}
    rows = []
    for b in spec.blocks:
        pr, po = by.get((b.block, "practice")), by.get((b.block, "post"))
        n = counts_by_block.get(b.block)
        done, possible = (po.score if po and po.score else (0, 2 if b.skill == "cliff" else 1))
        viol = "; ".join(x for x in (pr.protocol_violation if pr else "", po.protocol_violation if po else "") if x)
        notes = [f"variant={spec.variant}", f"actual={b.actual_condition}"]
        if viol:
            notes.append(f"protocol violation: {viol}")
        rows.append({
            "participant": spec.pid, "sequence": spec.sequence, "block": b.block, "skill": b.skill, "condition": b.nominal_condition,
            "practice_case": b.practice_case, "post_case": b.post_case,
            "practice_seconds": pr.used if pr else 0, "practice_capped": "yes" if (pr and pr.capped) else "no",
            "post_seconds": po.used if po else 0, "post_capped": "yes" if (po and po.capped) else "no",
            "post_checks_done": done, "post_checks_possible": possible,
            "nudges_shown": n.shown if n else 0, "nudges_followed": n.followed if n else 0, "nudges_dismissed": n.dismissed if n else 0,
            "exclusion": exclusion, "notes": "; ".join(notes),
            "arm": spec.arm, "persona": spec.persona.code(), "model": model_id, "effort_unit": "actions", "actual_condition": b.actual_condition,
            "case_variant": spec.variant, "practice_actions": pr.used if pr else 0, "post_actions": po.used if po else 0,
            "practice_wall_s": pr.wall_s if pr else 0, "post_wall_s": po.wall_s if po else 0,
            "practice_end": pr.reason if pr else "", "post_end": po.reason if po else "", "protocol_violation": viol,
            "nudges_ignored": n.ignored if n else 0, "false_nudges": n.false_nudges if n else 0, "lag_prompts": n.lag_prompts if n else 0,
            "rings_drawn": n.rings_drawn if n else 0, "worker": spec.worker,
            "load1_start": getattr(spec, "load1_start", ""), "load1_end": getattr(spec, "load1_end", "")})
    return rows


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)


def append_csv(path: Path, rows: list[dict]) -> None:
    exists = path.exists()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS, extrasaction="ignore")
        if not exists:
            w.writeheader()
        for r in rows:
            w.writerow(r)


def append_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, sort_keys=True) + "\n")


def landing_checks(data_dir: Path, person: str, coached_skill_id: str | None = None) -> dict:
    """Read what the engine stored for this person and check it: schema validity, counts by type, the coach events by block and skill."""
    import jsonschema

    validator = jsonschema.Draft202012Validator(json.loads(EVENT_SCHEMA.read_text()))
    rows: list[dict] = []
    d = Path(data_dir) / "real" / person
    for f in sorted(d.glob("*.jsonl")) if d.is_dir() else []:
        for line in f.read_text().splitlines():
            if line.strip():
                rows.append(json.loads(line))
    invalid = [r for r in rows if not validator.is_valid(r)]
    types: dict[str, int] = {}
    for r in rows:
        types[r["type"]] = types.get(r["type"], 0) + 1
    ext = [r for r in rows if r.get("source") != "coach"]
    shown = [r for r in rows if r["type"] == "coach_shown"]
    by_block_skill: dict[str, int] = {}
    enforcement = []
    for r in shown:
        meta = r.get("meta") or {}
        key = f"{meta.get('block')}/{meta.get('skill')}"
        by_block_skill[key] = by_block_skill.get(key, 0) + 1
        if meta.get("block") != "train" or meta.get("skill") != coached_skill_id:
            enforcement.append(f"coach_shown with block={meta.get('block')} skill={meta.get('skill')} (trained skill: {coached_skill_id})")
    zones: dict[str, int] = {}
    for r in ext:
        z = (r.get("meta") or {}).get("zone")
        if z:
            zones[z] = zones.get(z, 0) + 1
    return {"events": {"total": len(rows), "from_extension": len(ext), "schema_invalid": len(invalid), "types": types, "zones": zones,
                       "first_invalid": (invalid[0] if invalid else None) and {"type": invalid[0].get("type"), "errors": [e.message[:80] for e in validator.iter_errors(invalid[0])][:3]},
                       "task_starts": types.get("task_start", 0), "task_ends": types.get("task_end", 0), "tab_events": types.get("tab", 0)},
            "coach_events": {"shown": len(shown), "followed": types.get("coach_followed", 0), "dismissed": types.get("coach_dismissed", 0),
                             "by_block_skill": by_block_skill},
            "study_mode_enforcement_from_store": enforcement}


_ENUMLIKE = __import__("re").compile(r"^[A-Za-z0-9_:.\-/+=@#]{1,64}$")


def export_engine_events(data_dir: Path, person: str, dest: Path) -> dict:
    """Copy this participant's schema-valid L0 events (timestamps, types, zones, hashed ids; no page text) out of the engine's data dir before it is
    deleted, time-ordered, to ``dest`` (results/raw/<participant>/engine_events.jsonl). The schema forbids free text; as a belt-and-braces check any string
    value in ``meta`` or ``target`` that is not enum-like (letters, digits and _:.-/+=@#, at most 64 characters, no spaces) is replaced by "[removed]" and
    counted; the count is reported (it should be 0)."""
    d = Path(data_dir) / "real" / person
    rows: list[dict] = []
    for f in sorted(d.glob("*.jsonl")) if d.is_dir() else []:
        for line in f.read_text().splitlines():
            if line.strip():
                rows.append(json.loads(line))
    rows.sort(key=lambda r: (r.get("t", ""), r.get("id", "")))
    stripped = 0

    def scrub(node):
        nonlocal stripped
        if isinstance(node, dict):
            return {k: scrub(v) for k, v in node.items()}
        if isinstance(node, list):
            return [scrub(v) for v in node]
        if isinstance(node, str) and not _ENUMLIKE.match(node):
            stripped += 1
            return "[removed]"
        return node

    out = []
    for r in rows:
        r = dict(r)
        for k in ("meta", "target"):
            if k in r:
                r[k] = scrub(r[k])
        out.append(r)
    write_provenance(dest.parent)
    dest.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in out))
    return {"events": len(out), "stripped_values": stripped}


# ----------------------------------------------------------------------------------------------- output safety and provenance
PROVENANCE = {"origin": "simulated_participants_llm", "label": "simulated participants (language model), not people"}
LIVE_STUDY_DIR = STUDY      # evals/study: the live study with people. Nothing simulated may ever be written there.


class UnsafeOutputDir(RuntimeError):
    pass


def check_output_dir(path: Path) -> Path:
    """Refuse to write anywhere under evals/study/ (real paths compared) and refuse any symlink in the path, so a simulated results file can
    never land in the live study's folder by accident, by a relative path or through a link. Returns the resolved path."""
    p = Path(path).expanduser()
    probe = p if p.is_absolute() else Path.cwd() / p
    cur = Path(probe.anchor)
    for part in probe.parts[1:]:
        cur = cur / part
        if cur.is_symlink():
            raise UnsafeOutputDir(f"refusing to write through the symlink {cur}")
    real = probe.resolve()
    live = LIVE_STUDY_DIR.resolve()
    if real == live or live in real.parents:
        raise UnsafeOutputDir(f"refusing to write simulated results under the live study folder {live}")
    return real


def write_provenance(path: Path) -> Path:
    """Create the folder (after the safety check) and put PROVENANCE.json in it."""
    real = check_output_dir(path)
    real.mkdir(parents=True, exist_ok=True)
    f = real / "PROVENANCE.json"
    if not f.exists():
        f.write_text(json.dumps(PROVENANCE, indent=1) + "\n")
    return real


def write_provenance_tree(root: Path) -> int:
    """Put PROVENANCE.json in the folder and every sub-folder of a results tree (used after a run, so folders the run created get one too)."""
    root = write_provenance(root)
    n = 1
    for d in sorted(p for p in root.rglob("*") if p.is_dir()):
        write_provenance(d)
        n += 1
    return n
