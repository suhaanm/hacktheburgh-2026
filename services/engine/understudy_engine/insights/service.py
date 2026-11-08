"""The insights service (REQ-9): builds the snapshot, runs the fixed candidate lists through the selection, pins the worker's week, keeps feedback
and shown-history, and shapes every response. No model, no network, no clock of its own (the clock is a parameter; the firm has a fixed ``now``).

Two sources: ``firm`` (the synthetic firm of ``insights.firm``, badge ``synthetic firm``) and ``local`` (this device's own assist ledger; one
person, so the admin views have nothing to compare and say so). Admin payloads are built from per-person NUMBERS and enums only
(``summary.PersonSummary``), never from ledger rows.
"""
from __future__ import annotations

import hashlib
import re
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any

from . import admin as A
from . import texts as T
from . import views as VW
from . import vocab as V
from .firm import build_firm
from .names import natural_key
from .params import DAY, DEFAULT, Params
from .rows import iso_date, row_t, week_bounds
from .select import history_entry, select
from .store import InsightsStore
from .summary import AdminView, summarise
from .types import FirmSnapshot, History, InsightCandidate, PersonRecord, Selection
from .worker import WorkerCtx, worker_run

FIRM_SEED = 0
NUM_KEYS = ("seconds", "k", "n", "days", "seen", "needed", "count", "hours", "k_before", "n_before", "k_after", "n_after")
DETAILS_KINDS = ("time_loss_habit", "habit_improved", "independence_milestone", "relapse", "retention_due", "trade_off")
EFFECT_LABEL = {"role_gap": "Seconds per case beyond the experts", "cohort_trend": "Change in independence", "bottleneck_skill": "Help needed above their other skills",
                "onboarding_speed": "Reached the line by the target, against the design target", "unit_attention": "Independence below the rest of the role",
                "automation_value": "Hours of work handled", "automation_pending": "Hours over four weeks if approved", "risk_signal": "Count or hours",
                "coverage": "Share of people with enough data", "data_stale": "Days since the last update"}
BECAUSE = {
    "time_loss_habit": ["It compares your time on this skill with the expert's median for the same step.", "It uses your own work from the last three weeks."],
    "habit_improved": ["It compares your last three weeks on this skill with the three weeks ending a month ago.", "Errors and unfinished cases did not get worse."],
    "independence_milestone": ["It counts the cases you finished without help out of your last 20 on this skill."],
    "retention_due": ["It looks at how long it has been since you last did this skill, which you had been doing well."],
    "relapse": ["It compares your recent cases on this skill with an earlier run of cases you did without help.", "Cases right after a break are left out."],
    "automation_opportunity": ["It found the same steps repeated, and estimated the time a routine could take over."],
    "calendar_pointer": ["It comes from the calendar layer's comparison with the expert pattern."],
    "git_pointer": ["It comes from the git layer's comparison with the expert pattern."],
    "onboarding": ["There is too little history for any comparison yet."],
    "stale_data": ["The newest work Understudy has from you is older than three weeks."],
    "trade_off": ["Your time on this skill improved, but a quality measure got worse over the same period."],
}
LIMITS = ["A pointer is a prompt to look, not a verdict.", "It is a pattern in your own recent work and says nothing about your ability.", "It is chosen by fixed rules, and worded from a fixed list of sentences."]
ADMIN_LIMITS = ["These figures are for coaching and onboarding, not for evaluating individuals.", "Comparisons are within the same tasks and need at least 5 people per group.",
                "The data is generated until a real deployment says otherwise.", "Insights are chosen by fixed rules, and worded from a fixed list of sentences."]


@dataclass
class AdminBundle:
    view: AdminView
    cands: list[InsightCandidate]
    selection: Selection
    week: str


class UnknownPerson(KeyError):
    pass


def _rows_digest(snap: FirmSnapshot) -> str:
    h = hashlib.sha1(f"{snap.source}|{snap.now}".encode())
    for p in snap.people:
        h.update(f"{p.id}|{p.role}|{p.level}|{len(p.rows)}|{p.rows[-1]['id'] if p.rows else ''}|{p.role_since_t}".encode())
    h.update(f"|{len(snap.routines)}|{len(snap.approvals)}|{len(snap.risk_events)}|{sorted(snap.feed_t.items())}".encode())
    return h.hexdigest()


def _action(c: InsightCandidate) -> dict[str, Any] | None:
    if not c.action_id:
        return None
    label, to, query = V.ACTIONS[c.action_id]
    a: dict[str, Any] = {"id": c.action_id, "label": label, "to": to}
    if query:
        a["query"] = query
    return a


