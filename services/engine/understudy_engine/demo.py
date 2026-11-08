"""A coherent demo state for the three-minute demo: ``python -m understudy_engine.demo seed [--reset]``.

Seeds ONE isolated state home so the demo runs with no manual steps. It only ever touches the directory named by
``UNDERSTUDY_HOME`` (``make demo`` points it at ``data/demo-home``); with the variable unset it refuses, so it can never
write the owner's real ``~/.understudy``. Everything goes through the same code the API uses, as the worker:

* onboarding for the benefits-processor role with desk capture on (the ``Capture: times only`` line), person ``p_learn01``;
* the Skill state line for ``enter-household-once`` at L4 (the routine's cogs), so the calculator-entry routine is eligible
  for consent without an override;
* the ``calc-entry-3x`` routine detected by the real finder and listed as proposed: rung A0, nothing consented, plus a second,
  smaller one (``case-note-copy``) so the Routines list and the Repeats list each show two rows. The finder reads the nine-to-five
  persona's traces for them (the learner trajectories are one task type and hold no calculator-entry routine);
* ``p_learn01`` at learner case 24 (coach level and chip from the analytics track's SkillTracker). Case 24, not 20: that is
  the first case range where the learner's own ENTER_HOUSEHOLD level is L4, so the skill gate agrees with the memory file;
* three consistent corrections already recorded, so one rule proposal is waiting for the worker's approval.

The shared data directory is isolated too. ``make demo`` must set::

    UNDERSTUDY_HOME=$(CURDIR)/data/demo-home
    UNDERSTUDY_DATA_DIR=$(CURDIR)/data/demo-data
    UNDERSTUDY_MOCK=1

``data/demo-data`` holds read-only symlinks to ``../synthetic``, ``../golden``, ``../voice_cache`` and ``../eval`` and its own
fresh ``queue/``, ``runs/``, ``routines/`` and ``audit.jsonl``, seeded with a morning story built through the agent's public
classes: two pending approvals from last night's background run (an irreversible "Submit case note" with evidence and a shadow
mismatch), a few audit lines, one earlier run folder with four screenshots, and one run that yielded when the worker came back.
It also fills the assist ledger (``<data>/assist/ledger.jsonl``) with ONE simulated improving learner for ``p_learn01``, every row labelled
``origin: synthetic`` and ``origin_detail: synthetic_learner``, so the Growth screen has a curve to show (a fresh person sees "Your curve starts
after 10 steps"); ``--reset`` removes it with the rest, and a marker keeps a second run from adding it twice.
The seed then calls ``understudy_agent.demo_bundle.install()`` (skipped with a note if absent) so the compiled bundle
``routines/calc-entry-3x/steps.json`` exists. A data directory that is not the demo one (named ``demo-data`` or carrying the
demo marker) is never written: the seed says so and skips that part.

``--reset`` wipes only what this seed made (in the home: only if it carries the demo marker or is empty; in the data directory:
queue, runs, routines, assist ledger, audit log and kill flag of the demo directory). Re-running without ``--reset`` changes nothing.
"""
from __future__ import annotations

import argparse
import os
import shutil
import struct
import sys
import zlib
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .memory import MemoryStore, RuleEngine, load_pack, onboard
from .memory import doc as D
from .memory.paths import data_dir, home_dir
from .memory.shadow import ExpertPolicy

DEMO_PERSON = "p_learn01"
DEMO_CASE = 24
DEMO_ROLE = "benefits-processor"
DEMO_ROUTINE = "calc-entry-3x"
#: the routines the demo person owns: the story's routine first, then a smaller one that needs no skill gate (both borrow the nine-to-five traces)
DEMO_ROUTINES = (DEMO_ROUTINE, "case-note-copy")
ROUTINE_SOURCE = "p_ninetofive"
MARKER = ".understudy-demo-home"
DATA_MARKER = ".understudy-demo-data"
STORY_MARKER = ".demo-story"
GROWTH_MARKER = ".demo-growth"
#: the assist ledger the Growth screen reads (``<data>/assist/ledger.jsonl``): the demo seed fills it with ONE simulated learner (labelled)
GROWTH_DIR = "assist"
GROWTH_SEED = 21            # the same fixed seed ``cue.make_examples`` uses for the dashboard's example learner
GROWTH_PER_SKILL = 30       # 3 skills x 30 = 90 occurrences: past the 10 the screen needs and the 30 its trend needs
GROWTH_LAG_HOURS = 2.0      # the last occurrence is this long before the seed's clock, so the curve is current
STATE_FILES = ("memory.md", "memory_state.json", "routines_state.json", ".memory.lock")
LINKS = ("synthetic", "golden", "voice_cache", "eval")
EARLIER_RUNS = ("r_demo_0001", "r_demo_0002")


