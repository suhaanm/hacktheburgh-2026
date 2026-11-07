"""Readers: where the collectors get their facts. One small function per source, each returning a ``Reading``.

``available=False`` means the source could not be read at all (a track that has not landed, a service that is down); an
empty list with ``available=True`` means we looked and found nothing. Verification depends on the difference: a source that
cannot be re-read can neither confirm nor refute a card, so it never makes one stale (honest uncertainty).

Real imports, wrapped so a missing or broken module gives ``Reading([], False, note)``:

* routines and skill state: the engine-handoff and engine-analytics tracks (always present);
* calendar suggestions: ``understudy_engine.calendar.suggest.suggestions(person)`` (sources-calendar track);
* git habits: ``understudy_engine.gitanalysis.suggest.suggestions(person, repo)`` (git-analysis track);
* finished agent runs: ``data/runs/*`` result files that name the person, plus ``GET :7710/agents/runs?person=`` when the
  caller allows the call (agent-runtime track).

Notes are plain reasons written here, never text read from a source.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .candidates import Ctx, Reader, Reading, _date_ts
from .paths import agent_url, data_dir, home_dir, layer_on

_LEVEL_MASTERY = {1: 0.2, 2: 0.45, 3: 0.7, 4: 0.9}     # when only a level is known (the memory file), a stated estimate


def _as_dict(x: Any) -> dict[str, Any]:
    if isinstance(x, dict):
        return x
    for attr in ("model_dump", "_asdict", "dict"):
        fn = getattr(x, attr, None)
        if callable(fn):
            try:
                return dict(fn())
            except Exception:
                pass
    try:
        import dataclasses

        if dataclasses.is_dataclass(x) and not isinstance(x, type):
            return dataclasses.asdict(x)
    except Exception:
        pass
    return {k: getattr(x, k) for k in dir(x) if not k.startswith("_") and not callable(getattr(x, k, None))}


# --------------------------------------------------------------------------------------------- routines
def routine_rows(st: Any, person: str) -> list[dict[str, Any]]:
    """Normalise a ``RoutineStore``'s routines for one person to the rows the collectors read."""
    rows: list[dict[str, Any]] = []
    for r in st._load()["routines"].values():
        if r.get("person") != person:
            continue
        c = st.contract(r)
        hours = (c["value"].get("hours_saved") or [0, 0])
        rows.append({
            "id": c["id"], "title": c["title"], "status": c["status"], "proposable": bool(c["proposable"]),
            "automatable": bool(c["automatable"]), "episodes": c["episodes"], "minutes_per_week": c["minutes_per_week"],
            "hours_lo": hours[0], "hours_hi": hours[1], "confidence": c["value"].get("confidence"),
            "horizon_weeks": c["value"].get("horizon_weeks"), "skill_gate_ok": bool(c["skill_gate"]["eligible"]),
            "skill_cogs": list(r.get("skill_cogs") or []), "touches": c["touches"], "never": c["never"],
            "irreversible_classes": c.get("irreversible_classes", []), "last_seen": c.get("last_seen"),
            "buy_after_runs": (c.get("build_timing") or {}).get("buy_after_runs"),
            "declined_not_now_at": r.get("declined_not_now_at"), "consent_mode": c["consent"]["mode"]})
    return rows


def read_routines(ctx: Ctx) -> Reading:
    """The worker's routines as the engine sees them now (the same call ``GET /routines`` makes), filtered to this person."""
    try:
        from .. import routes_handoff as rh
        from ..memory import MemoryStore
    except Exception:
        return Reading([], False, "handoff track not importable")
    pd = rh._src().load(ctx.person)
    if pd is None:
        return Reading([], True, "no events for this person")
    mem = MemoryStore(home_dir())
    st = rh._sync_routines(pd, mem)
    return Reading(routine_rows(st, ctx.person), True, None)