class InsightsService:
    def __init__(self, store: InsightsStore | None = None, *, clock: Callable[[], float] | None = None, snapshot_provider: Callable[[str], FirmSnapshot] | None = None,
                 rewriter: Callable[[str, dict, str], str | None] | None = None, params: Params = DEFAULT, firm_seed: int = FIRM_SEED) -> None:
        self.store = store or InsightsStore()
        self.clock = clock or time.time
        self.snapshot_provider = snapshot_provider
        self.rewriter = rewriter
        self.p = params
        self.firm_seed = firm_seed
        self._firm: FirmSnapshot | None = None
        self._admin: dict[str, AdminBundle] = {}
        self._stand: dict[tuple[str, str, str], tuple[str, str]] = {}
        self._pointer_sources: dict[str, Callable[[str, float], list[dict[str, Any]]]] = {}
        self._lock = threading.RLock()

    # ------------------------------------------------------------------------------------------ sources
    def register_pointer_source(self, name: str, fn: Callable[[str, float], list[dict[str, Any]]]) -> None:
        """The calendar or git layer registers a function ``(person, now) -> [flagged suggestion dicts]``. Absent by default (those layers are off)."""
        self._pointer_sources[name] = fn

    def snapshot(self, source: str) -> FirmSnapshot:
        if self.snapshot_provider is not None:
            return self.snapshot_provider(source)
        if source == "firm":
            built = self._built_firm()
            if built is not None:
                return built
            if self._firm is None:
                self._firm = build_firm(self.firm_seed).snapshot
            return self._firm
        return self._local_snapshot()

    def _built_firm(self) -> FirmSnapshot | None:
        """The firm the seed wrote into the data directory (``<data>/firm/``), when there is one. Checked by a stat on every call, so a firm added, refreshed or removed
        while the engine runs is picked up without a restart; an unreadable or inconsistent firm is treated as absent (``firmstore.load_firm``)."""
        from . import firmstore as FS
        from .paths import data_dir

        return FS.load_cached(data_dir())

    def _local_snapshot(self) -> FirmSnapshot:
        now = self.clock()
        people: list[PersonRecord] = []
        origin = "real"
        try:
            from ..cue.ledger import Ledger

            led = Ledger()
            for pid in led.persons():
                rows = tuple(led.rows(pid))
                if not rows:
                    continue
                last = rows[-1]
                first_t = min(row_t(r) for r in rows)
                o = "real" if all(r.get("origin") == "real" for r in rows) else "synthetic"
                origin = "synthetic" if o == "synthetic" else origin
                role, since = _profile_role(pid)           # the role the worker chose on this device wins over the role of their newest row: after a role change the new role starts clean
                people.append(PersonRecord(id=pid, role=role or last.get("role", "unknown"), level="junior", unit="local", tenure_weeks=int(max(0.0, now - first_t) // (7 * DAY)),
                                           label=pid, origin=o, rows=rows, role_since_t=since))
        except Exception:
            pass
        return FirmSnapshot(now=now, people=tuple(people), origin=origin, badge="live" if origin == "real" else "synthetic", source="local", feed_t={"ledger": now, "risk_feed": now})

    def _person(self, snap: FirmSnapshot, person: str) -> PersonRecord:
        for p in snap.people:
            if p.id == person:
                return p
        if snap.source == "local":
            return PersonRecord(id=person, role="unknown", level="junior", unit="local", tenure_weeks=0, label=person, origin="real")
        raise UnknownPerson(person)

    # ------------------------------------------------------------------------------------------ worker
    def _ctx(self, rec: PersonRecord, snap: FirmSnapshot) -> WorkerCtx:
        routines = [r for r in snap.routines if r.get("person") == rec.id]
        pointers: list[dict[str, Any]] = []
        for name in sorted(self._pointer_sources):
            try:
                pointers += list(self._pointer_sources[name](rec.id, snap.now))
            except Exception:
                continue
        hit: list[dict[str, Any]] = []
        if snap.source == "local":
            hit = _hitlist_rows(rec.id)
        return WorkerCtx(routines=routines, pointers=pointers, hitlist=hit, badge=snap.badge)

    def _worker_selection(self, rec: PersonRecord, snap: FirmSnapshot):
        _wk, w0, _w1 = week_bounds(snap.now, rec.tz)
        out = worker_run(rec, snap.now, self.p, self._ctx(rec, snap))
        hist = self.store.history(rec.id, before=w0)
        sel = select(out.candidates, audience="worker", scope=rec.id, now=snap.now, history=hist, params=self.p)
        return out, sel, w0

    def _pointer(self, s, role: str) -> dict[str, Any]:
        c = s.cand
        r = T.render(c, role=role, rewriter=self.rewriter)
        nums = {k: v for k, v in c.slots.items() if k in NUM_KEYS and isinstance(v, int) and not isinstance(v, bool)}
        return {"id": c.id, "kind": c.kind, "base_kind": V.KINDS[c.kind].id, "polarity": c.polarity, "polarity_label": V.POLARITY_LABEL[c.polarity], "glyph": V.KINDS[c.kind].glyph,
                "title": r["title"], "headline": r["headline"], "detail": r["detail"], "text": r["text"], "source": r["source"], "badge": c.badge, "origin": c.origin,
                "numbers": nums, "action": _action(c), "details_available": c.kind in DETAILS_KINDS, "a11y_label": T.a11y_label(c.polarity, r["headline"]), "reason": s.reason}

    def worker(self, person: str, source: str) -> dict[str, Any]:
        with self._lock:
            snap = self.snapshot(source)
            rec = self._person(snap, person)
            wk, w0, w1 = week_bounds(snap.now, rec.tz)
            ev = {"n": len(rec.rows), "last": max((r["t_hour"] for r in rec.rows), default="")}
            pin = self.store.get_pin(rec.id, wk)
            if pin is not None and not (ev["n"] >= pin["evidence"]["n"] and ev["last"] >= pin["evidence"]["last"]):
                self.store.drop_pin(rec.id, wk)             # the ledger was deleted or reset: nothing derived from it survives
                pin = None
            if pin is None:
                out, sel, w0_ = self._worker_selection(rec, snap)
                pointers = [self._pointer(s, rec.role) for s in sel.selected]
                status = out.status if out.status != "ok" else ("ok" if pointers else "nothing_stands_out")
                pin = {"evidence": ev, "status": status, "pointers": pointers, "stale_sources": out.stale_sources, "needed": out.needed}
                self.store.set_pin(rec.id, wk, pin)
                self.store.record_shown(rec.id, [replace(history_entry(s.cand, w0_), t=w0_) for s in sel.selected])
            hist = self.store.history(rec.id)
            vis = [p for p in pin["pointers"] if not (p["id"] in hist.quiet_ids and snap.now - hist.quiet_ids[p["id"]] <= self.p.novelty_window_days * DAY)
                   and p["kind"] not in hist.hidden_kinds and p["base_kind"] not in hist.hidden_kinds]
            status = pin["status"]
            if not vis and status == "ok":
                status = "nothing_stands_out"
            message = None
            if not vis:
                message = T.NO_DATA.format(needed=pin.get("needed", self.p.onboard_min)) if status == "no_data" else T.NOTHING
            pub = [{k: v for k, v in p.items() if k not in ("base_kind", "reason")} for p in vis]
            return {"person": rec.id, "role": rec.role, "week": {"key": wk, "from": iso_date(w0), "to": iso_date(w1 - DAY)}, "status": status,
                    "nothing_stands_out": not vis, "message": message, "pointers": pub, "try": None, "monday_note": T.monday_note([p["headline"] for p in pub], [p["title"] for p in pub]),
                    "stale_sources": pin["stale_sources"], "cap": self.p.worker_cap, "badge": snap.badge, "origin": snap.origin}

    # ------------------------------------------------------------------------------------------ admin
    def admin(self, source: str) -> AdminBundle:
        with self._lock:
            snap = self.snapshot(source)
            wk, w0, _w1 = week_bounds(snap.now, "UTC")
            hist = self.store.history("admin", before=w0)
            key = hashlib.sha1(f"{_rows_digest(snap)}|{len(hist.shown)}|{sorted(hist.quiet_ids.items())}|{sorted(hist.hidden_kinds)}|{id(self.p)}".encode()).hexdigest()
            b = self._admin.get(key)
            if b is None:
                view = AdminView(snap, self.p)
                cands = A.admin_run(view)
                sel = select(cands, audience="admin", scope="firm", now=snap.now, history=hist, params=self.p)
                b = AdminBundle(view, cands, sel, wk)
                self._admin = {key: b} if len(self._admin) >= 4 else {**self._admin, key: b}
                self.store.record_shown("admin", [replace(history_entry(s.cand, w0), t=w0) for s in sel.selected])
            return b

    def _card(self, s, view: AdminView) -> dict[str, Any]:
        c = s.cand
        r = T.render(c, rewriter=self.rewriter)
        spec = V.KINDS[c.kind]
        eff = {"label": EFFECT_LABEL.get(c.kind, c.kind.replace("_", " ")), "unit": c.unit, "value": c.value, "ci": None if c.lo is None or c.hi is None else [round(c.lo, 4), round(c.hi, 4)]}
        role = c.group if c.group in view.roles() else "all"
        return {"id": c.id, "kind": c.kind, "headline": r["headline"], "text": r["text"], "polarity": c.polarity, "polarity_label": V.POLARITY_LABEL[c.polarity], "glyph": spec.glyph,
                "role": role, "effect": eff, "n": c.n, "n_unit": c.n_unit, "split": c.split, "origin": c.origin, "badge": c.badge, "source": r["source"], "drill": c.id,
                "position": s.position, "a11y_label": T.a11y_label(c.polarity, r["headline"]), "statement": V.STATEMENT, "action": _action(c)}

    def overview(self, source: str) -> dict[str, Any]:
        b = self.admin(source)
        view, sel = b.view, b.selection
        snap = view.snap
        ages = sorted(a.get("age_h", 0.0) for a in snap.approvals)
        med = ages[len(ages) // 2] if ages else None
        cov = view.coverage()
        comp = []
        for role in view.roles():
            d = A.role_gap_detail(view, role)
            td = A.trend_detail(view, role)
            gap = None
            if not d.get("reason"):
                g = d["gap"]
                gap = {"value": round(g["value"], 2), "ci": [round(g["lo"], 2), round(g["hi"], 2)], "unit": "seconds"}
            comp.append({"role": role, "name": V.role_name(role), "people": len(view.people(role=role)), "n_expert": int(d.get("n_expert", 0)), "n_junior": int(d.get("n_junior", 0)),
                         "enough": not d.get("reason"), "reason": d.get("reason"), "gap": gap,
                         "trend": {"class": td.get("class", "not_enough_data"), "label": V.TREND_LABEL[td.get("class", "not_enough_data")]}})
        by_reason: dict[str, int] = {}
        for x in sel.suppressed:
            by_reason[x.reason] = by_reason.get(x.reason, 0) + 1
        return {"firm": {"users": len(view.sums), "roles": len(view.roles()), "label": "Firm"}, "top": [self._card(s, view) for s in sel.selected],
                "nothing_stands_out": not sel.selected, "coverage": cov,
                "risk": {"approval_backlog_age_h": None if not ages else {"median": round(med, 1), "max": round(ages[-1], 1)},
                         "injection_pauses_30d": sum(1 for e in snap.risk_events if e.get("kind") == "injection_pause" and e.get("age_days", 1e9) <= 30),
                         "kill_events_30d": sum(1 for e in snap.risk_events if e.get("kind") == "kill" and e.get("age_days", 1e9) <= 30), "open_approvals": len(ages)},
                "role_comparison": comp, "suppressed": {"count": len(sel.suppressed), "by_reason": dict(sorted(by_reason.items()))},
                "family": sel.family, "statement": V.STATEMENT, "week": b.week, "as_of": iso_date(snap.now), "badge": snap.badge}

    def roles(self, source: str) -> dict[str, Any]:
        return {**VW.roles_payload(self.admin(source).view), "statement": V.STATEMENT}

    def firm(self, source: str) -> dict[str, Any]:
        return {**VW.firm_payload(self.admin(source).view), "statement": V.STATEMENT}

    def onboarding(self, source: str) -> dict[str, Any]:
        return {**VW.onboarding_payload(self.admin(source).view), "statement": V.STATEMENT}

    def drill(self, source: str, insight: str) -> dict[str, Any] | None:
        b = self.admin(source)
        c = b.selection.all_candidates.get(insight)
        if c is None:
            return None
        r = T.render(c) if not c.reason_pre and c.value is not None or c.kind in ("coverage", "data_stale") else None
        headline = r["headline"] if r else f"{V.KINDS[c.kind].id.replace('_', ' ').capitalize()}: {c.subject}"
        d = VW.drill_payload(b.view, c, b.selection.all_candidates, headline)
        st = b.selection.reason_of(insight)
        d["state"], d["reason_code"] = (st if st else ("unknown", "unknown_insight"))
        d["reason_text"] = V.REASON_TEXT[d["reason_code"]]
        d["statement"] = V.STATEMENT
        return d

    # ------------------------------------------------------------------------------------------ why, feedback, sharing
    def why(self, insight: str, *, audience: str, source: str, person: str | None = None) -> dict[str, Any] | None:
        if audience == "admin":
            b = self.admin(source)
            c = b.selection.all_candidates.get(insight)
            st = b.selection.reason_of(insight)
            if c is None or st is None:
                return None
            sc = next((s for s in b.selection.selected if s.cand.id == insight), None)
            r = T.render(c) if (c.value is not None or c.kind in ("coverage", "data_stale", "risk_signal", "automation_value", "automation_pending")) and not c.reason_pre else None
            return {"id": insight, "headline": r["headline"] if r else f"{c.kind.replace('_', ' ')}: {c.subject}", "state": st[0], "reason_code": st[1], "reason_text": V.REASON_TEXT[st[1]],
                    "because": [f"Kind: {c.kind.replace('_', ' ')}.", "Compared within the same tasks, standardised to a fixed skill mix." if c.family else "A count or state with a fixed threshold."],
                    "sources": [{"label": V.SOURCE_NAMES.get(("admin", V.KINDS[c.kind].source), "Understudy"), "n": c.n, "n_unit": c.n_unit, "origin": c.origin}],
                    "limits": ADMIN_LIMITS, "parts": None if sc is None else {**sc.parts, "score": sc.score}, "family": b.selection.family, "position": None if sc is None else sc.position}
        snap = self.snapshot(source)
        rec = self._person(snap, person or "")
        out, sel, _w0 = self._worker_selection(rec, snap)
        c = sel.all_candidates.get(insight)
        st = sel.reason_of(insight)
        if c is None or st is None:
            pin = self.store.get_pin(rec.id, week_bounds(snap.now, rec.tz)[0])
            pp = next((p for p in (pin or {}).get("pointers", []) if p["id"] == insight), None)
            if pp is None:
                return None
            return {"id": insight, "headline": pp["headline"], "state": "selected", "reason_code": pp["reason"], "reason_text": V.REASON_TEXT[pp["reason"]],
                    "because": BECAUSE.get(pp["base_kind"], []), "sources": [{"label": pp["source"], "origin": pp["origin"]}], "limits": LIMITS}
        r = T.render(c, role=rec.role) if not c.reason_pre else None
        return {"id": insight, "headline": r["headline"] if r else f"{c.kind.replace('_', ' ')}: {c.subject}", "state": st[0], "reason_code": st[1], "reason_text": V.REASON_TEXT[st[1]],
                "because": BECAUSE.get(c.kind, BECAUSE.get("trade_off", [])) if st[0] == "selected" else [V.REASON_TEXT[st[1]]],
                "sources": [{"label": V.SOURCE_NAMES.get(("worker", V.KINDS[c.kind].source), "Understudy"), "origin": c.origin}], "limits": LIMITS}

    def feedback(self, insight: str, event: str, *, audience: str, source: str, person: str | None = None) -> dict[str, Any] | None:
        """Record feedback. It only ever makes things quieter: ``useful`` is recorded and changes nothing; the others hide this insight for 28 days or hide its kind."""
        with self._lock:
            snap = self.snapshot(source)
            if audience == "admin":
                c = self.admin(source).selection.all_candidates.get(insight)
                scope = "admin"
            else:
                rec = self._person(snap, person or "")
                _o, sel, _w = self._worker_selection(rec, snap)
                c = sel.all_candidates.get(insight)
                if c is None:
                    pin = self.store.get_pin(rec.id, week_bounds(snap.now, rec.tz)[0]) or {}
                    pp = next((p for p in pin.get("pointers", []) if p["id"] == insight), None)
                    kind = pp["base_kind"] if pp else None
                else:
                    kind = c.kind
                scope = rec.id
                if c is None and kind is None:
                    return None
                self.store.feedback(scope, insight, event, kind, snap.now)
                self._admin = {}
                return {"insight": insight, "event": event, "recorded": True}
            if c is None:
                return None
            self.store.feedback(scope, insight, event, c.kind, snap.now)
            self._admin = {}
            return {"insight": insight, "event": event, "recorded": True}

    def sharing(self, person: str, source: str) -> dict[str, Any]:
        snap = self.snapshot(source)
        rec = self._person(snap, person)
        s = summarise(rec, snap, self.p)
        first = min((row_t(r) for r in rec.rows), default=None)
        return {
            "person": rec.id, "audience": "admin", "level": "summary_numbers",
            "items": [
                {"id": "counts", "label": "How many steps you did and how recently you were last seen", "kind": "count"},
                {"id": "independence", "label": "The share of your last 20 steps finished without help, with its interval", "kind": "number"},
                {"id": "trend", "label": "Whether you need less help over time, as a plain class", "kind": "enum"},
                {"id": "skills", "label": "For each skill: how often you finished without help and how much longer than the expert's median you took, with intervals", "kind": "number"},
                {"id": "automation", "label": "How many routines you approved and how many runs they did", "kind": "count"},
                {"id": "profile", "label": "Your role, unit, tenure band and a pseudonym label", "kind": "enum"},
            ],
            "never": ["Raw events, clicks or keystrokes", "Screenshots", "Text from pages, files or messages", "Your memory file", "Individual ledger rows, times or ids beyond counts",
                      "Names of sites, files or people"],
            "notice": "Your admin sees a summary of numbers about your work, shown below exactly as they see it. It is for coaching and onboarding, not for evaluating individuals. "
                      "You can delete your assist ledger at any time; the summary then shows no data.",
            "visible_since": iso_date(first) if first else None, "visible_to": "People with the Admin role in your firm.", "preview": s.to_row(),
            "legal_note": "A real deployment needs a lawful basis and a clear notice to workers before any of this is shared.",
            "statement": V.STATEMENT, "badge": snap.badge,
        }

    def stand_in(self, role: str, source: str) -> tuple[str, str]:
        """The fixed firm member that stands in for a profile that is not in the synthetic firm (mock mode, worker views only): the first member of ``role`` in natural label
        order who has at least 2 worker pointers in the week, else the first member. The count ignores feedback and history, so the choice never moves. Returns ``(id, label)``."""
        snap = self.snapshot(source)
        key = (source, role, _rows_digest(snap))
        hit = self._stand.get(key)
        if hit is not None:
            return hit
        pool = [pr for pr in snap.people if pr.role == role] or list(snap.people)
        members = sorted(pool, key=lambda pr: natural_key(pr.label or pr.id))
        if not members:
            raise UnknownPerson(role)
        chosen = members[0]
        for m in members:
            out = worker_run(m, snap.now, self.p, self._ctx(m, snap))
            if len(select(out.candidates, audience="worker", scope=m.id, now=snap.now, history=History(), params=self.p).selected) >= 2:
                chosen = m
                break
        self._stand[key] = (chosen.id, chosen.label or chosen.id)
        return self._stand[key]

    def forget_person(self, person: str) -> int:
        with self._lock:
            self._admin = {}
            return self.store.delete_person(person)


def _profile_role(person: str) -> tuple[str | None, float | None]:
    """``(role, None)``: the role the worker chose on this device (the profile's). ``(None, None)`` for anyone else, or when the profile cannot be read."""
    try:
        from .. import routes_handoff as rh
        from ..memory.onboarding import load_profile

        prof = load_profile(rh._mem()) or {}
        if prof.get("person") != person or not prof.get("role"):
            return None, None
        # No "since": ledger rows carry the role they were done under, so the old role's rows are already apart from the new role's, and a worker who returns to a role finds
        # that role's history again (history is kept per role, never mixed). A time cut would hide rows written before the switch, which is exactly the history they came back for.
        return str(prof["role"]), None
    except Exception:
        return None, None


def _hitlist_rows(person: str) -> list[dict[str, Any]]:
    """The repeat list's top row for this person, normalised; empty when the module or the row is absent (it never raises)."""
    try:
        from ..hitlist import top_rows

        rows = top_rows(person, 1)
    except Exception:
        return []
    out: list[dict[str, Any]] = []
    for r in rows or []:
        try:
            if not isinstance(r.get("id"), str) or not re.fullmatch(r"[a-z0-9][a-z0-9_.\-]{0,47}", r["id"]):     # an id is a slug, never text
                continue
            hs = r.get("hours_saved") or {}
            what = "the same step"
            try:
                from ..hitlist.vocab import label_for

                lab = label_for(r["id"])
                if isinstance(lab, str) and lab:
                    what = f"the step {lab}"
            except Exception:
                pass
            out.append({"id": str(r["id"]), "count": int(r.get("count", 0)), "window_days": int(r.get("window_days", 7)), "hours_lo": hs.get("lo"), "hours_hi": hs.get("hi"),
                        "horizon_weeks": hs.get("horizon_weeks", 4), "origin": r.get("origin", "real"), "t": r.get("t"), "what": what})
        except Exception:
            continue
    return out