class DemoError(RuntimeError):
    pass


def is_demo_data_dir(p: Path) -> bool:
    """Only a directory called demo-data, or one carrying the demo marker, may be written."""
    return p.name == "demo-data" or (p / DATA_MARKER).exists()


def reset_home(home: Path, out: Callable[[str], None]) -> None:
    if (home / "memory.md").exists() and not (home / MARKER).exists():
        raise DemoError(f"{home} holds a memory file the demo did not create, so I will not reset it. Point UNDERSTUDY_HOME at an empty or demo home.")
    removed = []
    for name in STATE_FILES:
        f = home / name
        if f.exists():
            f.unlink()
            removed.append(name)
    out(f"reset home: removed {', '.join(removed) if removed else 'nothing (already empty)'}")


def reset_data(dd: Path, out: Callable[[str], None]) -> None:
    """Empty the demo data directory's own folders. Symlinks to the shared data are unlinked, never followed."""
    removed = []
    for name in ("queue", "runs", "routines", GROWTH_DIR, "firm"):
        d = dd / name
        if d.is_symlink():
            d.unlink()
        elif d.exists():
            shutil.rmtree(d)
        else:
            continue
        removed.append(name + "/")
    for name in ("audit.jsonl", "KILL", STORY_MARKER, GROWTH_MARKER):
        f = dd / name
        if f.exists() or f.is_symlink():
            f.unlink()
            removed.append(name)
    out(f"reset data: removed {', '.join(removed) if removed else 'nothing (already empty)'}")


def prepare_data_dir(dd: Path, out: Callable[[str], None]) -> list[str]:
    """Create the demo data directory: marker, relative symlinks to the shared folders that exist, empty working folders."""
    dd.mkdir(parents=True, exist_ok=True)
    (dd / DATA_MARKER).write_text("created by understudy_engine.demo seed; holds demo data only\n")
    linked = []
    for name in LINKS:
        target = dd.parent / name
        link = dd / name
        if not target.exists():
            continue
        if link.is_symlink() or link.exists():
            if link.is_symlink() and os.readlink(link) == f"../{name}":
                linked.append(name)
                continue
            if link.is_symlink():
                link.unlink()
            else:
                continue  # a real folder someone put there: leave it alone
        link.symlink_to(f"../{name}")
        linked.append(name)
    for sub in ("queue", "runs", "routines"):
        (dd / sub).mkdir(exist_ok=True)
    (dd / "audit.jsonl").touch(exist_ok=True)
    out(f"data dir: {dd} (demo data dir); linked {', '.join(linked) or 'nothing'} from {dd.parent}")
    return linked


def placeholder_png(width: int, height: int, rgb: tuple[int, int, int], label_bar: tuple[int, int, int] | None = None) -> bytes:
    """A small valid PNG (solid colour with a darker top bar) for a screenshot stand-in. No imaging library needed."""
    rows = []
    for y in range(height):
        c = label_bar if (label_bar and y < height // 9) else rgb
        rows.append(b"\x00" + bytes(c) * width)

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress(b"".join(rows), 6)) + chunk(b"IEND", b""))


