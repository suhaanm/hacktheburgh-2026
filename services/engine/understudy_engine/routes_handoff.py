"""Handoff routes (engine-handoff track). `api/app.py` includes `router` when importable.

    GET  /onboarding/questions?role=        POST /onboarding
    GET  /memory                            PUT  /memory                 409 stale_revision
    POST /memory/forget                     GET  /memory/proposals       POST /memory/proposals/{id}/approve|reject
    POST /memory/corrections (additive)     GET  /memory/export (additive)
    GET  /coach/state?person=
    GET  /graph/work?person=                {meta, data}
    POST /routines/detect                   GET  /routines?person=       {meta, data}
    POST /routines/{id}/consent             POST /routines/{id}/shadow
    GET  /presence?person=                  {meta, data}     PUT /presence/quiet_hours
    POST /offhours/decide                   GET  /offhours/report?since=

Nothing here calls a model, and with UNDERSTUDY_MOCK=1 everything is deterministic (fixed seeds; "now" is the end of a
synthetic persona's data, never the wall clock). Writes to memory, consent and quiet hours are the worker's own actions:
a request is refused (403) when it names another actor in ``X-Understudy-Actor`` (page, agent, model, tool ...) or comes
from an origin other than localhost; every refusal is written to the audit log without the refused text (MEM-2, SEC-8).
"""
from __future__ import annotations

import dataclasses
import json
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, Query, Request
from . import http_guard
from fastapi.responses import JSONResponse

from .memory import (
    ExpertPolicy, MemoryStore, NotOnboarded, OnboardingError, RuleEngine, RuleError, StaleRevision, UnknownRole, WriteRefused, change_profile,
    load_pack, load_profile, onboard, profile_name, profile_view, questions_payload,
)
from .memory.onboarding import _KEEP as _NAME_KEEP
from .memory import doc as D
from .memory.hours import DEFAULT_QUIET, normalise_window, parse_quiet_line, quiet_line
from .memory.paths import data_dir, is_mock
from .memory.store import WORKER_ACTORS, atomic_write, now_iso
from .presence.model import PresenceModel, PriorHours, window_mask
from .presence.survival import DEFAULT_GRID_MIN, ReturnTimeModel, decide, threshold
from .presence.timeline import day_states_from_events, get_tz, spells_from_events
from .routines.detect import DetectConfig, detect_routines
from .routines.gate import MemorySkillSource
from .routines.graph import build_work_graph
from .routines.sources import PersonData, PersonSource, shared_source
from .yamlcache import load_yaml_file
from .routines.store import ConsentError, RoutineStore

router = APIRouter(tags=["handoff"])

_lock = threading.RLock()
_cache: dict[tuple, Any] = {}
DEFAULT_GAIN, DEFAULT_CAP = 1.0, 0.10


# ------------------------------------------------------------------------------------------------ helpers
def _error(status: int, code: str, message: str, **extra: Any) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}, **extra})


