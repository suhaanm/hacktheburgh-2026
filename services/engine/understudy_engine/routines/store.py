"""Routine registry: the worker's decisions about each routine, shadow statistics, the autonomy rung, and consent.

Measured fields (episodes, value, forecast...) come from detection and are replaced each run. **Owned** fields are the
worker's: status, consent, rung, shadow statistics, decline times. Detection never touches them.

Rules enforced here, in code:

* Consent modes: ``not_now``, ``never``, ``shadow``, ``approval``, ``unattended`` (HND-2). ``not_now`` and ``never`` always
  succeed (and revoke); the others need the skill gate to pass or an explicit ``skill_override`` by the worker.
* ``irreversible_unattended`` lists the irreversible classes the worker lets run while they are away. It only applies to
  ``unattended`` mode and must be classes the routine actually has. A **model-driven** routine needs ``typed_confirm`` equal
  to the routine id (typed by the worker); a **compiled** routine needs only the one tap (D11, SEC-4). Otherwise 422.
* The rung is earned, never granted by consent: ``A1`` once shadow is on, ``A2`` after at least 20 shadow runs with a Wilson
  lower bound of at least 0.8, ``A3`` at 0.95 (about 73 clean runs). It is capped by consent (shadow A1, approval A2,
  unattended A3). A failure, an undo or an injection hit demotes one rung and restarts the shadow count.
* The memory file is read back: deleting the routine's line in Routines, or editing it to something tighter, tightens
  behaviour at once. Editing it looser has no effect: loosening goes through the API with its confirmations.
"""
from __future__ import annotations

import json
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from ..memory import doc as D
from ..memory.paths import data_dir
from ..memory.shadow import wilson_lower
from ..memory.store import MemoryStore, atomic_write, now_iso
from .finder import edit_distance

MODES = ("not_now", "never", "shadow", "approval", "unattended")
MODE_RANK = {"none": 0, "not_now": 0, "never": 0, "shadow": 1, "approval": 2, "unattended": 3}
RUNGS = ("A0", "A1", "A2", "A3")
CEILING = {"none": "A0", "not_now": "A0", "never": "A0", "shadow": "A1", "approval": "A2", "unattended": "A3"}
PROMOTE_A2 = (20, 0.80)
PROMOTE_A3 = (60, 0.95)
STATUS_OF = {"not_now": "declined", "never": "never", "shadow": "shadow", "approval": "approval", "unattended": "unattended"}
OWNED = ("status", "consent", "rung", "shadow", "declined_not_now_at", "skill_override", "decided_at", "blocked")
_LINE = re.compile(r"^(?P<id>\S+)\s*\|\s*rung (?P<rung>A[0-3])\s*\|\s*consent:\s*(?P<mode>\w+)(?:.*?\|\s*unattended:\s*(?P<un>.*))?$")


class ConsentError(ValueError):
    def __init__(self, code: str, message: str, status: int = 422) -> None:
        super().__init__(message)
        self.code, self.status = code, status


def _lid(routine_id: str) -> str:
    import hashlib

    return "rt_" + hashlib.sha1(routine_id.encode()).hexdigest()[:8]


def routines_dir() -> Path:
    return data_dir() / "routines"


def line_text(r: dict[str, Any]) -> str:
    c = r["consent"]
    un = c["irreversible_unattended"]
    unat = f"unattended: allowed [{', '.join(un)}]" if c["mode"] == "unattended" and un else "unattended: " + ("allowed [none]" if c["mode"] == "unattended" else "not allowed")
    return f"{r['id']} | rung {r['rung']} | consent: {c['mode']} | {unat}"


def parse_line(text: str) -> dict[str, Any] | None:
    m = _LINE.match(text.strip())
    if not m:
        return None
    un = m.group("un") or ""
    classes = re.findall(r"\[(.*?)\]", un)
    allowed = [x.strip() for x in classes[0].split(",") if x.strip() and x.strip() != "none"] if classes else []
    return {"id": m.group("id"), "rung": m.group("rung"), "mode": m.group("mode"), "unattended_classes": allowed,
            "unattended": "allowed" in un}