def seed_story(dd: Path, now: datetime, out: Callable[[str], None]) -> dict[str, Any]:
    """Last night's background run, as the morning queue and report show it. Built only through the agent's public classes."""
    try:
        from understudy_agent.audit import AuditLog
        from understudy_agent.queue import ApprovalQueue, save_screenshot
    except ImportError as e:
        out(f"morning story skipped: the agent package is not importable ({e})")
        return {"story": False}
    if os.environ.get("UNDERSTUDY_DATA_DIR") and Path(os.environ["UNDERSTUDY_DATA_DIR"]).expanduser().resolve() != dd.resolve():
        raise DemoError("UNDERSTUDY_DATA_DIR changed while seeding; refusing to write the story.")
    clock = {"t": now - timedelta(hours=8)}
    audit = AuditLog(dd / "audit.jsonl", clock=lambda: clock["t"], fsync=False)
    queue = ApprovalQueue(dd / "queue", audit=audit, clock=lambda: clock["t"].timestamp())
    gold = dd / "golden" / "screenshots"
    shots = []
    for i in range(1, 5):
        src = gold / f"s{i}.png"
        png = src.read_bytes() if src.exists() else placeholder_png(640, 360, (236 - 18 * i, 240 - 14 * i, 246 - 10 * i), (60, 80, 110))
        shots.append(save_screenshot(EARLIER_RUNS[0], i, png))
    base = clock["t"]

    def at(minutes: float) -> None:
        clock["t"] = base + timedelta(minutes=minutes)

    r1, r2, routine = EARLIER_RUNS[0], EARLIER_RUNS[1], "benefits-workflow"
    at(0)
    audit.append("agent", "run_start", routine=routine, run_id=r1, tier=1, outcome="started", note_code="household:hh_0004")
    at(1)
    audit.append("agent", "step", routine=routine, run_id=r1, tier=1, outcome="ok", note_code="step:enter_household")
    at(4)
    audit.append("agent", "tier_escalation", routine=routine, run_id=r1, tier=2, outcome="ok", note_code="precondition:calculator_layout")
    at(8)
    audit.append("agent", "gate", routine=routine, run_id=r1, tier=1, outcome="pending", note_code="gate:irreversible:submit")
    submit = queue.enqueue(
        kind="irreversible_step", title="Submit case note CN-2041", summary="The three calculators agree. The note is written and waiting for your click.",
        risk_class="irreversible", routine_id=None, run_id=r1,
        evidence={"screenshots": shots[2:4], "extracted": {"case_ref": "CN-2041", "calculators_agree": True, "note_fields": 6},
                  "expected": {"case_ref": "CN-2041", "calculators_agree": True}, "diff": [],
                  "tier_log": [{"step": 1, "tier": 1}, {"step": 3, "tier": 2}, {"step": 5, "tier": 1}]},
        signature="submit_case_note:CN-2041")
    at(9)
    mismatch = queue.enqueue(
        kind="shadow_mismatch", title="Shadow run differed from yours", summary="Calculator B gave 214 where your entry gave 241. Nothing was saved.",
        risk_class="normal", routine_id="result-to-note", run_id=r1,
        evidence={"screenshots": shots[1:2], "extracted": {"calculator_b_total": 214}, "expected": {"calculator_b_total": 241},
                  "diff": [{"field": "calculator_b_total", "expected": 241, "got": 214}], "tier_log": [{"step": 2, "tier": 1}]})
    at(11)
    audit.append("system", "completion_check", routine=routine, run_id=r1, outcome="ok", note_code="goal_tokens:all_present")
    at(12)
    audit.append("agent", "run_end", routine=routine, run_id=r1, tier=2, outcome="ok", note_code="stopped_before_submit")
    at(180)
    audit.append("agent", "run_start", routine=routine, run_id=r2, tier=1, outcome="started", note_code="household:hh_0007")
    at(182)
    audit.append("agent", "yield", routine=routine, run_id=r2, tier=1, outcome="yielded", note_code="human_input")
    (dd / STORY_MARKER).write_text(now.isoformat() + "\n")
    out(f"morning story: 2 pending approvals ({submit['kind']}, {mismatch['kind']}), {len(audit.read(limit=0))} audit lines, "
        f"earlier run {r1} with {len(shots)} screenshots, run {r2} that yielded when the worker came back")
    return {"story": True, "queue": [submit["id"], mismatch["id"]], "audit_lines": len(audit.read(limit=0)), "run": r1, "screenshots": shots}