# --------------------------------------------------------------------------------------------- skills
def skill_rows_from_tracker(learner: Any, pack: Any, now_ts: float) -> list[dict[str, Any]]:
    """One row per curriculum skill from a learner's ``SkillTracker`` (levels with decay applied at ``now_ts``)."""
    t = max(now_ts, learner.t_ref)
    snap = learner.tracker.snapshot(t)
    items = []
    for sk in pack.skills:
        seen = [snap[c] for c in sk.get("cogs", []) if c in snap]
        if seen:
            level = min(s["level"] for s in seen)
            mastery = min(s["mastery"] for s in seen)
            drops = [s["days_until_level_drop"] for s in seen if s.get("days_until_level_drop") is not None]
            last = max((s["last_seen"] for s in seen if s.get("last_seen")), default=None)
        else:
            level, mastery, drops, last = 1, learner.tracker.params.p_init, [], None
        lts = _date_ts(last)
        items.append(_skill_row(sk, level, mastery, None if lts is None else max(0.0, (t - lts) / 86400.0), min(drops) if drops else None))
    return items


def skill_rows_from_levels(levels: dict[str, dict[str, Any]], pack: Any, now_ts: float) -> list[dict[str, Any]]:
    """One row per curriculum skill from level records ``{skill: {level, last_seen}}`` (the memory file's Skill state);
    mastery is estimated from the level, and says so."""
    items = []
    for sk in pack.skills:
        st = levels.get(str(sk["id"]))
        lv = int(st["level"]) if st else 1
        lts = _date_ts(st.get("last_seen") if st else None)
        items.append(_skill_row(sk, lv, _LEVEL_MASTERY.get(lv, 0.2), None if lts is None else max(0.0, (now_ts - lts) / 86400.0), None))
    return items


def read_skills(ctx: Ctx) -> Reading:
    """One row per curriculum skill: level, mastery, days since practice, days until the level would drop. A learner
    trajectory person comes from the SkillTracker (with decay); anyone else from the memory file's Skill state."""
    try:
        from .. import routes_handoff as rh
        from ..memory import MemoryStore
        from ..memory import doc as D
    except Exception:
        return Reading([], False, "handoff track not importable")
    mem = MemoryStore(home_dir())
    pd = rh._src().load(ctx.person)
    role = ctx.role or (pd.role if pd else None) or "benefits-processor"
    pack = rh._pack(role)
    learner = rh._learner(ctx.person, rh._case_for(ctx.person, None, mem))
    if learner is not None:
        return Reading(skill_rows_from_tracker(learner, pack, ctx.now_ts), True, "from the skill tracker")
    levels = D.skill_levels(mem.read())
    if not levels:
        return Reading([], True, "no skill record yet")
    return Reading(skill_rows_from_levels(levels, pack, ctx.now_ts), True, "from the memory file (mastery estimated from level)")


def _skill_row(sk: dict[str, Any], level: int, mastery: float, days_idle: float | None, days_until_drop: float | None) -> dict[str, Any]:
    return {"id": str(sk["id"]), "label": sk.get("label") or sk["id"], "order": sk.get("order", 99), "cogs": list(sk.get("cogs", [])),
            "prerequisites": list(sk.get("prerequisites", [])), "expert_signal": sk.get("expert_signal", ""),
            "prompts": dict(sk.get("prompts") or {}), "level": int(level), "mastery": float(mastery), "days_idle": days_idle,
            "days_until_drop": days_until_drop}


# --------------------------------------------------------------------------------------------- digests
def digest_mode() -> str | None:
    """``"model"`` when the calendar and git digests came from the local model, ``"rules"`` when from the deterministic rules,
    None when the local model layer is not there. Side-effect free (``localmodel.mode`` never starts the server)."""
    try:
        from understudy_engine.localmodel import mode

        m = mode()
        return m if m in ("model", "rules") else None
    except Exception:
        return None