class RoutineStore:
    def __init__(self, memory: MemoryStore, *, bundle_root: Path | None = None) -> None:
        self.memory = memory
        self.path = memory.home / "routines_state.json"
        self.bundle_root = bundle_root or routines_dir()

    # ----- persistence -----
    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"routines": {}, "labels": []}
        try:
            return json.loads(self.path.read_text())
        except (json.JSONDecodeError, OSError):
            return {"routines": {}, "labels": []}

    def _save(self, st: dict[str, Any]) -> None:
        atomic_write(self.path, json.dumps(st, indent=1, sort_keys=True))

    # ----- merge detection output -----
    def merge(self, detected: Iterable[dict[str, Any]]) -> list[str]:
        st = self._load()
        known = st["routines"]
        earlier = set(known)          # only routines from before this run can be the same routine seen again
        ids: list[str] = []
        for d in detected:
            rid = d["id"]
            if rid not in known and d.get("template_id") is None:
                for oid, o in known.items():  # a recurrence of an earlier unnamed routine keeps its id (and its consent)
                    if oid not in earlier:
                        continue
                    if o.get("template_id") is None and o.get("signature") and edit_distance(tuple(o["signature"]), tuple(d["signature"])) <= 0.3:
                        rid = oid
                        break
            d = {**d, "id": rid}
            cur = known.get(rid)
            owned = {k: cur[k] for k in OWNED if cur and k in cur}
            base = {"status": "proposed", "consent": {"mode": "none", "irreversible_unattended": [], "typed_confirm": False},
                    "rung": "A0", "shadow": {"runs": 0, "matches": 0, "wilson_lower": 0.0}, "declined_not_now_at": None,
                    "skill_override": False}
            known[rid] = {**base, **d, **owned}
            ids.append(rid)
        self._save(st)
        return ids

    # ----- reads -----
    def get_raw(self, rid: str) -> dict[str, Any]:
        r = self._load()["routines"].get(rid)
        if r is None:
            raise KeyError(rid)
        return r

    def driver(self, rid: str) -> str:
        return "compiled" if (self.bundle_root / rid / "steps.json").exists() else "model"

    def effective(self, r: dict[str, Any], doc: D.MemoryDoc | None = None) -> dict[str, Any]:
        """The routine as it behaves now: stored state tightened by whatever the memory file says."""
        doc = doc or self.memory.read()
        out = json.loads(json.dumps(r))
        mode = out["consent"]["mode"]
        note = None
        if mode in ("shadow", "approval", "unattended"):
            sec = doc.section("Routines", create=False)
            line = next((ln for ln in (sec.lines() if sec else []) if ln.text.split("|")[0].strip() == out["id"]), None)
            if line is None:
                out["consent"] = {"mode": "not_now", "irreversible_unattended": [], "typed_confirm": False}
                out["rung"], out["status"] = "A0", "declined"
                note = "Its line was removed from your memory file, so it is switched off."
            else:
                p = parse_line(line.text)
                if p:
                    if MODE_RANK.get(p["mode"], 0) < MODE_RANK[mode]:
                        out["consent"]["mode"] = p["mode"]
                        out["status"] = STATUS_OF.get(p["mode"], out["status"])
                        note = f"Your memory file says {p['mode']}, which is tighter, so that applies."
                    if not p["unattended"] or p["unattended_classes"] != out["consent"]["irreversible_unattended"]:
                        keep = [c for c in out["consent"]["irreversible_unattended"] if c in p["unattended_classes"]] if p["unattended"] else []
                        out["consent"]["irreversible_unattended"] = keep
                    if RUNGS.index(p["rung"]) < RUNGS.index(out["rung"]):
                        out["rung"] = p["rung"]
                    out["rung"] = RUNGS[min(RUNGS.index(out["rung"]), RUNGS.index(CEILING[out["consent"]["mode"]]))]
        out["driver"] = self.driver(out["id"])
        if note:
            out["note"] = note
        return out

    def contract(self, r: dict[str, Any]) -> dict[str, Any]:
        e = self.effective(r)
        sh = e["shadow"]
        out = {
            "id": e["id"], "role": e["role"], "title": e["title"], "status": e["status"], "episodes": e["episodes"],
            "minutes_per_week": e["minutes_per_week"], "cv": e["cv"], "judgement_share": e["judgement_share"],
            "value": {k: e["value"][k] for k in ("hours_saved", "net_gbp", "confidence", "horizon_weeks")},
            "touches": e["touches"], "never": e["never"],
            "consent": e["consent"], "rung": e["rung"],
            "shadow": {"runs": sh["runs"], "matches": sh["matches"], "wilson_lower": round(sh["wilson_lower"], 3)},
            "build_timing": {k: e["build_timing"][k] for k in ("rule", "buy_after_runs", "regret_vs_hindsight")},
            "skill_gate": e["skill_gate"], "proposal": e["proposal"],
            "bundle": f"data/routines/{e['id']}/steps.json",
            "driver": e["driver"], "irreversible_classes": e["irreversible_classes"],
            "automatable": e["automatable"], "proposable": e["proposable"], "not_proposable_because": e["not_proposable_because"],
            "template_id": e.get("template_id"), "forecast": e.get("forecast"), "last_seen": e.get("last_seen"),
            "build_timing_detail": e["build_timing"],
        }
        if "note" in e:
            out["note"] = e["note"]
        return out

    def list(self) -> list[dict[str, Any]]:
        st = self._load()
        rows = [self.contract(r) for r in st["routines"].values()]
        rows.sort(key=lambda r: (r["status"] != "proposed", -(r["value"]["hours_saved"][1] if r["value"]["hours_saved"] else 0), r["id"]))
        return rows

    def labels(self, person: str) -> list[tuple[float, bool]]:
        return [(x["t"], x["accepted"]) for x in self._load().get("labels", []) if x["person"] == person]

    def refresh_gate(self, source, t: float, person: str | None = None) -> None:
        """Re-evaluate every routine's skill gate against the worker's current skill levels (cheap; no re-detection)."""
        from .gate import routine_skill_gate

        st = self._load()
        changed = False
        for r in st["routines"].values():
            if person is not None and r.get("person") != person:
                continue
            gate = routine_skill_gate(source, r.get("skill_cogs", []), t, learning_relevant=r.get("learning_relevant", True))
            reasons = list(r.get("other_reasons", []))
            if not gate["eligible"]:
                reasons.append(gate["reason"])
            proposable = not reasons
            if gate != r.get("skill_gate") or proposable != r.get("proposable") or reasons != r.get("not_proposable_because"):
                r["skill_gate"], r["proposable"], r["not_proposable_because"] = gate, proposable, reasons
                changed = True
        if changed:
            self._save(st)

    # ----- consent -----
    def consent(self, rid: str, mode: str, *, irreversible_unattended: list[str] | None = None, typed_confirm: str | None = None,
                skill_override: bool = False, actor: str, person: str = "p_me", now: float | None = None) -> dict[str, Any]:
        self.memory._check_actor(actor, "routine consent")
        if mode not in MODES:
            raise ConsentError("bad_mode", f"mode must be one of {', '.join(MODES)}")
        st = self._load()
        r = st["routines"].get(rid)
        if r is None:
            raise KeyError(rid)
        e = self.effective(r)
        classes = list(irreversible_unattended or [])
        if classes and mode != "unattended":
            raise ConsentError("irreversible_needs_unattended", "irreversible_unattended only applies to the unattended mode")
        if mode == "unattended" and classes:
            unknown = [c for c in classes if c not in e["irreversible_classes"]]
            if unknown:
                raise ConsentError("unknown_class", f"this routine has no irreversible class {', '.join(unknown)}; it has: "
                                   f"{', '.join(e['irreversible_classes']) or 'none'}")
            if e["driver"] == "model" and typed_confirm != rid:
                raise ConsentError("typed_confirm_required",
                                   f"a model-driven routine needs you to type its id ({rid}) to allow irreversible steps unattended")
        if mode in ("shadow", "approval", "unattended"):
            if not e["automatable"]:
                raise ConsentError("not_automatable", "this routine needs your judgement, so it stays manual")
            if not e["skill_gate"]["eligible"] and not skill_override:
                raise ConsentError("skill_gate", e["skill_gate"]["reason"] + ". Coach it first, or say you already know it.")
        t = now if now is not None else __import__("time").time()
        prev_mode = r["consent"]["mode"]
        r["consent"] = {"mode": mode, "irreversible_unattended": classes if mode == "unattended" else [],
                        "typed_confirm": bool(classes and typed_confirm == rid)}
        r["status"] = STATUS_OF[mode]
        r["skill_override"] = bool(skill_override and mode in ("shadow", "approval", "unattended"))
        r["blocked"] = False
        r["decided_at"] = now_iso()
        if mode in ("not_now", "never"):
            r["rung"] = "A0"
            if mode == "not_now":
                r["declined_not_now_at"] = t
            r["shadow"] = {"runs": 0, "matches": 0, "wilson_lower": 0.0}
        else:
            r["declined_not_now_at"] = None
            earned = self._earned(r["shadow"], at_least="A1")
            r["rung"] = RUNGS[min(RUNGS.index(earned), RUNGS.index(CEILING[mode]))]
        if prev_mode == "none" or mode in ("not_now", "never", "shadow", "approval", "unattended"):
            st["labels"].append({"person": person, "t": t, "accepted": mode in ("shadow", "approval", "unattended"), "routine": rid})
        self._save(st)
        self._sync(r)
        return self.contract(r)

    # ----- shadow and the ladder -----
    @staticmethod
    def _earned(sh: dict[str, Any], at_least: str = "A0") -> str:
        runs, lw = sh["runs"], sh["wilson_lower"]
        if runs >= PROMOTE_A3[0] and lw >= PROMOTE_A3[1]:
            rung = "A3"
        elif runs >= PROMOTE_A2[0] and lw >= PROMOTE_A2[1]:
            rung = "A2"
        else:
            rung = "A1"
        return rung if RUNGS.index(rung) >= RUNGS.index(at_least) else at_least

    def shadow(self, rid: str, *, matched: bool | None = None, runs: int | None = None, matches: int | None = None,
               event: str | None = None, actor: str = "worker") -> dict[str, Any]:
        """Record shadow runs (one outcome, or a batch) or a failure event; returns the ladder state."""
        if event not in (None, "failure", "undo", "injection"):
            raise ConsentError("bad_event", "event must be failure, undo or injection")
        st = self._load()
        r = st["routines"].get(rid)
        if r is None:
            raise KeyError(rid)
        e = self.effective(r)
        mode = e["consent"]["mode"]
        if mode not in ("shadow", "approval", "unattended"):
            raise ConsentError("not_enabled", "shadow runs only count once the routine is switched on in shadow mode or above", 409)
        before = RUNGS.index(e["rung"])
        sh = r["shadow"]
        if r.get("blocked"):
            raise ConsentError("blocked", "an injection hit paused this routine; switch it on again yourself to continue", 409)
        if event:
            floor = 0 if event == "injection" else 1  # a hit drops to observe-only until the worker re-enables it
            r["rung"] = RUNGS[max(floor, RUNGS.index(r["rung"]) - 1)]
            r["shadow"] = {"runs": 0, "matches": 0, "wilson_lower": 0.0}
            r["blocked"] = event == "injection"
            demoted = True
        else:
            demoted = False
            if runs is not None:
                if matches is None or not (0 <= matches <= runs):
                    raise ConsentError("bad_batch", "matches must be between 0 and runs")
                sh["runs"] += runs
                sh["matches"] += matches
            else:
                sh["runs"] += 1
                sh["matches"] += 1 if matched else 0
            sh["wilson_lower"] = wilson_lower(sh["matches"], sh["runs"])
            earned = self._earned(sh, at_least="A1")
            r["rung"] = RUNGS[min(RUNGS.index(earned), RUNGS.index(CEILING[mode]))]
        self._save(st)
        self._sync(r)
        after = RUNGS.index(r["rung"])
        sh = r["shadow"]
        return {"runs": sh["runs"], "matches": sh["matches"], "wilson_lower": round(sh["wilson_lower"], 3), "rung": r["rung"],
                "promoted": after > before, "demoted": demoted, "ceiling": CEILING[mode],
                "next_rung": None if r["rung"] == "A3" else RUNGS[RUNGS.index(r["rung"]) + 1],
                "needs": {"A2": {"runs": PROMOTE_A2[0], "wilson_lower": PROMOTE_A2[1]}, "A3": {"runs": PROMOTE_A3[0], "wilson_lower": PROMOTE_A3[1]}}}

    # ----- side effects: memory line and the file the agent reads -----
    def _sync(self, r: dict[str, Any]) -> None:
        rid = r["id"]
        mode = r["consent"]["mode"]
        lid = _lid(rid)
        text = line_text(r)

        def mutate(doc: D.MemoryDoc) -> None:
            hit = doc.find(lid)
            if mode in ("not_now", "never", "none"):
                if hit:
                    doc.remove(lid)
                return
            note = "worker override of the skill gate" if r.get("skill_override") else "consent set by you"
            if hit:
                hit[1].text, hit[1].note = D.clean_text(text), note
            else:
                doc.add("Routines", text, note=note, line_id=lid)

        self.memory.mutate("worker", mutate)
        d = self.bundle_root / rid
        try:
            d.mkdir(parents=True, exist_ok=True)
            atomic_write(d / "consent.json", json.dumps({
                "routine_id": rid, "mode": mode, "rung": r["rung"], "irreversible_unattended": r["consent"]["irreversible_unattended"],
                "revoked": mode in ("not_now", "never"), "updated_at": now_iso(),
            }, indent=1))
        except OSError:
            pass  # the shared data directory is the agent's convenience copy; the memory line stays the source of truth