def demo_learner_rows(now: datetime) -> list[dict[str, Any]]:
    """The Growth screen's data for the demo person: one SIMULATED improving learner (``cue.simlearn``, fixed seed) shifted in time so its last
    occurrence is ``GROWTH_LAG_HOURS`` before ``now``, plus four offloaded rows (work the agent did, listed and never scored). Every row is
    labelled ``origin: synthetic`` and ``origin_detail: synthetic_learner``, so the screen's origin badge says "example data". Pure and
    deterministic for a given ``now``; it writes nothing."""
    import numpy as np

    from .cue import ledger as L
    from .cue import simlearn as SL

    spec = SL.preset("improving")
    _rows, truth = SL.simulate_learner(spec, np.random.default_rng(GROWTH_SEED), person=DEMO_PERSON, n_per_skill=GROWTH_PER_SKILL)
    t0 = 1_790_000_000.0                       # simulate_learner's own default start
    span = float(truth.t[-1]) - t0
    end = now.timestamp() - GROWTH_LAG_HOURS * 3600.0
    rows, _ = SL.simulate_learner(spec, np.random.default_rng(GROWTH_SEED), person=DEMO_PERSON, n_per_skill=GROWTH_PER_SKILL, t0=end - span)
    offloaded = [L.make_row(person=DEMO_PERSON, role=DEMO_ROLE, skill="enter-household-once", t=end - 3600.0 * (i + 1) * 5, outcome="clean",
                            stream="automation" if i % 2 else "delegated", routine=DEMO_ROUTINE, minutes=12.0 + i, offload_outcome="done",
                            origin="synthetic", origin_detail="synthetic_learner", serial=900 + i) for i in range(4)]
    return rows + offloaded


def seed_growth(dd: Path, now: datetime, out: Callable[[str], None]) -> dict[str, Any]:
    """Fill the assist ledger of the demo data directory so the Growth screen shows a curve and the Home insights have an independence
    story (the dashboard's "Your curve starts after 10 steps" empty state is what a fresh person sees). Only ever writes into the demo data
    directory, only once (a marker), and every row is a schema-validated, labelled simulated-learner row."""
    from .cue import ledger as L

    rows = demo_learner_rows(now)
    ledger = L.Ledger(dd / GROWTH_DIR / "ledger.jsonl")
    n = ledger.extend(rows)
    (dd / GROWTH_MARKER).write_text(now.isoformat() + "\n")
    counts = {s: sum(1 for r in rows if r["stream"] == s) for s in ("assist", "delegated", "automation")}
    out(f"growth: {counts['assist']} assist occurrences for {DEMO_PERSON} from one SIMULATED improving learner (labelled synthetic_learner), "
        f"{counts['delegated'] + counts['automation']} offloaded rows (listed, never scored); {n} rows in {GROWTH_DIR}/ledger.jsonl")
    return {"growth": True, "growth_rows": n, "growth_counts": counts}


def seed_firm(dd: Path, now: datetime, out: Callable[[str], None], *, refresh: bool = False) -> dict[str, Any]:
    """Write the firm the Admin screens show into ``<dd>/firm/``: 32 people in three roles and three teams, twelve weeks of history ending at ``now``, their routines, open
    approvals and risk events (``insights.firm.demo_firm``, then ``insights.firmstore.write_firm``). Only the demo data directory is written. Idempotent: a firm that is already
    there, of this plan, version and seed, and that reads back clean, is left exactly as it is (``refresh=True`` writes it again with its history ending at ``now``). It is a top-up:
    it touches nothing but ``<dd>/firm/`` (not the queue, the runs, the routines, the audit log, the worker's own ledger or the home)."""
    from .insights import firm as F
    from .insights import firmstore as FS

    if not is_demo_data_dir(dd):
        out(f"firm: {dd} is not a demo data dir; not written.")
        return {"firm": False}
    have = FS.describe(dd)
    same = bool(have) and have.get("plan") == F.DEMO32.name and have.get("version") == FS.VERSION and have.get("seed") == F.DEMO_SEED
    if same and not refresh and FS.load_firm(dd) is not None:
        out(f"firm: already seeded ({have['people']} people, {have['rows']} ledger rows, {len(have['units'])} teams); nothing changed. (--refresh moves its history to end now.)")
        return {"firm": True, "firm_people": have["people"], "firm_written": False}
    snap = F.demo_firm(now.timestamp()).snapshot
    res = FS.write_firm(dd, snap, plan=F.DEMO32.name, seed=F.DEMO_SEED)
    got = FS.describe(dd) or {}
    out(f"firm: {res['people']} people ({', '.join(f'{n} {r}' for r, n in sorted(got.get('roles', {}).items()))}) in {len(got.get('units', []))} teams, {res['rows']} ledger rows over 12 weeks, "
        f"{len(snap.routines)} routines, {len(snap.approvals)} open approvals; written to {res['path']}")
    return {"firm": True, "firm_people": res["people"], "firm_rows": res["rows"], "firm_written": True}