# --------------------------------------------------------------------------------------------- calendar
def read_calendar(ctx: Ctx) -> Reading:
    """Calendar suggestions (CAL-3): ``[{id, template, numbers, expert_ref, risk, can_draft}]``. Free text is not kept.
    Read only when the calendar layer is on (it may build synthetic calendars on first use)."""
    if not layer_on("calendar"):
        return Reading([], False, "calendar layer is off")
    try:
        from understudy_engine.calendar import suggest as cal
    except Exception:
        return Reading([], False, "calendar track not available")
    fn = getattr(cal, "suggestions", None)
    if not callable(fn):
        return Reading([], False, "calendar track has no suggestions yet")
    try:
        raw = fn(ctx.person)
    except Exception as exc:
        return Reading([], False, f"{type(exc).__name__} from the calendar track")
    if isinstance(raw, dict) and "data" in raw:
        raw = raw["data"]
    items = []
    for s in list(raw or []):
        d = _as_dict(s)
        items.append({"id": str(d.get("id") or d.get("template") or ""), "template": d.get("template") or d.get("id"),
                      "numbers": d.get("numbers") or {}, "expert_ref": d.get("expert_ref") or {},
                      "risk": d.get("risk"), "can_draft": bool(d.get("can_draft"))})
    return Reading(items, True, None, {"digest": digest_mode()})


