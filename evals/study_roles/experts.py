"""Record the scripted EXPERT runs (synthetic experts, no model, no cost) through the sandbox with the real pipeline (extension -> isolated engine), so the genome
comparison has a reference path per role. A run = one deterministic program (``sandbox.program(task, variant, "expert", variation=k)``) on one case with the coach off.
What is kept per run: the events the engine stored (schema-valid, no text), the cog sequence the pack's own mapping gives them, and the oracle verdict. Labelled everywhere
as a synthetic expert, never a person."""
from __future__ import annotations

import json
from pathlib import Path

from evals.study_sim import analysis_io as sim_io

from .design import BlockPlan, ParticipantSpec, Persona, Slot
from .roles import SLUG, cfg, skill_pack_id, steps_off

HERE = Path(__file__).resolve().parent
EXPERT_LABEL = "synthetic expert (scripted driver), not a person"


def expert_plan(role: str, count: int = 8) -> list[tuple[str, int, int]]:
    """(task, variant, variation) for ``count`` runs: every task once (variant alternating, variation 0..3), then the first tasks again with the other variant. Deterministic."""
    sb = cfg(role).sandbox
    tasks = list(sb.TASKS)
    out = [(t, 1 + (i % 2), i % 4) for i, t in enumerate(tasks)]
    i = 0
    while len(out) < count:
        t, v, k = out[i]
        out.append((t, 3 - v, (k + 1) % 4))
        i += 1
    return out[:count]


def expert_spec(role: str, n: int, task: str, variant: int) -> ParticipantSpec:
    skill = next(k for k, s in cfg(role).sandbox.SKILLS.items() if task in s["task_ids"])
    b = BlockPlan(block=1, skill=skill, skill_id=skill_pack_id(role, skill), nominal_condition="uncoached", actual_condition="uncoached", pre=(task, variant), practice=(task, variant),
                  post=(task, variant), coach_on=False)
    return ParticipantSpec(pid=f"p_x{SLUG[role]}{n:02d}", index=n, role=role, arm="expert", sequence="X", pair=(skill, skill), unit=0, bits=(0, 0), persona=Persona("high", "high", "normal"), blocks=[b])


def expert_slot(role: str, task: str, variant: int) -> Slot:
    skill = next(k for k, s in cfg(role).sandbox.SKILLS.items() if task in s["task_ids"])
    return Slot(block=1, phase="practice", skill=skill, skill_id=skill_pack_id(role, skill), task=task, variant=variant, mode="off", coach_on=False, steps_off=steps_off(role, task))


def events_to_cogs(role: str, events: list[dict]) -> list[dict]:
    from understudy_engine.cogs import to_cogs
    from understudy_engine.core import Event
    from understudy_engine.packs import load_pack

    evs = [Event.model_validate(e) for e in events]
    cogs = to_cogs(evs, load_pack(role).cog_mapping())
    return [{"cog": c.id, "t0": round(c.t0, 2), "t1": round(c.t1, 2)} for c in cogs]


def save_run(role: str, outdir: Path, n: int, task: str, variant: int, variation: int, verdict: dict | None, events: list[dict]) -> Path:
    outdir = sim_io.write_provenance(outdir)
    doc = {"label": EXPERT_LABEL, "role": role, "task": task, "variant": variant, "style": "expert", "variation": variation, "verdict": {k: (verdict or {}).get(k) for k in ("outcome", "points", "skill_check_done")},
           "n_events": len(events), "events": events, "cogs": events_to_cogs(role, events) if events else []}
    f = outdir / f"run_{n:02d}.json"
    f.write_text(json.dumps(doc, indent=1))
    return f


def manifest(outdir: Path, role: str) -> dict:
    runs = sorted(Path(outdir).glob("run_*.json"))
    docs = [json.loads(f.read_text()) for f in runs]
    m = {"label": EXPERT_LABEL, "role": role, "runs": len(docs), "all_correct": all(d["verdict"].get("outcome") == "correct" for d in docs),
         "tasks": sorted({d["task"] for d in docs}), "cog_sequences": {f"run_{i + 1:02d}": [c["cog"] for c in d["cogs"]] for i, d in enumerate(docs)}}
    (Path(outdir) / "MANIFEST.json").write_text(json.dumps(m, indent=1))
    return m