def install_demo_bundle(dd: Path, out: Callable[[str], None]) -> str | None:
    """Agent-core's compiled bundle for calc-entry-3x. Lazy: skipped with a note when their module is absent."""
    try:
        from understudy_agent import demo_bundle
    except ImportError:
        out("demo bundle skipped: understudy_agent.demo_bundle is not available yet (steps.json not installed)")
        return None
    try:
        res = demo_bundle.install()
    except Exception as e:  # their installer failing must not undo the rest of the seed
        out(f"demo bundle FAILED: {type(e).__name__}: {str(e)[:160]}")
        return None
    steps = dd / "routines" / DEMO_ROUTINE / "steps.json"
    out(f"demo bundle installed: {steps} {'exists' if steps.exists() else 'is MISSING'}" + (f" ({res})" if isinstance(res, (str, int)) else ""))
    return str(steps) if steps.exists() else None


def seed(*, reset: bool = False, now: datetime | None = None, out: Callable[[str], None] = print, bundle: bool = True) -> dict[str, Any]:
    if not os.environ.get("UNDERSTUDY_HOME"):
        raise DemoError("UNDERSTUDY_HOME is not set. I will not touch the default ~/.understudy; set UNDERSTUDY_HOME (make demo uses data/demo-home).")
    home = home_dir()
    dd = data_dir().resolve()
    demo_data = is_demo_data_dir(dd)
    if demo_data:
        prepare_data_dir(dd, lambda m: None)
    for slug in ("learners", "nine-to-five"):
        if not (dd / "synthetic" / slug / "events.jsonl").exists():
            raise DemoError(f"synthetic data is missing ({slug}). Run `uv run understudy synth --all` first.")
    home.mkdir(parents=True, exist_ok=True)
    out(f"state home: {home}")
    if reset:
        reset_home(home, out)
    store = MemoryStore(home)
    if (home / "memory.md").exists() and not (home / MARKER).exists():
        raise DemoError(f"{home} already holds a memory file that is not a demo seed. Use an empty directory (or a demo home with --reset).")
    if demo_data:
        if reset:
            reset_data(dd, out)
        prepare_data_dir(dd, out)
    else:
        out(f"data dir {dd} is not a demo data dir (call it demo-data, e.g. UNDERSTUDY_DATA_DIR=data/demo-data): I will not write the morning "
            "queue, audit log or routine bundle there.")
    result = _seed_home(store, home, reset, now, out)
    if demo_data:
        t = now or datetime.now(timezone.utc)
        if (dd / STORY_MARKER).exists():
            out("morning story: already seeded; nothing changed.")
        else:
            result.update(seed_story(dd, t, out))
        if (dd / GROWTH_MARKER).exists():
            out("growth: already seeded; nothing changed.")
        else:
            try:
                result.update(seed_growth(dd, t, out))
            except Exception as e:  # the base demo does not depend on it: say what failed, keep going
                out(f"growth: NOT SEEDED, the Growth screen will show its empty state ({type(e).__name__}: {str(e)[:160]})")
                result["growth"] = False
        try:
            result.update(seed_firm(dd, t, out))
        except Exception as e:  # the base demo does not depend on it: say what failed, keep going
            out(f"firm: NOT SEEDED, the Admin screens will show their empty state ({type(e).__name__}: {str(e)[:160]})")
            result["firm"] = False
        if bundle:
            result["bundle"] = install_demo_bundle(dd, out)
        else:
            result["bundle"] = None
            out("demo bundle: not requested (--no-bundle); steps.json not installed")
        result["briefing"] = _seed_briefing(home, dd, now, out, force=reset)
        out("done. Start the engine and the agent with the same UNDERSTUDY_HOME, UNDERSTUDY_DATA_DIR and UNDERSTUDY_MOCK=1 to run the demo.")
    elif result.get("seeded"):
        out("done (home only). Start the engine with this UNDERSTUDY_HOME to run the demo.")
    return result


