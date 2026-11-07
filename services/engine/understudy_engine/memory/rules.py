"""Corrections, precedents and personal rules (MEM-3, MEM-4, MEM-5).

The path from a correction to a rule, every step by code and every write by the worker:

1. The worker corrects the system on a *subject* (``summary_length``, ``check_order``) and picks a *value*.
   That is a **precedent**. The Corrections section shows one line per (subject, value) with a count.
2. Three consistent precedents in a row (same subject, same value, nothing contradicting them, none faded
   by decay) make a **proposal**. A proposal changes nothing.
3. Its **ceiling** (the highest autonomy rung a rule may ever grant, A0 to A3) is the tightest ceiling among
   the precedents, so a rule is never looser than anything the worker already approved. Approval may only
   tighten it further.
4. A separate **approval** by the worker activates it. A personal *procedure* rule additionally has to match
   the expert policy's outcomes in a shadow comparison, or it is rejected (MEM-4).
5. Active rules are lines in the memory file, versioned (``v1``, ``v2`` ...). Behaviour is read **from the
   file**, so deleting the line (or "forget that") ends the rule at once.
"""
from __future__ import annotations

import hashlib
import math
import re
from datetime import datetime, timezone
from typing import Any

from . import doc as D
from .shadow import ExpertPolicy, ShadowResult, parse_order
from .store import MemoryStore, now_iso

RUNGS = ("A0", "A1", "A2", "A3")
N_CONSISTENT = 3
HALF_LIFE_DAYS = 30.0
MIN_WEIGHT = 0.25  # a precedent older than two half-lives no longer counts toward a proposal

_RULE_NOTE = re.compile(r"rule:(?P<key>\S+)\s+v(?P<v>\d+)(?:\s+ceiling:(?P<c>A[0-3]))?")
_CORR_NOTE = re.compile(r"corr:(?P<key>\S+)")


def _h(*parts: str, n: int = 8) -> str:
    return hashlib.sha1("\x00".join(parts).encode()).hexdigest()[:n]


def min_rung(rungs: list[str]) -> str:
    return min(rungs, key=RUNGS.index) if rungs else "A1"


def clamp_rung(requested: str, ceiling: str) -> str:
    """A request is clamped to the rule's ceiling. The model may ask for more; code does not grant it."""
    return RUNGS[min(RUNGS.index(requested), RUNGS.index(ceiling))]


def _label(subject: str) -> str:
    return subject.replace("_", " ").replace("-", " ").strip().capitalize()


def _parse_ts(ts: str | datetime | None) -> datetime:
    if ts is None:
        return datetime.now(timezone.utc)
    if isinstance(ts, datetime):
        return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def decay_weight(age_days: float, half_life_days: float = HALF_LIFE_DAYS) -> float:
    return 0.5 ** (max(0.0, age_days) / half_life_days)


class RuleError(ValueError):
    pass