def _audit(kind: str, note: str, outcome: str = "refused") -> None:
    """Append one redacted line to data/audit.jsonl. Never carries the refused text."""
    line = {"t": now_iso(), "actor": "system", "kind": kind, "routine": None, "run_id": None, "tier": None, "outcome": outcome,
            "note": note[:120]}
    try:
        p = data_dir() / "audit.jsonl"
        p.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(p, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
        try:
            os.write(fd, (json.dumps(line) + "\n").encode())
        finally:
            os.close(fd)
    except OSError:
        pass


def _clean_actor(a: str) -> str:
    return "".join(ch for ch in a if ch.isalnum() or ch in "-_.:")[:24] or "unknown"


def _mem() -> MemoryStore:
    return MemoryStore(on_refusal=lambda actor, what: _audit("memory_write_refused", f"{what}: actor {_clean_actor(actor)}"))


def _guard(request: Request) -> JSONResponse | None:
    """Only the worker's own UI writes. Anything naming another actor, or from a foreign origin, is refused."""
    actor = http_guard.actor_of(request)
    origin = request.headers.get("origin")
    if origin is not None and not http_guard.origin_allowed(origin):          # judged first: a page that also names no actor is still "a foreign origin"
        _audit("memory_write_refused", f"origin {_clean_actor(origin)} on {request.url.path}")
        return _error(403, "write_refused", "Writes only come from the worker's own app on this machine.")
    if actor not in WORKER_ACTORS:
        _audit("memory_write_refused", f"actor {_clean_actor(actor)} on {request.url.path}")
        return _error(403, "write_refused", f"Only the worker can change memory, consent or quiet hours; the actor {_clean_actor(actor)!r} cannot.")
    return None


def _actor(request: Request) -> str:
    return http_guard.actor_of(request)


def _src() -> PersonSource:
    return shared_source()          # one per data root: its parsed-events cache lives until a person's files change (see routines/sources.py)


def _role(mem: MemoryStore | None = None, pd: PersonData | None = None) -> str:
    if pd is not None:
        return pd.role
    m = (mem or _mem()).read()
    return m.role if m.role != "unknown" else "benefits-processor"


def _pack(role: str):
    try:
        return load_pack(role)
    except KeyError:
        return load_pack("benefits-processor")


_current_memo: dict[tuple[str, str], tuple[PersonData, PersonData]] = {}


def _as_current(pd: PersonData | None) -> PersonData | None:
    """A real worker who changed role in setup but has not yet done any work under the new role: the role is the profile's and there are no current-role
    events, so routines, the hit list and the graph start clean for the new pack instead of reading the old role's work with the wrong pack. The earlier
    events stay on ``earlier_events``. Only after a recorded role change (``history``), so a first setup is read exactly as before."""
    if pd is None:
        return pd
    prof = load_profile(_mem()) or {}
    role = prof.get("role")
    if not role or prof.get("person") != pd.person:
        return pd
    # History is kept per role and is never mixed: when the worker's events carry more than one role (earlier work under another role, seeded history, live capture beside it), the current
    # events are ALL the events of the profile's role, in any order the worker has switched, and every other role's events stay on ``earlier_events`` (readable, never in a count).
    hit = _current_memo.get((pd.person, role))
    if hit is not None and hit[0] is pd:                     # PersonSource hands out the same object until the person's files change, so the split is made once per data version
        return hit[1]
    allev = [*pd.earlier_events, *pd.events]
    roles = {e.role for e in allev}
    if len(roles) > 1 and role in roles:
        allev.sort(key=lambda e: (e.t, e.id))
        cur = [e for e in allev if e.role == role]
        # the person's own truth file (a generated learner's trajectory) describes one role's days; it does not describe another role's
        truth = pd.truth if role == (pd.truth or {}).get("role", pd.role) else None
        out = dataclasses.replace(pd, role=role, events=cur, earlier_events=[e for e in allev if e.role != role], truth=truth)
        if len(_current_memo) > 8:
            _current_memo.clear()
        _current_memo[(pd.person, role)] = (pd, out)
        return out
    if pd.origin != "real" or not prof.get("history") or role == pd.role:
        return pd
    return dataclasses.replace(pd, role=role, events=[], earlier_events=[*pd.earlier_events, *pd.events])


def hidden_routine_roles() -> set[str]:
    """Roles the worker has left (``history``) and is not in now: their routines are not listed under the new role."""
    prof = load_profile(_mem()) or {}
    return {str(h.get("role")) for h in (prof.get("history") or []) if h.get("role")} - {str(prof.get("role") or "")}


def _resolve(person: str | None) -> tuple[str | None, PersonData | None]:
    src = _src()
    if person:
        return person, _as_current(src.load(person))
    prof = load_profile(_mem())
    if prof and prof.get("person"):
        # The caller is someone: every route that defaults its person answers for THEM, even before any of their work is captured (then pd is None and the route says so calmly).
        # It never falls back to another person's data or id (the engine's default persona is for a stack nobody has set up).
        return prof["person"], _as_current(src.load(prof["person"]))
    p = src.default_person()
    return p, _as_current(src.load(p) if p else None)


def _meta(origin: str, n: int, n_unit: str, split: str | None = None, note: str | None = None) -> dict[str, Any]:
    return {"origin": origin, "n": n, "n_unit": n_unit, "split": split, "interval_level": 0.95, "note": note, "generated_at": now_iso()}


def _unknown_person(person: str | None) -> JSONResponse:
    # Calm and without any other person's id: a worker's page never learns who else the engine knows.
    return _error(404, "unknown_person", "Nothing has been captured for this person yet, so there is nothing to show. It fills in as work is captured.")


def _demo(mem: MemoryStore) -> dict[str, Any]:
    """Demo configuration written by ``python -m understudy_engine.demo seed`` (empty in a real install)."""
    return mem.load_state().get("demo") or {}


def _case_for(person: str | None, case: int | None, mem: MemoryStore) -> int | None:
    """The learner case to show: the caller's, else the demo person's seeded case, else the last case."""
    if case is not None:
        return case
    d = _demo(mem)
    return d.get("case") if d.get("person") and d.get("person") == person else None


LEARNER_ROLE = "benefits-processor"      # the learner trajectories (data/synthetic/learners) are thirty benefits cases each


def _learner(person: str | None, case: int | None, role: str | None = None):
    """A learner-trajectory person (data/synthetic/learners): skill state from a SkillTracker built case by case. Only for the role those trajectories are about: the same worker id
    under another role (programmer, data analyst) has no learner trajectory, and the benefits skill state is never read as theirs."""
    from .routines.learners import learner_people, tracker_at

    if role is not None and role != LEARNER_ROLE:
        return None
    if person and person in learner_people():
        return tracker_at(person, case)
    return None


def _tz(pd: PersonData) -> str:
    if pd.truth and pd.truth.get("tz"):
        return str(pd.truth["tz"])
    return os.environ.get("UNDERSTUDY_TZ", "Europe/London") if pd.origin == "real" else "UTC"


# ------------------------------------------------------------------------------------------------ onboarding
@router.get("/onboarding/questions")
def onboarding_questions(role: str = Query("benefits-processor")):
    try:
        return questions_payload(role)
    except KeyError:
        return _error(404, "unknown_role", f"No role pack {role!r}.")


def _onboarding_error(e: OnboardingError) -> JSONResponse:
    extra = {"roles": e.valid} if isinstance(e, UnknownRole) else {}
    return _error(409 if isinstance(e, NotOnboarded) else 422, e.code, str(e), **extra)


def _name_arg(body: dict[str, Any]) -> Any:
    """``name`` absent: keep it. ``null`` or ``""``: clear it. Anything else is validated by ``clean_name``."""
    return body["name"] if "name" in body else _NAME_KEEP


@router.post("/onboarding")
def post_onboarding(request: Request, body: dict[str, Any] = Body(...)):
    """First run, or "Set up again". Safe to repeat: the same body twice changes nothing the second time. For a worker who already exists use
    ``POST /profile``, which also keeps the capture choice and usual hours across a role change."""
    if (r := _guard(request)):
        return r
    role = body.get("role")
    if not role:
        return _error(422, "role_required", "Pick a role first.")
    try:
        out = onboard(_mem(), str(role), body.get("answers") or {}, body.get("person"), name=_name_arg(body))
    except OnboardingError as e:
        return _onboarding_error(e)
    except WriteRefused as e:
        return _error(403, "write_refused", str(e))
    if out.get("role_changed"):
        _audit("profile_changed", f"role {out.get('previous_role')} to {out['role']} (onboarding)", outcome="ok")
    return out


@router.get("/profile")
def get_profile():
    """Who the worker is on this device: ``{person, role, name?, since, history: [{role, since, until}], roles: [{id, name, summary, depth}]}``.
    404 ``not_onboarded`` before the first setup. ``roles`` is the closed list a role change may use."""
    out = profile_view(_mem())
    if out is None:
        return _error(404, "not_onboarded", "No profile yet: finish onboarding first (POST /onboarding).")
    return out


def _post_profile(request: Request, body: dict[str, Any]):
    """Change the worker's role and/or name: ``{role?, name?, answers?}``. At least one of role, name, answers. Worker only (the same guard as every memory
    write). The same body twice is a no-op. A new role switches the pack (skills, rules and routines start clean for it; the person id, name, quiet hours,
    capture choice and usual hours stay); the earlier role stays in ``history`` and its work stays readable under it (``GET /growth?role=``). The audit line
    names the roles and never the name."""
    if (r := _guard(request)):
        return r
    mem = _mem()
    name_before = profile_name(mem.read()) or ""
    try:
        out = change_profile(mem, role=(str(body["role"]) if body.get("role") else None), name=_name_arg(body), answers=body.get("answers") or {},
                             person=body.get("person"))
    except OnboardingError as e:
        return _onboarding_error(e)
    except WriteRefused as e:
        return _error(403, "write_refused", str(e))
    flags = []
    if out.get("role_changed"):
        flags.append(f"role {out.get('previous_role')} to {out['role']}")
    name_after = out.get("name") or ""
    if name_after != name_before:
        flags.append("name set" if name_after else "name cleared")
    if flags:
        _audit("profile_changed", "; ".join(flags), outcome="ok")
    return out


@router.post("/profile")
def post_profile(request: Request, body: dict[str, Any] = Body(...)):
    return _post_profile(request, body)


@router.patch("/profile")
def patch_profile(request: Request, body: dict[str, Any] = Body(...)):
    return _post_profile(request, body)


@router.get("/identity")
def get_identity():
    """The person id the engine owns (created by POST /onboarding). The desktop app and the extension adopt it. ``name`` is there only when the worker gave one."""
    mem = _mem()
    prof = load_profile(mem)
    if not prof or not prof.get("person"):
        return _error(404, "not_onboarded", "No identity yet: finish onboarding first (POST /onboarding).")
    out = {"person": prof["person"], "role": prof.get("role") or mem.read().role}
    if (nm := profile_name(mem.read())):
        out["name"] = nm
    return out


# ------------------------------------------------------------------------------------------------ memory
def _rules() -> RuleEngine:
    mem = _mem()
    return RuleEngine(mem, policy=ExpertPolicy.from_pack(_pack(_role(mem))))


@router.get("/memory")
def get_memory():
    return _mem().view()


@router.put("/memory")
def put_memory(request: Request, body: dict[str, Any] = Body(...)):
    if (r := _guard(request)):
        return r
    if "markdown" not in body or "base_revision" not in body:
        return _error(422, "bad_request", "Send {markdown, base_revision}.")
    try:
        rev = _mem().write_markdown(str(body["markdown"]), int(body["base_revision"]), actor=_actor(request))
    except StaleRevision as e:
        return _error(409, "stale_revision", f"Memory is at revision {e.current}; your edit started from {e.base}. Reload, then submit again.",
                      current_revision=e.current)
    except WriteRefused as e:
        return _error(403, "write_refused", str(e))
    except (TypeError, ValueError):
        return _error(422, "bad_request", "base_revision must be an integer.")
    return {"revision": rev}


@router.post("/memory/forget")
def post_forget(request: Request, body: dict[str, Any] = Body(...)):
    if (r := _guard(request)):
        return r
    lid = body.get("line_id")
    if not lid:
        return _error(422, "bad_request", "Send {line_id}.")
    try:
        rev = _rules().forget(str(lid), actor=_actor(request))
    except KeyError:
        return _error(404, "unknown_line", f"No memory line {lid!r}.")
    except WriteRefused as e:
        return _error(403, "write_refused", str(e))
    _invalidate()
    return {"revision": rev}


@router.get("/memory/proposals")
def get_proposals():
    return _rules().proposals()


@router.post("/memory/proposals/{proposal_id}/{verb}")
def decide_proposal(proposal_id: str, verb: str, request: Request, body: dict[str, Any] | None = Body(None)):
    if verb not in ("approve", "reject"):
        return _error(404, "not_found", "Use approve or reject.")
    if (r := _guard(request)):
        return r
    rules = _rules()
    try:
        if verb == "approve":
            out = rules.approve(proposal_id, actor="worker_approval" if _actor(request) in WORKER_ACTORS else _actor(request),
                                ceiling=(body or {}).get("ceiling"))
        else:
            out = rules.reject(proposal_id, actor=_actor(request))
    except KeyError:
        return _error(404, "unknown_proposal", f"No proposal {proposal_id!r}.")
    except RuleError as e:
        return _error(409, "not_open", str(e))
    except WriteRefused as e:
        return _error(403, "write_refused", str(e))
    return out


@router.post("/memory/corrections")
def post_correction(request: Request, body: dict[str, Any] = Body(...)):
    """The worker corrected the system. Three consistent corrections raise a proposal (never an active rule)."""
    if (r := _guard(request)):
        return r
    try:
        return _rules().record_correction(str(body.get("subject", "")), body.get("value", ""), actor=_actor(request),
                                          kind=str(body.get("kind", "preference")), ceiling=str(body.get("ceiling", "A1")))
    except RuleError as e:
        return _error(422, "bad_correction", str(e))
    except WriteRefused as e:
        return _error(403, "write_refused", str(e))


@router.get("/memory/export")
def get_export():
    return _mem().export_bundle()


# ------------------------------------------------------------------------------------------------ coach state
_CHIP = {1: "full", 2: "small", 3: "dot", 4: "gone"}
_LEVEL_MASTERY = {1: 0.2, 2: 0.4, 3: 0.65, 4: 0.85}


def _task_open(request: Request, person: str | None) -> bool | None:
    """Whether the live coach has an open task window for this person (read-only: it never moves the dignity gate). None when that cannot be said."""
    if not person:
        return None
    try:
        from .routes_coach import brain

        return bool(brain(request).snapshot(person).task_open)
    except Exception:                       # noqa: BLE001 - the state is still worth sending without the flag
        return None


@router.get("/coach/state")
def coach_state(request: Request, person: str | None = Query(None), step: int | None = Query(None, ge=0), case: int | None = Query(None, ge=1)):
    """Today screen. For a learner-trajectory person the level and chip come from the analytics track's SkillTracker at
    ``case`` (default: the last case); otherwise from the Skill state lines of the worker's memory file."""
    mem = _mem()
    doc = mem.read()
    pid, pd = _resolve(person)
    learner = _learner(pid, _case_for(pid, case, mem), pd.role if pd else None)
    if person and person.startswith("p_learn") and learner is None and (pd is None or pd.role == LEARNER_ROLE):
        return _unknown_person(person)
    pack = _pack(doc.role if doc.role != "unknown" and learner is None else (pd.role if pd else "benefits-processor"))
    task_doc = _task_yaml(pack.id)
    steps = list(task_doc.get("steps") or []) or ["Start the task", "Do the checks", "Write it up"]
    total = len(steps)
    cur = step
    if cur is None and pd is not None:
        if learner is not None:
            tid = learner.trace["task_id"]
            cur = sum(1 for e in pd.events if e.task_id == tid and e.type == "progress")
        else:
            eps = [e for e in _src().episodes(pd) if e.task_id]
            cur = len(eps[-1].progress_t) if eps else 1
    cur = min(max(1, cur or 1), total)
    prefs = [ln.text for ln in (doc.section("Preferences", create=False).lines() if doc.section("Preferences", create=False) else [])]
    detailed = any("Summaries: detailed" in p for p in prefs)
    mastery: dict[str, float] = {}
    if learner is not None:
        snap = learner.snapshot

        def skill_level(sk) -> int:
            return min((snap[c]["level"] if c in snap else 1) for c in sk.get("cogs", ["?"]))

        teaching = next((sk for sk in pack.skills if skill_level(sk) < 4), pack.skills[-1] if pack.skills else None)
        cs = learner.tracker.coach_state(list((teaching or {}).get("cogs", [])), learner.t_ref)
        lvl = int(cs["level"][1:])
        chip = cs["chip"]
        for sk in pack.skills:
            for c in sk.get("cogs", []):
                mastery[c] = round(float(snap[c]["mastery"]) if c in snap else learner.tracker.params.p_init, 2)
        extra = {"case": learner.case, "cases_total": learner.n_cases, "person": learner.person}
    else:
        levels = D.skill_levels(doc)
        skills = [s for s in pack.skills if s["id"] in levels] or pack.skills
        teaching = next((s for s in skills if levels.get(str(s["id"]), {"level": 1})["level"] < 4), skills[-1] if skills else None)
        lvl = levels.get(str(teaching["id"]), {"level": 1})["level"] if teaching else 1
        chip = _CHIP[lvl]
        for sk in pack.skills:
            m = _LEVEL_MASTERY[levels.get(str(sk["id"]), {"level": 1})["level"]]
            for c in sk.get("cogs", []):
                mastery[c] = round(max(mastery.get(c, 0.0), m), 2)
        # `active`: whether a task is really open now, so the Home row and the Today screen say "coaching" only while one is. Left out when it cannot be said.
        open_now = _task_open(request, pid)
        extra = {} if open_now is None else {"active": open_now}
    prompts = (teaching or {}).get("prompts", {})
    key = f"L{min(lvl, 3)}" if lvl < 4 else None
    if detailed and lvl > 1 and lvl < 4:
        key = "L1"
    message = prompts.get(key, "") if key else ""
    why = (teaching or {}).get("expert_signal", "") if teaching else ""
    return {"task": {"id": task_doc.get("id", "t_task"), "name": task_doc.get("name") or _lesson_name(teaching, pack), "step": cur, "steps_total": total},
            "level": f"L{lvl}", "chip": chip, "message": message, "why": why, "mastery": mastery, **extra}


def _lesson_name(skill: dict[str, Any] | None, pack) -> str:
    """The name of the task on the Today screen when the pack has no task of its own (the programmer and the data analyst): the lesson being taught, in the
    curriculum's own words ("Read the failing trace before changing code"), never the role label."""
    label = str((skill or {}).get("label") or "").strip()
    return label or str(pack.name)


def _task_yaml(role: str) -> dict[str, Any]:
    import yaml

    from .memory.paths import packs_dir

    p = packs_dir() / role / "tasks" / "task.yaml"
    try:
        return load_yaml_file(p) or {}
    except (OSError, yaml.YAMLError):
        return {}


# ------------------------------------------------------------------------------------------------ routines
def _detected(pd: PersonData, mem: MemoryStore) -> list[dict[str, Any]]:
    """Detection for one person, cached per data version. Skill gates are refreshed separately at read time."""
    src = _src()
    if not pd.events:
        return []                                   # nothing done yet under this role: nothing to find
    key = ("detect", pd.person, src._signature(pd.person), pd.role, len(pd.events))
    with _lock:
        hit = _cache.get(key)
    if hit is not None:
        return hit
    pack = _pack(pd.role)
    eps = src.episodes(pd)
    doc = mem.read()
    out = detect_routines(eps, pack, person=pd.person, now=pd.t_last, skills=MemorySkillSource(doc, pack), cfg=DetectConfig())
    with _lock:
        for k in [k for k in _cache if k[0] == "detect" and k[1] == pd.person]:
            del _cache[k]
        _cache[key] = out
    return out


def _invalidate() -> None:
    with _lock:
        for k in [k for k in _cache if k[0] in ("graph",)]:
            del _cache[k]


def _detections_for(pd: PersonData, mem: MemoryStore) -> list[dict[str, Any]]:
    """The routines to show for ``pd``. In a seeded demo the finder reads another persona's traces (the learner trajectories
    are one task type, so they hold no calculator-entry routine) and only the listed routine ids, labelled as the demo person's."""
    d = _demo(mem)
    if d.get("person") == pd.person and d.get("routine_source"):
        other = _src().load(d["routine_source"])
        if other is not None and other.role == pd.role:           # the demo person's routines come from another persona of the SAME role; under another role the worker's own events are read
            ids = set(d.get("routine_ids") or [])
            return [{**r, "person": pd.person} for r in _detected(other, mem) if not ids or r["id"] in ids]
    return _detected(pd, mem)


def _sync_routines(pd: PersonData, mem: MemoryStore, case: int | None = None) -> RoutineStore:
    """Detect (cached per data version), merge into the registry (the worker's decisions are kept), and re-evaluate the skill
    gates against current skill state: a learner's tracker at ``case``, or the Skill state lines of the memory file."""
    st = RoutineStore(mem)
    st.merge(_detections_for(pd, mem))
    learner = _learner(pd.person, _case_for(pd.person, case, mem), pd.role)
    if learner is not None:
        st.refresh_gate(learner.tracker, learner.t_ref, pd.person)
    else:
        st.refresh_gate(MemorySkillSource(mem.read(), _pack(pd.role)), pd.t_last, pd.person)
    return st


@router.post("/routines/detect")
def post_detect(request: Request, body: dict[str, Any] | None = Body(None)):
    mem = _mem()
    pid, pd = _resolve((body or {}).get("person"))
    if pd is None:
        return _unknown_person(pid)
    st = _sync_routines(pd, mem)
    rows = [r for r in st.list() if r.get("last_seen") is not None]
    proposable = [r for r in rows if r["proposable"]]
    precision = recall = None
    if pd.truth and "routines" in pd.truth and not _demo(mem).get("routine_source"):
        from .routines.evaluate import _score_clusters

        labels = {i["task_id"]: r["name"] for r in pd.truth["routines"] for i in r["instances"]}
        counts = {r["name"]: len(r["instances"]) for r in pd.truth["routines"]}
        det = _detections_for(pd, mem)
        scored = _score_clusters([d["member_task_ids"] for d in det if d["value"]["confidence"] >= 0.5 or d["template_id"]], labels, counts, 3)
        precision, recall = scored["precision"], scored["recall"]
    return {"proposals": len(proposable), "precision": precision, "recall": recall, "routines": len(rows)}


@router.get("/routines")
def get_routines(person: str | None = Query(None), case: int | None = Query(None, ge=1)):
    mem = _mem()
    pid, pd = _resolve(person)
    if pd is None:
        return _unknown_person(pid)
    st = _sync_routines(pd, mem, case)
    left = hidden_routine_roles()
    rows = [r for r in st.list() if _owner(st, r["id"]) == pd.person and r.get("role") not in left]
    eps = len(_src().episodes(pd))
    note = ("Found in the recorded traces; value uses a wage of 15 pounds an hour as an illustration and a build cost per routine from the role pack."
            if pd.origin == "synthetic" else "Found in your own traces; value uses a wage of 15 pounds an hour as an illustration.")
    return {"meta": _meta(pd.origin, eps, "episodes", "unsupervised; truth is only used for the precision score", note), "data": rows}


def _owner(st: RoutineStore, rid: str) -> str | None:
    return st._load()["routines"].get(rid, {}).get("person")


@router.post("/routines/{routine_id}/consent")
def post_consent(routine_id: str, request: Request, body: dict[str, Any] = Body(...)):
    if (r := _guard(request)):
        return r
    mem = _mem()
    st = RoutineStore(mem)
    try:
        st.get_raw(routine_id)
    except KeyError:
        pid, pd = _resolve(None)
        if pd is not None:
            st = _sync_routines(pd, mem)
    try:
        prof = load_profile(mem)
        return st.consent(
            routine_id, str(body.get("mode", "")), irreversible_unattended=list(body.get("irreversible_unattended") or []),
            typed_confirm=body.get("typed_confirm") if isinstance(body.get("typed_confirm"), str) else None,
            skill_override=bool(body.get("skill_override", False)), actor=_actor(request),
            person=(prof or {}).get("person", "p_me"))
    except KeyError:
        return _error(404, "unknown_routine", f"No routine {routine_id!r}.")
    except ConsentError as e:
        return _error(e.status, e.code, str(e))
    except WriteRefused as e:
        return _error(403, "write_refused", str(e))
    finally:
        _invalidate()


EVIDENCE_ACTORS = WORKER_ACTORS | {"agent"}


def _guard_evidence(request: Request) -> JSONResponse | None:
    """Shadow results are evidence, not memory: the worker's app or the agent service may post them. Pages, models and tools may not."""
    actor = http_guard.actor_of(request)
    origin = request.headers.get("origin")
    if origin is not None and not http_guard.origin_allowed(origin):
        _audit("shadow_write_refused", f"origin {_clean_actor(origin)} on {request.url.path}")
        return _error(403, "write_refused", "Only the worker's app or the agent service can post shadow results.")
    if actor not in EVIDENCE_ACTORS:
        _audit("shadow_write_refused", f"actor {_clean_actor(actor)} on {request.url.path}")
        return _error(403, "write_refused", "Only the worker's app or the agent service can post shadow results.")
    return None


@router.post("/routines/{routine_id}/shadow")
def post_shadow(routine_id: str, request: Request, body: dict[str, Any] | None = Body(None)):
    """Record shadow comparisons and apply the autonomy ladder (``understudy_engine.trust.ladder``).

    Body for the agent's shadow runner::

        { "results": [ { "run_id": "r_0042", "matched": true, "reason": "optional, at most 200 characters, no page text" } ] }

    ``matched`` is the code-checked verdict (the compiled routine's result equals the worker's). An item may carry
    ``"event": "failure" | "undo" | "injection"`` instead of ``matched``; that demotes one rung and restarts the count (an
    injection hit also blocks the routine until the worker switches it on again). ``run_id`` is optional but should be sent:
    one already recorded for this routine is ignored (a retried POST is harmless) and reported in ``duplicates``. At most 1000
    results per request. Each accepted result is appended to ``data/routines/<id>/shadow_log.jsonl``.
    Response: ``{runs, matches, wilson_lower, rung, promoted, demoted, accepted, duplicates, blocked, ceiling, next_rung, needs}``.
    Errors: 404 unknown routine, 409 ``not_enabled`` (the worker has not switched the routine on) or ``blocked``, 422 bad body.
    Also accepted: ``{matched}``, ``{runs, matches}``, ``{event}``. An empty body only simulates one run, and only in mock mode.
    """
    if (r := _guard_evidence(request)):
        return r
    mem = _mem()
    st = RoutineStore(mem)
    b = body or {}
    if "results" in b and not isinstance(b["results"], list):
        return _error(422, "bad_result", "results must be a list of {run_id, matched, reason?}.")
    try:
        simulated = False
        if not b:
            if not is_mock():
                return _error(422, "body_required", "Send {results: [{run_id, matched}]} (or {matched}, {runs, matches}, {event}) from a shadow run.")
            raw = st.get_raw(routine_id)
            n = raw["shadow"]["runs"]
            import hashlib

            h = int(hashlib.sha1(f"{routine_id}:{n}".encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
            b, simulated = {"matched": h < 0.95}, True   # mock mode only: a deterministic stand-in for one shadow run
        out = st.shadow(routine_id, results=b.get("results"), matched=b.get("matched", b.get("match")), runs=b.get("runs"),
                        matches=b.get("matches"), event=b.get("event"), actor=_actor(request))
        if simulated:
            out["simulated"] = True
        _invalidate()
        return out
    except KeyError:
        return _error(404, "unknown_routine", f"No routine {routine_id!r}.")
    except ConsentError as e:
        return _error(e.status, e.code, str(e))


_REC_VALIDATOR: Any = None
MAX_RECORDING_STEPS = 300


def _recording_validator():
    global _REC_VALIDATOR
    if _REC_VALIDATOR is None:
        from jsonschema import Draft202012Validator

        from .memory.paths import repo_root

        schema = json.loads((repo_root() / "packages" / "schema" / "recording.schema.json").read_text())
        _REC_VALIDATOR = Draft202012Validator(schema)
    return _REC_VALIDATOR


@router.post("/routines/{routine_id}/recording")
def post_recording(routine_id: str, body: dict[str, Any] = Body(...)):
    """L1 recording batch from the extension for a routine the worker opted in (shadow, approval or unattended).

    Validated against packages/schema/recording.schema.json (values never present, sensitive fields only counted, at most
    300 steps) and stored at data/routines/<id>/recording.json for the compile step. Not guarded by the worker-actor check:
    the extension posts it; consent is what gates it.
    """
    mem = _mem()
    st = RoutineStore(mem)
    try:
        raw = st.get_raw(routine_id)
    except KeyError:
        return _error(404, "unknown_routine", f"No routine {routine_id!r}.")
    mode = st.effective(raw)["consent"]["mode"]
    if mode not in ("shadow", "approval", "unattended"):
        return _error(409, "not_opted_in", "Recording only starts after you switch this routine on (shadow, approval or unattended).")
    steps = body.get("steps")
    if isinstance(steps, list) and len(steps) > MAX_RECORDING_STEPS:
        return _error(422, "too_many_steps", f"A recording has at most {MAX_RECORDING_STEPS} steps; this one has {len(steps)}.")
    if body.get("routine_id") != routine_id:
        return _error(422, "routine_mismatch", "routine_id in the body must match the routine in the path.")
    errors = sorted(_recording_validator().iter_errors(body), key=lambda e: list(e.path))
    if errors:
        e = errors[0]
        where = "/".join(str(x) for x in e.path) or "recording"
        return _error(422, "bad_recording", f"{where}: {e.message[:200]}", problems=len(errors))
    d = st.bundle_root / routine_id
    d.mkdir(parents=True, exist_ok=True)
    atomic_write(d / "recording.json", json.dumps(body, indent=1))
    _audit("recording_stored", f"{routine_id}: {len(body['steps'])} steps", outcome="ok")
    return {"steps": len(body["steps"]), "accepted": True}


# ------------------------------------------------------------------------------------------------ work graph
@router.get("/graph/work")
def get_work_graph(person: str | None = Query(None), case: int | None = Query(None, ge=1)):
    mem = _mem()
    pid, pd = _resolve(person)
    if pd is None:
        return _unknown_person(pid)
    st = _sync_routines(pd, mem, case)
    doc = mem.read()
    learner = _learner(pd.person, _case_for(pd.person, case, mem), pd.role)
    now = learner.t_ref if learner is not None else (pd.t_last if pd.origin == "synthetic" else time.time())
    g = build_work_graph(st, doc, _pack(pd.role), now, skill_snapshot=learner.snapshot if learner is not None else None, person=pd.person)
    return {"meta": _meta(pd.origin, len(g["nodes"]), "episodes", None,
                          "Routines, skills, memory lines and automations. Strength fades with disuse along the skills module's forgetting curve; "
                          "deleting a node's memory line edits your memory file."), "data": g}


# ------------------------------------------------------------------------------------------------ presence
def _prior_for(pd: PersonData, mem: MemoryStore) -> PriorHours:
    prof = load_profile(mem)
    if prof and prof.get("person") == pd.person and prof.get("hours"):
        h = prof["hours"]
        base = _pack(pd.role).presence_prior()
        return PriorHours.from_pack_prior({"hours": h, "active_in_hours": base.get("active_in_hours", 0.7), "active_out_of_hours": base.get("active_out_of_hours", 0.03)})
    return PriorHours.from_pack_prior(_pack(pd.role).presence_prior())


def _fit_presence(pd: PersonData, mem: MemoryStore) -> dict[str, Any]:
    src = _src()
    prior = _prior_for(pd, mem)
    key = ("presence", pd.person, src._signature(pd.person), (prior.start_min, prior.end_min, prior.days, prior.p_in, prior.p_out), pd.role, len(pd.events))
    with _lock:
        hit = _cache.get(key)
    if hit is not None:
        return hit
    tz = _tz(pd)
    first = last = None
    if pd.truth and pd.truth.get("start_date"):
        from datetime import date, timedelta

        first = date.fromisoformat(pd.truth["start_date"])
        last = first + timedelta(days=int(pd.truth["n_days"]) - 1)
    days = day_states_from_events(pd.events, tz=tz, first_day=first, last_day=last)
    model = PresenceModel(prior).fit(days)
    if len(days) >= 7:
        model.tune(days)
    spells = spells_from_events(pd.events, tz=tz)
    out = {"model": model, "days": days, "returns": ReturnTimeModel(spells), "tz": tz, "n_spells": len(spells)}
    with _lock:
        for k in [k for k in _cache if k[0] == "presence" and k[1] == pd.person]:
            del _cache[k]
        _cache[key] = out
    return out


def _idle_capacity(fit: dict[str, Any], model: PresenceModel) -> dict[str, float]:
    """The idle-capacity interval (a 200-draw day bootstrap with fixed seeds: the same every time) once per fit, not once per request. ``fit`` is the cached
    per-data-version dict, so a change of the person's files or of their hours makes a new fit and a new interval."""
    got = fit.get("_idle_capacity")
    if got is None:
        got = fit["_idle_capacity"] = model.idle_capacity_interval()
    return got


def _now_for(pd: PersonData, now: str | None) -> float:
    if now:
        return datetime.fromisoformat(now.replace("Z", "+00:00")).timestamp()
    return pd.t_last + 600.0 if pd.origin == "synthetic" else time.time()


def _situation(pd: PersonData, now_ts: float, tz: str) -> dict[str, Any]:
    """Time of week, minutes idle, and whether the screen is locked or the machine asleep, from events up to ``now``."""
    zone = get_tz(tz)
    ev = [e for e in pd.events if e.actor == "human" and e.t.timestamp() <= now_ts]
    from .presence.timeline import INPUT_TYPES

    last_in = next((e.t.timestamp() for e in reversed(ev) if e.type in INPUT_TYPES), None)
    state_ev = next((e for e in reversed(ev) if e.type in ("lock", "unlock", "sleep", "resume")), None)
    loc = datetime.fromtimestamp(now_ts, zone)
    return {
        "tow_min": loc.weekday() * 1440 + loc.hour * 60 + loc.minute + loc.second / 60.0,
        "idle_raw_min": (now_ts - last_in) / 60.0 if last_in else None,
        "idle_min": max(5.0, (now_ts - last_in) / 60.0) if last_in else 5.0,
        "locked": bool(state_ev and state_ev.type == "lock"), "asleep": bool(state_ev and state_ev.type == "sleep"),
        "has_screen_events": state_ev is not None,
        "dow": loc.weekday(), "local": loc.isoformat(),
    }


def _quiet(mem: MemoryStore) -> dict[str, Any]:
    sec = mem.read().section("Preferences", create=False)
    for ln in (sec.lines() if sec else []):
        w = parse_quiet_line(ln.text)
        if w:
            return w
    return dict(DEFAULT_QUIET)


@router.get("/presence")
def get_presence(person: str | None = Query(None), now: str | None = Query(None), gain: float = Query(DEFAULT_GAIN, gt=0),
                 cap: float = Query(DEFAULT_CAP, gt=0, lt=1)):
    mem = _mem()
    pid, pd = _resolve(person)
    if pd is None:
        return _unknown_person(pid)
    fit = _fit_presence(pd, mem)
    model: PresenceModel = fit["model"]
    now_ts = _now_for(pd, now)
    sit = _situation(pd, now_ts, fit["tz"])
    quiet = _quiet(mem)
    from .presence.survival import loss_for_cap

    thr = threshold(gain, loss_for_cap(gain, cap))
    fc = fit["returns"].forecast(sit["tow_min"], sit["idle_min"], DEFAULT_GRID_MIN)
    data = {
        "bins": model.heatmap(),
        "idle_capacity_h": dict(_idle_capacity(fit, model)),
        "idle_capacity_in_quiet_hours_h": model.idle_capacity_h(mask=window_mask(quiet)),
        "active_h_per_week": round(model.active_hours_per_week(), 1),
        "quiet_hours": quiet,
        "forecast": [{"d_min": r["d_min"], "survival": r["survival"], "lo": r["lo"], "hi": r["hi"]} for r in fc],
        "decision_threshold": round(thr, 4),
        "now": {"local": sit["local"], "dow": sit["dow"], "idle_min": round(sit["idle_min"], 1), "locked": sit["locked"], "asleep": sit["asleep"]},
        "person": pd.person,
    }
    note = ("Presence is an estimate from input times only. Idle capacity is an upper bound: it counts a locked but awake machine, and assumes "
            "the machine sleeps an hour after its last event when no sleep event was seen. "
            + "")
    return {"meta": _meta(pd.origin, len(fit["days"]), "days", "weekly map from all observed days; intervals from smoothed per-bin posteriors", note.strip()), "data": data}


@router.put("/presence/quiet_hours")
def put_quiet_hours(request: Request, body: dict[str, Any] = Body(...)):
    if (r := _guard(request)):
        return r
    try:
        w = normalise_window(body)
    except ValueError as e:
        return _error(422, "bad_quiet_hours", str(e))
    mem = _mem()
    text = quiet_line(w)

    def mutate(doc: D.MemoryDoc) -> None:
        hit = doc.find("l_quiet_hours")
        if hit:
            hit[1].text, hit[1].note = text, "set by you"
        else:
            doc.add("Preferences", text, note="set by you", line_id="l_quiet_hours")

    try:
        mem.mutate(_actor(request), mutate)
    except WriteRefused as e:
        return _error(403, "write_refused", str(e))
    return w


# ------------------------------------------------------------------------------------------------ off-hours
SCREENS = ("unlocked", "locked", "asleep")


def _decision(pd: PersonData, mem: MemoryStore, *, d_min: float, gain: float, loss: float, now_ts: float, screen: str | None,
              locked_flag: bool | None = None) -> dict[str, Any]:
    """The start-or-wait decision for one person at one time, from the real functions. ``screen`` overrides the screen state
    that would otherwise come from the person's lock, unlock, sleep and resume events."""
    thr = threshold(gain, loss)
    fit = _fit_presence(pd, mem)
    sit = _situation(pd, now_ts, fit["tz"])
    if screen is not None:
        eff, source = screen, "override"
    elif locked_flag is not None:
        eff, source = ("locked" if locked_flag else "unlocked"), "override"
    elif sit["has_screen_events"]:
        eff, source = ("asleep" if sit["asleep"] else "locked" if sit["locked"] else "unlocked"), "events"
    else:
        eff, source = "unlocked", "default"
    locked, asleep = eff == "locked", eff == "asleep"
    est = fit["returns"].survival(d_min, sit["tow_min"], sit["idle_min"])
    dec = decide(est, d_min, gain, loss, locked=locked, asleep=asleep)
    if sit["idle_raw_min"] is not None and sit["idle_raw_min"] < 5.0 and eff == "unlocked":
        from .presence.survival import Decision

        dec = Decision(False, dec.survival, dec.threshold, "You used the machine less than five minutes ago, so I do not treat you as away yet.",
                       dec.lo, dec.hi, dec.n_eff, locked)
    quiet = _quiet(mem)
    from .memory.hours import DAYS, minutes

    s0, e0 = minutes(quiet["start"]), minutes(quiet["end"])
    tod = sit["tow_min"] % 1440
    inside = (tod >= s0 or tod < e0 if s0 > e0 else s0 <= tod < e0) and DAYS[sit["dow"]] in quiet["days"]
    return {"go": dec.go, "survival": round(dec.survival, 4), "threshold": round(thr, 4), "reason": dec.reason, "locked": dec.locked,
            "lo": round(dec.lo, 4), "hi": round(dec.hi, 4), "n_eff": round(dec.n_eff, 1), "idle_min": round(sit["idle_min"], 1),
            "asleep": asleep, "screen": eff, "screen_source": source, "in_quiet_hours": bool(inside), "person": pd.person,
            "now": datetime.fromtimestamp(now_ts, timezone.utc).isoformat().replace("+00:00", "Z")}


@router.post("/offhours/decide")
def post_decide(body: dict[str, Any] = Body(...)):
    mem = _mem()
    pid, pd = _resolve(body.get("person"))
    if pd is None:
        return _unknown_person(pid)
    try:
        d_min = float(body["d_min"])
        gain = float(body.get("gain", DEFAULT_GAIN))
        loss = float(body["loss"])
        if d_min <= 0:
            raise ValueError("d_min must be positive")
        threshold(gain, loss)
    except (KeyError, TypeError, ValueError) as e:
        return _error(422, "bad_request", f"Send {{person, d_min, gain, loss}} with positive numbers: {e}")
    screen = body.get("screen")
    if screen is not None and screen not in SCREENS:
        return _error(422, "bad_screen", f"screen must be one of {', '.join(SCREENS)}.")
    try:
        now_ts = _now_for(pd, body.get("now"))
    except ValueError:
        return _error(422, "bad_now", "now must be an ISO time such as 2026-10-20T23:00:00Z.")
    return _decision(pd, mem, d_min=d_min, gain=gain, loss=loss, now_ts=now_ts, screen=screen,
                     locked_flag=body["locked"] if isinstance(body.get("locked"), bool) else None)


DEMO_PERSON = "p_nightowl"


@router.get("/offhours/demo")
def get_offhours_demo(person: str = Query(DEMO_PERSON), d_min: float = Query(45.0, gt=0), cap: float = Query(0.20, gt=0, lt=1),
                      leave: str = Query("2026-10-20T23:00:00Z"), short: str = Query("2026-10-20T13:00:00Z")):
    """A short precomputed sequence that shows the start-or-wait rule at work, without poking parameters.

    Every row is the real decision function at a stated time. Scene one: the worker leaves at ``leave`` and the rule is asked
    again as the idle time grows (screen set to unlocked, as it would be at a desk that is left on), until it says go, then the
    same moment with a locked screen. Scene two: a short break at ``short``. The screen state is an override (``screen_source``
    says so): the personas' machines go to sleep after work, so overnight their event-derived screen state is "asleep".
    """
    from .presence.survival import loss_for_cap

    mem = _mem()
    pid, pd = _resolve(person)
    if pd is None:
        return _unknown_person(pid)
    loss = loss_for_cap(DEFAULT_GAIN, cap)
    leave_ts = datetime.fromisoformat(leave.replace("Z", "+00:00")).timestamp()
    short_ts = datetime.fromisoformat(short.replace("Z", "+00:00")).timestamp()

    def row(scene: str, label: str, start_ts: float, u: float, screen: str) -> dict[str, Any]:
        d = _decision(pd, mem, d_min=d_min, gain=DEFAULT_GAIN, loss=loss, now_ts=start_ts + u * 60.0, screen=screen)
        # the situation's own idle clock would read the persona's real events; the scene sets the idle time explicitly
        fit = _fit_presence(pd, mem)
        sit = _situation(pd, start_ts + u * 60.0, fit["tz"])
        est = fit["returns"].survival(d_min, sit["tow_min"], u)
        dec = decide(est, d_min, DEFAULT_GAIN, loss, locked=screen == "locked", asleep=screen == "asleep")
        return {"scene": scene, "label": label, "time": d["now"], "idle_min": u, "d_min": d_min, "survival": round(est.survival, 4),
                "lo": round(est.lo, 4), "hi": round(est.hi, 4), "threshold": d["threshold"], "screen": screen, "screen_source": "override",
                "go": dec.go, "decision": "start" if dec.go else "wait", "reason": dec.reason}

    grid = [5, 10, 15, 20, 30, 45, 60, 90, 120, 180]
    evening = [row("evening", f"Away {int(u)} min", leave_ts, float(u), "unlocked") for u in grid]
    g = next((i for i, r in enumerate(evening) if r["go"]), None)
    picks = sorted({0, max(0, g - 2), max(0, g - 1), g}) if g is not None else [0, 2, 4, len(evening) - 1]
    rows = [evening[i] for i in picks]
    anchor = evening[g] if g is not None else evening[-1]
    rows.append(row("evening", "Same moment, screen locked", leave_ts, float(anchor["idle_min"]), "locked"))
    rows.append(row("short window", "A short break", short_ts, 5.0, "unlocked"))
    return {"person": pd.person, "d_min": d_min, "gain": DEFAULT_GAIN, "loss": round(loss, 3), "threshold": round(threshold(DEFAULT_GAIN, loss), 4),
            "cap": cap, "rows": rows,
            "note": "Each row is the real decision function at a stated time. The screen state is set by the scene (screen_source: override); "
                    "the persona's machine would otherwise be asleep overnight. Start only when the chance the window lasts "
                    f"{int(d_min)} minutes beats L/(G+L) = {threshold(DEFAULT_GAIN, loss):.0%}."}


_RAN_KINDS = ("run_end", "run_done", "run_complete", "run_finished", "run")
_FAIL = ("failed", "error", "stopped", "refused", "aborted")


@router.get("/offhours/report")
def get_offhours_report(since: str | None = Query(None)):
    """Morning report from the audit log and the approval queue. Tolerant of the agent's exact line shapes."""
    t0 = datetime.fromisoformat(since.replace("Z", "+00:00")) if since else datetime.fromtimestamp(0, timezone.utc)
    lines: list[dict[str, Any]] = []
    ap = data_dir() / "audit.jsonl"
    if ap.exists():
        for raw in ap.read_text().splitlines():
            try:
                row = json.loads(raw)
                if datetime.fromisoformat(str(row["t"]).replace("Z", "+00:00")) >= t0:
                    lines.append(row)
            except (json.JSONDecodeError, KeyError, ValueError):
                continue
    runs: dict[str, list[dict[str, Any]]] = {}
    for row in lines:
        if row.get("run_id"):
            runs.setdefault(str(row["run_id"]), []).append(row)
    ran, failed, yielded = [], [], []
    for rid, rows in runs.items():
        rows.sort(key=lambda r: r["t"])
        routine = next((r["routine"] for r in rows if r.get("routine")), None)
        kinds = {str(r.get("kind", "")) for r in rows}
        outcome = str(rows[-1].get("outcome") or "")
        if any("yield" in k for k in kinds) or outcome == "yielded":
            yielded.append({"routine": routine, "at": next((r["t"] for r in rows if "yield" in str(r.get("kind")) or r.get("outcome") == "yielded"), rows[-1]["t"])})
            continue
        if outcome in _FAIL:
            failed.append({"routine": routine, "reason": str(rows[-1].get("note") or outcome)})
            continue
        if kinds & set(_RAN_KINDS) or outcome in ("ok", "done", "success", "completed"):
            a = datetime.fromisoformat(str(rows[0]["t"]).replace("Z", "+00:00"))
            b = datetime.fromisoformat(str(rows[-1]["t"]).replace("Z", "+00:00"))
            tiers = [int(r["tier"]) for r in rows if isinstance(r.get("tier"), int)]
            ran.append({"routine": routine, "run_id": rid, "outcome": outcome or "ok", "minutes": round((b - a).total_seconds() / 60.0, 1),
                        "tier": max(tiers) if tiers else None})
    queued: list[str] = []
    qd = data_dir() / "queue"
    if qd.exists():
        for f in sorted(qd.glob("*.json")):
            try:
                q = json.loads(f.read_text())
                if q.get("status") == "pending" and datetime.fromisoformat(str(q["created_at"]).replace("Z", "+00:00")) >= t0:
                    queued.append(q["id"])
            except (json.JSONDecodeError, KeyError, ValueError, OSError):
                continue
    return {"since": since, "ran": ran, "queued": queued, "failed": failed, "yielded": yielded}


# ------------------------------------------------------------------------------------------------ eval sections
def handoff_sections(*, root: Path | None = None, fast: bool = False) -> dict[str, Any]:
    """Section dicts for evals/report.json: presence, ski_rental, routines, plus this track's limitations. Heavy (seconds)."""
    from .presence.personas import evaluate_presence_all, report_section as presence_section
    from .routines.evaluate import evaluate_finder, evaluate_forecast, evaluate_ski_rental, routines_report

    pres = evaluate_presence_all(root, fast=fast)
    fin = evaluate_finder(root, fast=fast)
    ski = evaluate_ski_rental(fast=fast)
    fc = evaluate_forecast(root, fast=fast)
    limits = [*pres.get("limitations", []), *fin.get("limitations", []), *ski.get("limitations", []), *fc.get("limitations", [])]
    return {
        "presence": {**presence_section(pres), "detail": pres},
        "ski_rental": {"rows": ski["rows"], "hindsight_regret": 1.0, "hindsight": 1, "sweep": ski["sweep"], "meta": ski["meta"], "detail": ski},
        "routines": {**routines_report(fin), "detail": fin},
        "forecast": fc,
        "limitations": limits,
    }