def _seed_briefing(home: Path, dd: Path, now: datetime | None, out: Callable[[str], None], *, force: bool = False) -> dict[str, Any] | None:
    """The proactive briefing's three cards for the demo person (extension layer PRO). Only when that layer is switched on
    (UNDERSTUDY_X_PROACTIVE or UNDERSTUDY_X); idempotent; seeded again (``reseed=True``) when the extension flags changed since the
    last seed or the demo was reset. The flags last seen live in the demo state file (``demo.extension_flags``), so no new file
    appears and ``--reset`` forgets them with the rest. Never raises: the base demo does not depend on it."""
    from .api.flags import extension_flags

    flags = sorted(k for k, v in extension_flags().items() if v)
    ms = MemoryStore(home)

    def remember() -> None:
        try:
            st = ms.load_state()
            st.setdefault("demo", {})["extension_flags"] = flags
            ms.save_state(st, actor="worker")
        except Exception:                                  # a state file we cannot write is not a reason to fail the demo
            pass

    prev = ((ms.load_state().get("demo") or {}).get("extension_flags")) if ms.state_path.exists() else None
    if "proactive" not in flags:
        out("briefing: the proactive layer is off (UNDERSTUDY_X_PROACTIVE=1 or UNDERSTUDY_X=1 turns it on): not seeded.")
        remember()
        return None
    try:
        from .proactive.seed import seed_demo
    except ImportError as exc:
        out(f"briefing: skipped ({exc}).")
        return None
    reseed = force or (prev is not None and prev != flags)
    try:
        res = seed_demo(home, dd, now=now, reseed=reseed)
    except Exception as exc:  # the demo's base story must not fail because the extension could not seed
        out(f"briefing: not seeded ({type(exc).__name__}: {exc}).")
        return {"seeded": False, "error": f"{type(exc).__name__}: {exc}"}
    remember()
    out(f"briefing: {'seeded' if res.get('seeded') else 'already there'} ({len(res.get('cards', []))} cards{', reseeded' if reseed else ''}).")
    return res


def _seed_home(store: MemoryStore, home: Path, reset: bool, now: datetime | None, out: Callable[[str], None]) -> dict[str, Any]:
    st = store.load_state()
    if (st.get("demo") or {}).get("seeded"):
        out(f"already seeded (memory revision {store.revision()}); nothing changed in the home. Use --reset to start over.")
        return {"seeded": False, "revision": store.revision(), "person": (st.get("profile") or {}).get("person")}
    t = now or datetime.now(timezone.utc)
    (home / MARKER).write_text("created by understudy_engine.demo seed; safe to reset\n")

    # 1. onboarding, as the worker, with capture on
    res = onboard(store, DEMO_ROLE, {"capture": True}, person=DEMO_PERSON, now=t)
    out(f"onboarding: role {res['role']}, person {res['person']}, memory revision {res['revision']}, capture {'on' if res['capture'] else 'off'}")

    # 2. skill state at L4 for the routine's cogs
    pack = load_pack(DEMO_ROLE)
    tmpl = pack.template(DEMO_ROUTINE)
    cogs = set((tmpl or {}).get("cogs", [])) | set((tmpl or {}).get("skill_cogs", []))
    levelled = []
    doc = store.read()
    sec = doc.section("Skill state", create=False)
    skills = {str(s["id"]): s for s in pack.skills}
    for ln in (sec.lines() if sec else []):
        p = D.parse_skill_line(ln.text)
        if p and set(skills.get(p["skill"], {}).get("cogs", [])) & cogs:
            store.update_line(ln.id, actor="worker", text=f"{p['skill']}: L4, streak 3, last seen {t.date().isoformat()}", note="demo seed")
            levelled.append(p["skill"])
    out(f"skill state: L4 on {', '.join(levelled) or 'nothing'} (the routine's cogs: {', '.join(sorted(cogs))})")

    # 3. three consistent corrections: one pending rule proposal
    rules = RuleEngine(store, policy=ExpertPolicy.from_pack(pack))
    prop = None
    for k, ago in enumerate((timedelta(days=2), timedelta(days=1), timedelta(hours=3))):
        r = rules.record_correction("summary_length", "detailed", actor="worker", ceiling="A2", now=t - ago)
        prop = r["proposal"] or prop
    out(f"rule proposal waiting for approval: {prop['id']} ({prop['rule']!r}, {prop['evidence_count']} corrections, ceiling {prop['ceiling']})" if prop else "no proposal was raised")

    # 4. demo configuration (read by coach/state, routines and graph/work) and the routine through the real finder
    s2 = store.load_state()
    s2["demo"] = {"seeded": True, "person": DEMO_PERSON, "case": DEMO_CASE, "routine_source": ROUTINE_SOURCE,
                  "routine_ids": list(DEMO_ROUTINES), "seeded_at": t.replace(microsecond=0).isoformat()}
    store.save_state(s2, actor="worker")
    from . import routes_handoff as rh

    pd = rh._src().load(DEMO_PERSON)
    if pd is None:
        raise DemoError(f"no events for {DEMO_PERSON}; run `uv run understudy synth --all`.")
    rstore = rh._sync_routines(pd, rh._mem())
    routine = next((r for r in rstore.list() if r["id"] == DEMO_ROUTINE), None)
    if routine is None:
        raise DemoError(f"the finder did not produce {DEMO_ROUTINE}; check the nine-to-five persona data and the pack template.")
    coach = rh.coach_state(person=None, step=None, case=None)
    out(f"routine: {routine['id']} status {routine['status']}, rung {routine['rung']}, consent {routine['consent']['mode']}, "
        f"gate eligible {routine['skill_gate']['eligible']} ({routine['skill_gate']['reason']}), about {routine['value']['hours_saved'][0]} to "
        f"{routine['value']['hours_saved'][1]} hours over {routine['value']['horizon_weeks']} weeks")
    out(f"coach: {DEMO_PERSON} at case {coach.get('case')} of {coach.get('cases_total')}: level {coach['level']}, chip {coach['chip']}")
    problems = []
    listed = {r["id"] for r in rstore.list() if r["id"] in DEMO_ROUTINES}
    if listed != set(DEMO_ROUTINES):
        problems.append(f"the finder did not produce {', '.join(sorted(set(DEMO_ROUTINES) - listed))}")
    if routine["status"] != "proposed" or routine["rung"] != "A0" or routine["consent"]["mode"] != "none":
        problems.append("the routine is not in its proposed, unconsented state")
    if not routine["skill_gate"]["eligible"]:
        problems.append("the routine is not eligible without an override")
    if not prop:
        problems.append("no rule proposal")
    if problems:
        raise DemoError("seeded, but the state is not what the demo needs: " + "; ".join(problems))
    return {"seeded": True, "revision": store.revision(), "person": DEMO_PERSON, "routine": routine["id"], "proposal": prop["id"],
            "coach": {"level": coach["level"], "chip": coach["chip"], "case": coach.get("case")}}