class RuleEngine:
    def __init__(self, store: MemoryStore, *, policy: ExpertPolicy | None = None, half_life_days: float = HALF_LIFE_DAYS) -> None:
        self.store = store
        self.policy = policy
        self.half_life = half_life_days

    # ------------------------------------------------------------------ state helpers
    def _state(self) -> dict[str, Any]:
        s = self.store.load_state()
        s.setdefault("precedents", [])
        s.setdefault("proposals", [])
        return s

    def _save(self, s: dict[str, Any], actor: str) -> None:
        self.store.save_state(s, actor=actor)

    # ------------------------------------------------------------------ 1. corrections
    def record_correction(self, subject: str, value: Any, *, actor: str, kind: str = "preference",
                          ceiling: str = "A1", now: datetime | str | None = None) -> dict[str, Any]:
        """The worker corrected the system. Returns ``{precedent, line_id, proposal}`` (proposal may be None)."""
        self.store._check_actor(actor, "corrections")  # refuses any non-worker actor and reports it to the audit hook
        if kind not in ("preference", "procedure"):
            raise RuleError("kind must be preference or procedure")
        if ceiling not in RUNGS:
            raise RuleError(f"ceiling must be one of {RUNGS}")
        subject = D.clean_text(subject, 60).replace(" ", "_").lower()
        if not subject:
            raise RuleError("subject is empty")
        val = ">".join(parse_order(value)) if kind == "procedure" else D.clean_text(str(value), 120)
        if not val:
            raise RuleError("value is empty")
        ts = _parse_ts(now)
        s = self._state()
        pid = "pc_" + _h(subject, val, ts.isoformat(), str(len(s["precedents"])))
        s["precedents"].append({"id": pid, "subject": subject, "value": val, "kind": kind,
                                "ts": ts.isoformat(), "ceiling": ceiling, "proposal": None})
        line = self._sync_corrections_line(subject, val, s, now=ts)
        proposal = self._maybe_propose(s, subject, kind, ts)
        self._save(s, actor)
        return {"precedent": pid, "line_id": line, "proposal": self._public(proposal) if proposal else None}

    def _weight(self, p: dict[str, Any], now: datetime) -> float:
        return decay_weight((now - _parse_ts(p["ts"])).total_seconds() / 86400.0, self.half_life)

    def _live(self, s: dict[str, Any], subject: str, now: datetime) -> list[dict[str, Any]]:
        return [p for p in s["precedents"] if p["subject"] == subject and self._weight(p, now) >= MIN_WEIGHT]

    def _sync_corrections_line(self, subject: str, value: str, s: dict[str, Any], now: datetime) -> str | None:
        n = sum(1 for p in self._live(s, subject, now) if p["value"] == value)
        key = f"{subject}={value}"
        lid = "c_" + _h(key)
        shown = value.replace(">", " then ") if ">" in value else value
        text = f"{_label(subject)}: you chose {shown}" + (f" ({n} times)" if n > 1 else "")

        def mutate(doc: D.MemoryDoc) -> None:
            hit = doc.find(lid)
            if n <= 0:
                if hit:
                    doc.remove(lid)
                return
            if hit:
                hit[1].text, hit[1].note = D.clean_text(text), f"corr:{key}"
            else:
                doc.add("Corrections", text, note=f"corr:{key}", line_id=lid)

        self.store.mutate("worker", mutate)
        return lid if n > 0 else None

    # ------------------------------------------------------------------ 2. proposals
    def _maybe_propose(self, s: dict[str, Any], subject: str, kind: str, now: datetime) -> dict[str, Any] | None:
        live = sorted(self._live(s, subject, now), key=lambda p: p["ts"])
        free = [p for p in live if p["proposal"] is None or self._is_open(s, p["proposal"])]
        if not free:
            return None
        last = free[-1]["value"]
        run: list[dict[str, Any]] = []
        for p in reversed(free):  # trailing run of the same value; a different value ends it
            if p["value"] != last:
                break
            run.append(p)
        run.reverse()
        existing = next((q for q in s["proposals"] if q["subject"] == subject and q["value"] == last and q["status"] == "proposed"), None)
        if existing:
            existing["evidence_count"] = len(run)
            existing["precedent_ids"] = [p["id"] for p in run]
            existing["ceiling"] = min_rung([p["ceiling"] for p in run])
            return existing
        if len(run) < N_CONSISTENT:
            return None
        # a still-open proposal for a different value is overtaken by this run
        for q in s["proposals"]:
            if q["subject"] == subject and q["status"] == "proposed":
                q["status"] = "rejected"
                q["reason"] = "superseded by newer corrections"
        kind_ = run[-1]["kind"]
        version = 1 + max([q["version"] for q in s["proposals"] if q["subject"] == subject and q["status"] in ("active", "superseded")] or [0])
        prop = {
            "id": "pr_" + _h(subject, last, str(len(s["proposals"]))),
            "subject": subject, "value": last, "kind": kind_,
            "rule": self._rule_text(subject, last, kind_),
            "evidence_count": len(run), "precedent_ids": [p["id"] for p in run],
            "ceiling": min_rung([p["ceiling"] for p in run]),
            "shadow_match": None, "shadow_n": 0, "status": "proposed", "version": version,
            "created": now_iso(), "decided": None, "reason": None, "awaiting_shadow": kind_ == "procedure",
        }
        s["proposals"].append(prop)
        return prop

    @staticmethod
    def _is_open(s: dict[str, Any], proposal_id: str) -> bool:
        return any(q["id"] == proposal_id and q["status"] == "proposed" for q in s["proposals"])

    @staticmethod
    def _rule_text(subject: str, value: str, kind: str) -> str:
        if kind == "procedure":
            return "Do the checks in this order: " + ", then ".join(parse_order(value)) + "."
        return f"{_label(subject)}: {value}."

    @staticmethod
    def _public(p: dict[str, Any]) -> dict[str, Any]:
        keys = ("id", "rule", "kind", "evidence_count", "shadow_match", "status", "version")
        out = {k: p[k] for k in keys}
        out.update({"subject": p["subject"], "ceiling": p["ceiling"], "shadow_n": p.get("shadow_n", 0),
                    "reason": p.get("reason"), "awaiting_shadow": bool(p.get("awaiting_shadow")) and p["status"] == "proposed"})
        return out

    def proposals(self) -> list[dict[str, Any]]:
        s = self._state()
        return [self._public(p) for p in s["proposals"] if p["status"] != "superseded"]

    def get(self, proposal_id: str) -> dict[str, Any]:
        for p in self._state()["proposals"]:
            if p["id"] == proposal_id:
                return self._public(p)
        raise KeyError(proposal_id)

    # ------------------------------------------------------------------ 3/4. approval, shadow
    def shadow(self, proposal_id: str, cases: list[set[str]] | None = None, *, actor: str = "worker") -> ShadowResult:
        """Run the shadow comparison for a procedure proposal and store the match rate on it."""
        s = self._state()
        p = self._find(s, proposal_id)
        if p["kind"] != "procedure":
            raise RuleError("only procedure rules need a shadow comparison")
        if self.policy is None:
            raise RuleError("no expert policy loaded for this role, so a procedure cannot be shown to match it")
        res = self.policy.compare(parse_order(p["value"]), cases if cases is not None else self.policy.cases(p["id"]))
        p["shadow_match"], p["shadow_n"] = round(res.rate, 4), res.n
        self._save(s, actor)
        return res

    def approve(self, proposal_id: str, *, actor: str, ceiling: str | None = None,
                cases: list[set[str]] | None = None, now: datetime | None = None) -> dict[str, Any]:
        self.store._check_actor(actor, "rule approval")
        s = self._state()
        p = self._find(s, proposal_id)
        if p["status"] != "proposed":
            raise RuleError(f"proposal is {p['status']}, only a proposed rule can be approved")
        if ceiling is not None:
            if ceiling not in RUNGS:
                raise RuleError(f"ceiling must be one of {RUNGS}")
            p["ceiling"] = min_rung([p["ceiling"], ceiling])  # approval can tighten, never loosen
        if p["kind"] == "procedure":
            if self.policy is None:
                p["reason"] = "waiting for an expert policy to compare against"
                self._save(s, actor)
                return self._public(p)
            res = self.policy.compare(parse_order(p["value"]), cases if cases is not None else self.policy.cases(p["id"]))
            p["shadow_match"], p["shadow_n"] = round(res.rate, 4), res.n
            p["awaiting_shadow"] = False
            if not res.adopt:
                p["status"], p["reason"], p["decided"] = "rejected", res.reason(), now_iso()
                self._mark_used(s, p)
                self._save(s, actor)
                return self._public(p)
            p["reason"] = res.reason()
        self._activate(s, p)
        p["status"], p["decided"] = "active", now_iso()
        self._mark_used(s, p)
        self._save(s, actor)
        return self._public(p)

    def reject(self, proposal_id: str, *, actor: str) -> dict[str, Any]:
        self.store._check_actor(actor, "rule rejection")
        s = self._state()
        p = self._find(s, proposal_id)
        if p["status"] != "proposed":
            raise RuleError(f"proposal is {p['status']}, only a proposed rule can be rejected")
        p["status"], p["decided"], p["reason"] = "rejected", now_iso(), "rejected by you"
        self._mark_used(s, p)
        self._save(s, actor)
        return self._public(p)

    @staticmethod
    def _find(s: dict[str, Any], proposal_id: str) -> dict[str, Any]:
        for p in s["proposals"]:
            if p["id"] == proposal_id:
                return p
        raise KeyError(proposal_id)

    @staticmethod
    def _mark_used(s: dict[str, Any], p: dict[str, Any]) -> None:
        for pc in s["precedents"]:
            if pc["id"] in p.get("precedent_ids", []):
                pc["proposal"] = p["id"]

    def _activate(self, s: dict[str, Any], p: dict[str, Any]) -> None:
        section = "Procedure" if p["kind"] == "procedure" else "Preferences"
        key = p["subject"]
        lid = "r_" + _h(key)
        for q in s["proposals"]:
            if q["subject"] == key and q["status"] == "active" and q is not p:
                q["status"] = "superseded"
        text = p["rule"]
        note = f"rule:{key} v{p['version']} ceiling:{p['ceiling']} approved {now_iso()[:10]}"

        def mutate(doc: D.MemoryDoc) -> None:
            hit = doc.find(lid)
            if hit:
                sec, ln = hit
                ln.text, ln.note = D.clean_text(text), note
                if sec.name != section:  # a rule that changed kind moves section
                    doc.remove(lid)
                    doc.add(section, text, note=note, line_id=lid)
            else:
                doc.add(section, text, note=note, line_id=lid)

        self.store.mutate("worker_approval", mutate)
        p["line_id"] = lid

    # ------------------------------------------------------------------ behaviour (read from the file)
    def active_rules(self) -> list[dict[str, Any]]:
        """Rules in force right now: lines in the file that carry a rule note. Delete the line, lose the rule."""
        doc = self.store.read()
        out = []
        for name in ("Preferences", "Procedure"):
            sec = doc.section(name, create=False)
            for ln in (sec.lines() if sec else []):
                m = _RULE_NOTE.search(ln.note)
                if m:
                    out.append({"line_id": ln.id, "subject": m.group("key"), "version": int(m.group("v")),
                                "ceiling": m.group("c") or "A1", "text": ln.text, "section": name})
        return out

    # ------------------------------------------------------------------ 5. forget and decay
    def forget(self, line_id: str, *, actor: str) -> int:
        """Delete a line and everything that would bring it back: its precedents, and an open proposal on it."""
        self.store._check_actor(actor, "forget")
        doc = self.store.read()
        hit = doc.find(line_id)
        subj_val: tuple[str, str | None] | None = None
        if hit:
            note = hit[1].note
            rm, cm = _RULE_NOTE.search(note), _CORR_NOTE.search(note)
            if rm:
                subj_val = (rm.group("key"), None)
            elif cm and "=" in cm.group("key"):
                subj, val = cm.group("key").split("=", 1)
                subj_val = (subj, val)
        rev = self.store.forget(line_id, actor=actor)
        if subj_val:
            subject, value = subj_val
            s = self._state()
            s["precedents"] = [p for p in s["precedents"] if not (p["subject"] == subject and (value is None or p["value"] == value))]
            for q in s["proposals"]:
                if q["subject"] == subject and (value is None or q["value"] == value) and q["status"] in ("proposed", "active"):
                    q["status"], q["reason"], q["decided"] = "rejected", "forgotten by you", now_iso()
            self._save(s, actor)
            # the Corrections line for a forgotten rule goes too
            if value is None:
                def mutate(d: D.MemoryDoc) -> None:
                    for sec in d.sections:
                        for ln in list(sec.lines()):
                            m = _CORR_NOTE.search(ln.note)
                            if m and m.group("key").startswith(subject + "="):
                                d.remove(ln.id)
                self.store.mutate(actor, mutate)
                rev = self.store.revision()
        return rev

    def decay(self, now: datetime | None = None, *, actor: str = "worker") -> dict[str, int]:
        """Drop precedents that have faded below the weight floor and tidy their Corrections lines."""
        self.store._check_actor(actor, "decay")
        t = _parse_ts(now)
        s = self._state()
        keep, dropped = [], 0
        for p in s["precedents"]:
            if self._weight(p, t) >= MIN_WEIGHT:
                keep.append(p)
            else:
                dropped += 1
        s["precedents"] = keep
        groups = {(p["subject"], p["value"]) for p in keep}
        removed_lines = 0

        def mutate(doc: D.MemoryDoc) -> None:
            nonlocal removed_lines
            for sec in doc.sections:
                if sec.name != "Corrections":
                    continue
                for ln in list(sec.lines()):
                    m = _CORR_NOTE.search(ln.note)
                    if not m or "=" not in m.group("key"):
                        continue
                    subj, val = m.group("key").split("=", 1)
                    if (subj, val) not in groups:
                        doc.remove(ln.id)
                        removed_lines += 1

        if dropped:
            self.store.mutate(actor, mutate)
        self._save(s, actor)
        return {"precedents_dropped": dropped, "lines_removed": removed_lines}


def half_life_for_weight(w: float, half_life_days: float = HALF_LIFE_DAYS) -> float:
    """Days until a precedent decays to weight ``w``."""
    return half_life_days * math.log(1 / w, 2)