# --------------------------------------------------------------------------------------------- git
def git_items(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalise the git track's payload (``GET /git/habits`` data) to one row per code-selected suggestion: the template id,
    the primary habit's learner and expert shares, the difference and its interval. Text (the track's sentence, labels) is dropped."""
    n_commits = int(data.get("n_commits") or 0)
    rows = {h.get("id"): h for h in data.get("habits") or [] if isinstance(h, dict)}
    items = []
    for s in data.get("suggestions") or []:
        d = _as_dict(s)
        prim = d.get("primary_habit") or (d.get("habits") or [None])[0]
        nums = (d.get("numbers") or {}).get(prim) or {}
        row = rows.get(prim) or {}
        items.append({"id": str(d.get("template") or d.get("id") or ""), "habit": prim, "learner": nums.get("learner", row.get("learner")),
                      "expert": nums.get("expert", row.get("expert")), "delta": nums.get("delta", row.get("delta")),
                      "ci": nums.get("ci", row.get("ci")), "n_commits": n_commits, "flagged": True})
    if not items:      # no suggestions block: fall back to the flagged habit rows
        for h in data.get("habits") or []:
            if isinstance(h, dict) and h.get("flagged"):
                items.append({"id": str(h.get("id")), "habit": h.get("id"), "learner": h.get("learner"), "expert": h.get("expert"),
                              "delta": h.get("delta"), "ci": h.get("ci"), "n_commits": n_commits, "flagged": True})
    return items


def read_git(ctx: Ctx) -> Reading:
    """Git habits (GIT-1) from the git track's service (``habits(person, repo)``) or, if it ever lands, ``suggest.suggestions``.
    Read only when the git layer is on. A person with no repository is an honest empty reading, not an outage."""
    if not layer_on("git"):
        return Reading([], False, "git layer is off")
    try:
        from understudy_engine.gitanalysis import service as gsvc
        from understudy_engine.gitanalysis import suggest as gs
    except Exception:
        return Reading([], False, "git analysis track not available")
    try:
        fn = getattr(gs, "suggestions", None)
        if callable(fn):
            raw = fn(ctx.person, ctx.repo)
            data = raw if isinstance(raw, dict) else {"suggestions": list(raw or [])}
            data = data.get("data", data)
        else:
            data = gsvc.habits(ctx.person, ctx.repo)["data"]
    except Exception as exc:
        code = getattr(exc, "code", "")
        if code in ("unknown_person", "unknown_repo"):
            return Reading([], True, "no repository for this person")
        return Reading([], False, f"{type(exc).__name__} from the git track")
    digest = data.get("digest_source")
    return Reading(git_items(data), True, None, {"digest": digest if digest in ("model", "rules") else digest_mode()})


# --------------------------------------------------------------------------------------------- finished agent runs
_RUN_ID = re.compile(r"^[A-Za-z0-9_.\-]{1,64}$")
_DONE = ("done", "succeeded", "complete", "completed")
MAX_RUN_AGE_H = 72


def _viewed_marker(d: Path) -> bool:
    return (d / "viewed").exists() or (d / "viewed.json").exists()


def read_runs(ctx: Ctx) -> Reading:
    """Finished runs that belong to this person and have not been looked at. Files: ``data/runs/<id>/result.json`` or
    ``evidence.json`` carrying ``person``, ``state`` and (optionally) ``finished_at``. Runs without a person are not anyone's
    morning (the shared folder also holds evaluation runs)."""
    items: list[dict[str, Any]] = []
    runs = data_dir() / "runs"
    if runs.exists():
        for d in sorted(p for p in runs.iterdir() if p.is_dir() and _RUN_ID.match(p.name)):
            for name in ("result.json", "evidence.json"):
                f = d / name
                if not f.exists():
                    continue
                try:
                    j = json.loads(f.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                if not isinstance(j, dict) or j.get("person") != ctx.person:
                    continue
                fin = _date_ts(j.get("finished_at")) if isinstance(j.get("finished_at"), str) else j.get("finished_at")
                fin = fin if isinstance(fin, (int, float)) else f.stat().st_mtime
                if (ctx.now_ts - fin) / 3600.0 > MAX_RUN_AGE_H:
                    continue
                items.append({"run_id": d.name, "kind": j.get("kind") or "", "state": str(j.get("state")), "finished_at": fin,
                              "children": len(j.get("children") or []), "viewed": bool(j.get("viewed")) or _viewed_marker(d) or d.name in ctx.viewed_runs})
                break
    note = "from run files"
    if ctx.allow_http:
        try:
            import httpx

            r = httpx.get(f"{agent_url()}/agents/runs", params={"person": ctx.person}, timeout=1.5)
            if r.status_code == 200:
                have = {i["run_id"] for i in items}
                for j in r.json() or []:
                    rid = str(j.get("run_id") or "")
                    if not _RUN_ID.match(rid) or rid in have:
                        continue
                    fin = _date_ts(j.get("finished") or j.get("ended") or j.get("started")) or ctx.now_ts
                    if (ctx.now_ts - fin) / 3600.0 > MAX_RUN_AGE_H:
                        continue
                    items.append({"run_id": rid, "kind": str(j.get("kind") or ""), "state": str(j.get("state")), "finished_at": fin,
                                  "children": len(j.get("children") or []), "viewed": rid in ctx.viewed_runs})
                note = "from run files and the agent service"
        except Exception:
            note = "from run files (agent service not reachable)"
    return Reading(items, True, note)


# --------------------------------------------------------------------------------------------- queue
def queue_in_flight(dedupe_key: str, qdir: Path | None = None) -> bool:
    """Is there already a pending or approved queue item for this key (so firing again would only duplicate it)?"""
    d = qdir or (data_dir() / "queue")
    if not d.exists():
        return False
    for p in d.glob("q_*.json"):
        try:
            it = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if it.get("dedupe_key") == dedupe_key and it.get("status") in ("pending", "approved"):
            return True
    return False


# --------------------------------------------------------------------------------------------- bundle
@dataclass
class Readers:
    """The set of readers a briefing run uses. Tests and the evaluation swap any of them."""

    routines: Reader = read_routines
    skills: Reader = read_skills
    calendar: Reader = read_calendar
    git: Reader = read_git
    runs: Reader = read_runs
    in_flight: Callable[[str], bool] = queue_in_flight
    extra: dict[str, Any] = field(default_factory=dict)


def live_readers() -> Readers:
    return Readers()