def status(out: Callable[[str], None] = print) -> int:
    home = home_dir()
    store = MemoryStore(home)
    st = store.load_state()
    d = st.get("demo") or {}
    out(f"state home: {home} (UNDERSTUDY_HOME {'set' if os.environ.get('UNDERSTUDY_HOME') else 'NOT set: this is the default home'})")
    out(f"memory revision {store.revision()}, demo seeded: {bool(d.get('seeded'))}, person {(st.get('profile') or {}).get('person')}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m understudy_engine.demo", description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("seed", help="populate the isolated demo state home named by UNDERSTUDY_HOME")
    sp.add_argument("--reset", action="store_true", help="wipe the demo files in the home and the demo data dir first")
    sp.add_argument("--no-bundle", action="store_true", help="do not call understudy_agent.demo_bundle.install() (tests, or no browsers installed)")
    sub.add_parser("status", help="show what the home holds")
    sf = sub.add_parser("seed-firm", help="top up the data dir named by UNDERSTUDY_DATA_DIR with the firm the Admin screens show (writes only <data>/firm/; safe on a running stack; no --reset)")
    sf.add_argument("--refresh", action="store_true", help="write the firm again with its twelve weeks of history ending now (same people)")
    sub.add_parser("seed-growth", help="top up the data dir with the worker's own learning curve (writes only <data>/assist/ and one marker, once)")
    args = ap.parse_args(argv)
    try:
        if args.cmd == "status":
            return status()
        if args.cmd in ("seed-firm", "seed-growth"):
            dd = data_dir().resolve()
            if not is_demo_data_dir(dd):
                raise DemoError(f"{dd} is not a demo data dir (name it demo-data or give it the {DATA_MARKER} marker); I will not write there.")
            t = datetime.now(timezone.utc)
            if args.cmd == "seed-firm":
                seed_firm(dd, t, print, refresh=args.refresh)
            elif (dd / GROWTH_MARKER).exists():
                print("growth: already seeded; nothing changed.")
            else:
                seed_growth(dd, t, print)
            return 0
        seed(reset=args.reset, bundle=not args.no_bundle)
        return 0
    except DemoError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    from .api.flags import apply_default_flags

    apply_default_flags()   # D48: as a script the seed runs with the layers on (so it fills the briefing too); an explicit UNDERSTUDY_X=0 turns them off
    raise SystemExit(main())
