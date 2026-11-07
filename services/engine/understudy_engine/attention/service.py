"""The attention service (REQ-8): the store, the router and the digest builder tied into the six operations the routes expose.

    submit(event, worker_state)   a producer reports something. Helpful-now events (Cue) get the admission answer at once (``show``);
                                  everything else is registered, counted in the passive badge from this moment, and delivered by ``next``.
    next(person, worker_state)    what to show now: AT MOST ONE item, plus the passive counts. Held items are re-decided with the worker
                                  state of this moment; a due reminder and a digest on return are decided the same way.
    feedback(item, event)         the worker's reaction: the implicit label that teaches the router to be quieter, never louder.
    digest(person, kind)          the summary.   why(item)   the fixed one-line reason.   settings   the worker's own choices.

All decisions are the router's. This module only keeps the books: it never decides a channel itself. Metadata only; no network, no model.
The clock is injected (``clock``) and every call can carry its own ``now``, so a simulated day replays exactly.
"""
from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterable
from dataclasses import replace
from hashlib import sha1
from typing import Any

from . import digest as D
from . import paths
from . import texts
from . import vocab as V
from .events import Event, EventError, Item
from .learning import Label, label_of
from .router import AttentionRouter, Decision, is_natural_break
from .state import DEFAULT, History, Lock, Params, Settings, WorkerState
from .store import AttentionStore, PersonState

LABEL_REACTIONS = ("followed", "dismissed", "ignored", "never", "opened")


def local_day(now: float, local_hour: int) -> str:
    """A day key from the instant and the worker's local hour (the offset is read off the two; no time zone database needed)."""
    utc_hour = int(now // 3600) % 24
    off = ((int(local_hour) - utc_hour + 12) % 24) - 12
    return str(int((now + off * 3600) // 86400))


class AttentionService:
    def __init__(self, store: AttentionStore | None = None, params: Params = DEFAULT, clock: Callable[[], float] = time.time,
                 retain_s: float = 7 * 86400.0, prune_above: int = 200) -> None:
        self.store = store or AttentionStore()
        self.p = params
        self.router = AttentionRouter(params)
        self.clock = clock
        self.retain_s = retain_s
        self.prune_above = prune_above
        self.lock = threading.RLock()

    # ------------------------------------------------------------------------------------------------ small helpers
    def _hist(self, ps: PersonState, now: float) -> History:
        lk = ps.lock
        lock = Lock(lk["item_id"], lk["owner"], lk["family_key"], float(lk["until"])) if lk and float(lk["until"]) > now else None
        return History(day=ps.day, budget_used=ps.budget_used, wait_toasts=ps.wait_toasts, last_interruption_t=ps.last_interruption_t,
                       level_glances=tuple(t for t in ps.level_glances if now - t < 3600.0), lock=lock, settings=ps.get_settings(),
                       never_subjects=frozenset(ps.never_subjects), learned_drop=ps.acc.learned_drop,
                       level_glance_env_off=paths.level_glance_env_off())

    def _count(self, ps: PersonState, key: str) -> None:
        ps.counters[key] = ps.counters.get(key, 0) + 1

    def _set(self, ps: PersonState, it: Item, state: str, reason: str | None, now: float) -> None:
        if state == it.state and (reason is None or reason == it.reason_code):
            return
        old = it.state
        it.state = state
        if reason is not None:
            it.reason_code = reason
        it.note(now, state, it.reason_code)
        self.store.log({"t": round(now, 3), "p": ps.person, "i": it.id, "type": it.type, "from": old, "to": state, "reason": it.reason_code,
                        "ch": it.channel})
        if state in ("suppressed", "expired", "resolved") and reason and reason.startswith("dropped"):
            self._count(ps, f"dropped:{reason}")

    def _new_id(self, ps: PersonState, ev: Event) -> str:
        ps.seq += 1
        return "i_" + sha1(f"{ps.person}|{ps.seq}|{ev.type}|{ev.subject}".encode()).hexdigest()[:12]

    def _roll_day(self, ps: PersonState, day: str) -> None:
        if ps.day != day:
            ps.day, ps.budget_used, ps.wait_toasts = day, 0, 0
            ps.counters = {}

    def _prune(self, ps: PersonState, now: float) -> None:
        old = [k for k, i in ps.items.items() if i.state in V.TERMINAL and now - max(i.first_t, i.shown_t or 0.0) > self.retain_s]
        for k in old:
            del ps.items[k]

    def _tick(self, ps: PersonState, now: float) -> None:
        """Expire what ran out, end a display whose time is up (an untouched one is labelled ignored), drop the old."""
        for it in list(ps.items.values()):
            if it.state in V.TERMINAL:
                continue
            if now >= it.expires_at:
                self._set(ps, it, "expired", "dropped_expired", now)
        lk = ps.lock
        if lk and float(lk["until"]) <= now:
            ps.lock = None
        for it in ps.items.values():
            if it.interrupted and not it.labelled and it.until is not None and it.until <= now and it.state in ("shown", "reminded"):
                self._react(ps, it, "ignored", None, now, auto=True)
        if len(ps.items) > self.prune_above:
            self._prune(ps, now)

    # ------------------------------------------------------------------------------------------------ presence
    def _derive(self, ps: PersonState, ws: WorkerState) -> WorkerState:
        """Track presence from the polls (the worker's coming and going) and add what the router needs: ``returned_s`` and the day."""
        p, now = self.p, ws.now
        day = local_day(now, ws.local_hour)
        self._roll_day(ps, day)
        if not ws.known:
            return replace(ws, day=day)
        ret: dict[str, Any] | None = None
        if ws.absent:
            if ps.away_since is None:
                ps.away_since = now - max(0.0, ws.away_s)
        else:
            absence = None
            if ps.away_since is not None:
                absence, ps.away_since = now - ps.away_since, None
            elif ps.last_active_t is not None and now - ps.last_active_t >= p.welcome_away_s:
                absence = now - ps.last_active_t                     # the app was not polling (asleep or quit): the gap is the absence
            if absence is not None and absence >= p.welcome_away_s:
                kind = "morning" if absence >= p.morning_away_s and p.morning_hour_lo <= ws.local_hour < p.morning_hour_hi else "return"
                ret = {"kind": kind, "absence_s": round(absence, 1)}
                ps.returned_t = now
                ps.pending_return = ret
            ps.last_active_t = now
        rs = now - ps.returned_t if ps.returned_t is not None and now - ps.returned_t <= p.return_window_s else None
        return replace(ws, returned_s=rs, day=day)

    # ------------------------------------------------------------------------------------------------ submit
    def submit(self, ev: Event, ws: WorkerState | None = None, now: float | None = None) -> dict[str, Any]:
        with self.lock:
            t = ev.t if ev.t is not None else (now if now is not None else (ws.now if ws is not None else self.clock()))
            ps = self.store.person(ev.person)
            if ws is None:
                ws = self._last_ws(ps, t)
            self._roll_day(ps, local_day(t, ws.local_hour))
            self._tick(ps, t)
            ws = replace(ws, now=t)
            if ev.op == "resolve":
                return self._resolve(ps, ev, t)
            if ev.type == "kill_cleared":
                for it in list(ps.items.values()):
                    if it.family == "kill" and it.type == "kill_engaged" and it.state not in V.TERMINAL:
                        self._set(ps, it, "resolved", "dropped_resolved", t)
            open_ = [i for i in ps.items.values() if i.dedup_key == ev.dedup_key and i.state not in V.TERMINAL]
            same = next((i for i in open_ if i.type == ev.type), None)
            hist = self._hist(ps, t)
            if same is not None:
                return self._coalesce(ps, same, ev, ws, hist, t)
            # a newer item in the same family and subject replaces an older one: the older was either unseen (dropped quietly) or shown
            # (its world changed). Either way the badge counts the story once.
            first_t = t
            for o in open_:
                first_t = min(first_t, o.first_t) if o.state == "held" else first_t
                self._set(ps, o, "suppressed" if o.state == "held" else "resolved", "dropped_superseded", t)
            it = Item.from_event(ev, self._new_id(ps, ev), t)
            it.first_t = first_t
            ps.items[it.id] = it
            it.note(t, "held", "submitted")
            dec = self.router.decide(it, ws, hist)
            show = self._apply(ps, it, dec, t, admission=True)
            self.store.save()
            return {"item_id": it.id, "coalesced": False, "show": show, "decision": dec.to_dict(), "state": it.state}

    def _last_ws(self, ps: PersonState, t: float) -> WorkerState:
        """The most recent worker state a poll gave us, if it is fresh enough; else unknown (held, never interrupted)."""
        d = ps.last_ws
        if d and t - float(d["t"]) <= self.p.state_max_age_s:
            return WorkerState(**{**d["ws"], "now": t})
        return WorkerState(now=t, known=False)

    def _coalesce(self, ps: PersonState, it: Item, ev: Event, ws: WorkerState, hist: History, t: float) -> dict[str, Any]:
        it.occurrences += 1
        it.count = max(it.count, ev.count)
        sp = it.spec
        life = ev.expires_in_s if ev.expires_in_s is not None else sp.ttl_s
        it.expires_at = min(max(it.expires_at, t + life), it.first_t + max(sp.ttl_s, it.expires_at - it.first_t))
        if ev.outcome:
            it.outcome = ev.outcome
        on_screen = it.interrupted and it.state in ("shown", "reminded") and it.until is not None and it.until > t
        if on_screen and sp.cls == V.HELPFUL:
            # a tier escalation of the cue already up: a continuation, not a new interruption. The display and the lock run on.
            disp = min(V.DISPLAY_S.get(it.channel, 12.0), max(1.0, it.expires_at - t))
            it.until = max(it.until or 0.0, t + disp)
            if ps.lock and ps.lock["item_id"] == it.id:
                ps.lock["until"] = it.until
        dec = self.router.decide(it, ws, hist)
        self.store.save()
        return {"item_id": it.id, "coalesced": True, "show": bool(on_screen), "decision": dec.to_dict(), "state": it.state}

    def _resolve(self, ps: PersonState, ev: Event, t: float) -> dict[str, Any]:
        n = 0
        for it in list(ps.items.values()):
            if it.dedup_key == ev.dedup_key and it.state not in V.TERMINAL:
                self._set(ps, it, "resolved", "dropped_resolved", t)
                if ps.lock and ps.lock["item_id"] == it.id:
                    ps.lock = None
                n += 1
        self.store.save()
        return {"item_id": None, "coalesced": False, "show": False, "resolved": n, "decision": None, "state": "resolved"}

    def _apply(self, ps: PersonState, it: Item, dec: Decision, t: float, *, admission: bool) -> bool:
        """Book a decision on an item. Returns True when a helpful-now item is to be shown right now (the admission answer)."""
        it.channel, it.deliver_at = dec.channel, dec.deliver_at
        if dec.reason_code != it.reason_code:
            it.reason_code = dec.reason_code
            it.note(t, it.state, dec.reason_code)
        if dec.drop:
            state = "expired" if dec.reason_code == "dropped_expired" else ("resolved" if dec.reason_code == "dropped_resolved" else "suppressed")
            self._set(ps, it, state, dec.reason_code, t)
            return False
        sp = it.spec
        if dec.interrupting and dec.deliver_at == V.NOW and admission and sp.cls in (V.HELPFUL, V.INFO):
            self._show(ps, it, dec, t, reminder=False)
            return True
        if dec.channel in V.PASSIVE and dec.deliver_at == V.NOW and it.state == "held":
            self._set(ps, it, "shown", dec.reason_code, t)          # a count or a banner is visible at once; no interruption happened
            self._count(ps, f"passive:{dec.channel}")
        return False

    def _show(self, ps: PersonState, it: Item, dec: Decision, t: float, *, reminder: bool) -> None:
        sp = it.spec
        prev = ps.lock
        if prev and prev["item_id"] != it.id and dec.preempt:
            old = ps.items.get(prev["item_id"])
            if old is not None:
                old.until, old.labelled = t, True                      # cut short by something that outranks it: not the worker's reaction
                old.note(t, old.state, "preempted")
        it.prev_interruption_t, it.prev_budget = ps.last_interruption_t, [ps.budget_used, ps.wait_toasts]
        it.interrupted = True
        if it.shown_t is None:
            it.shown_t = t
        it.until = t + dec.display_s
        if reminder:
            it.reminders += 1
            it.reminded_t = t
        self._set(ps, it, "reminded" if reminder else "shown", dec.reason_code, t)
        ps.lock = {"item_id": it.id, "owner": dec.owner, "family_key": it.dedup_key, "until": it.until}
        ps.last_interruption_t = t
        self._count(ps, f"shown:{dec.channel}")
        if it.type == "help_level_changed":
            ps.level_glances.append(t)
            ps.level_glances = [x for x in ps.level_glances if t - x < 3600.0]
        elif not reminder and sp.cls in (V.HELPFUL, V.WAIT) and it.type != "attention_digest":
            ps.budget_used += 1
            if sp.cls == V.WAIT and dec.channel == V.TOAST:
                ps.wait_toasts += 1

    # ------------------------------------------------------------------------------------------------ next
    def peek(self, person: str, now: float | None = None) -> dict[str, Any]:
        """The passive counts and what is on screen, delivering nothing and changing nothing (the adapter uses it while the local lock is held)."""
        with self.lock:
            t = now if now is not None else self.clock()
            ps = self.store.person(person)
            lk = self._hist(ps, t).lock
            out: dict[str, Any] = {"item": None}
            out["active"] = {"id": lk.item_id, "type": ps.items[lk.item_id].type, "until": lk.until} if lk and lk.item_id in ps.items else None
            out.update(self._badges(ps))
            out["poll_after_s"] = 2.0
            return out

    def next(self, person: str, ws: WorkerState) -> dict[str, Any]:
        with self.lock:
            now = ws.now
            ps = self.store.person(person)
            self._tick(ps, now)
            ws = self._derive(ps, ws)
            if ws.known:
                ps.last_ws = {"t": now, "ws": {k: v for k, v in ws.__dict__.items() if k not in ("now", "known", "t", "returned_s", "day")}}
            self._maybe_digest(ps, ws)
            hist = self._hist(ps, now)
            self._refresh_digest_needs(ps)
            cands: list[tuple[Item, Decision, bool]] = []
            soon = 15.0                                   # when the adapter should ask again, at the latest
            for it in sorted((i for i in ps.items.values() if i.state not in V.TERMINAL), key=lambda i: (i.first_t, i.id)):
                if it.state == "held":
                    dec = self.router.decide(it, ws, hist)
                    self._apply(ps, it, dec, now, admission=False)
                    if it.state != "held":
                        continue
                    if dec.interrupting:
                        soon = min(soon, 2.0)             # something is waiting for a pause: look often
                    if dec.interrupting and dec.deliver_at == V.NOW:
                        cands.append((it, dec, False))
                elif it.state == "shown" and it.interrupted:
                    rd = self.router.reminder(it, ws, hist)
                    if rd is not None:
                        cands.append((it, rd, True))
                    elif it.spec.reminders and it.reminders < self.p.max_reminders and it.shown_t is not None:
                        after = self.p.reminder_after(hist.settings.mode(it.type))
                        if after is not None:
                            soon = min(soon, max(1.0, it.shown_t + after - now))
                if it.until is not None and it.until > now:
                    soon = min(soon, max(1.0, it.until - now))
            chosen = self._choose(ps, cands, ws, hist)
            out: dict[str, Any] = {"item": None}
            if chosen is not None:
                it, dec, reminder = chosen
                self._show(ps, it, dec, now, reminder=reminder)
                r = texts.render_item(it, now=now, reminder=reminder)
                out["item"] = {"id": it.id, "type": it.type, "channel": dec.channel, "text_id": r["text_id"], "title": r["title"], "body": r["body"],
                               "source": r["source"], "count": it.count, "actions": texts.actions_for(it.type), "priority": dec.priority,
                               "new": True, "preempt": dec.preempt, "reminder": reminder, "display_s": dec.display_s,
                               "expires_in_s": round(max(0.0, it.expires_at - now), 1), "reason_code": dec.reason_code,
                               "digest": it.payload if it.type == "attention_digest" else None}
            lk = hist.lock if (hist.lock is None or hist.lock.until > now) else None
            lk = Lock(ps.lock["item_id"], ps.lock["owner"], ps.lock["family_key"], float(ps.lock["until"])) if ps.lock and float(ps.lock["until"]) > now else None
            out["active"] = {"id": lk.item_id, "type": ps.items[lk.item_id].type, "until": lk.until} if lk and lk.item_id in ps.items else None
            out.update(self._badges(ps))
            out["poll_after_s"] = round(30.0 if ws.absent and soon >= 15.0 else max(1.0, soon), 1)
            self.store.save()
            return out

    def _choose(self, ps: PersonState, cands: list[tuple[Item, Decision, bool]], ws: WorkerState, hist: History) -> tuple[Item, Decision, bool] | None:
        if not cands:
            return None
        top = max(d.priority for _, d, _ in cands)
        if top < 2:
            waits = [c for c in cands if c[0].spec.cls == V.WAIT and c[0].type != "attention_digest" and not c[2]]
            if len(waits) >= 2:
                # several can-wait items at one break become ONE summary, never one notice after another
                dig = self._rollup(ps, [c[0] for c in waits], ws.now)
                dec = self.router.decide(dig, ws, hist)
                if dec.interrupting and dec.deliver_at == V.NOW:
                    cands = [c for c in cands if c not in waits] + [(dig, dec, False)]
                else:
                    self._apply(ps, dig, dec, ws.now, admission=False)
                    cands = [c for c in cands if c not in waits]
                if not cands:
                    return None
        cands.sort(key=lambda c: (-c[1].priority, c[0].first_t, c[0].id))
        return cands[0]

    # ------------------------------------------------------------------------------------------------ digests
    def _new_digest(self, ps: PersonState, kind: str, payload: dict[str, Any], now: float, folded: list[Item]) -> Item:
        ps.seq += 1
        did = "i_" + sha1(f"{ps.person}|{ps.seq}|digest|{kind}".encode()).hexdigest()[:12]
        sp = V.TYPES["attention_digest"]
        it = Item(id=did, person=ps.person, type="attention_digest", subject=f"digest_{kind}_{ps.seq}", dedup_key=f"digest:digest_{kind}_{ps.seq}",
                  first_t=now, expires_at=now + sp.ttl_s, count=max(1, payload["needs_you"] + payload["ran"] + payload["can_ignore"]),
                  payload={**payload, "kind": kind}, needs_you_n=payload["needs_you_unshown"])
        it.note(now, "held", "built")
        ps.items[it.id] = it
        for f in folded:
            f.folded_into = it.id
            self._set(ps, f, "digested", "shown_digest", now)
        ps.last_digest_t = now
        return it

    def _rollup(self, ps: PersonState, items: list[Item], now: float) -> Item:
        uniq = list({i.id: i for i in list(items) + D.needs_items(ps.items.values())}.values())
        payload = D.summarise(uniq, "rollup", now, self.p)
        return self._new_digest(ps, "rollup", payload, now, [i for i in items if i in D.foldable(items)])

    def _maybe_digest(self, ps: PersonState, ws: WorkerState) -> None:
        pr = ps.pending_return
        if not pr:
            return
        ps.pending_return = None
        now = ws.now
        if ps.last_digest_t is not None and now - ps.last_digest_t < self.p.digest_gap_s:
            return
        payload = D.summarise(ps.items.values(), pr["kind"], now, self.p)
        if payload["needs_you"] + payload["ran"] + payload["can_ignore"] == 0:
            return                                                    # nothing to say is silence, not a summary
        self._new_digest(ps, pr["kind"], payload, now, D.foldable(ps.items.values()))

    def _refresh_digest_needs(self, ps: PersonState) -> None:
        """A held digest toast is only a toast while something it lists still has not been shown on its own."""
        unshown = sum(1 for i in D.needs_items(ps.items.values()) if i.state == "held")
        for it in ps.items.values():
            if it.type == "attention_digest" and it.state == "held":
                it.needs_you_n = unshown

    def digest(self, person: str, kind: str, now: float | None = None) -> dict[str, Any]:
        """``kind`` is morning, return, rollup (the latest built one) or now (a preview of the day so far; nothing is folded)."""
        with self.lock:
            t = now if now is not None else self.clock()
            ps = self.store.person(person)
            if kind == "now":
                payload = D.summarise(ps.items.values(), "now", t, self.p)
                payload["today"] = dict(ps.counters)
                payload["today_detail"] = self._today_detail(ps)
                payload["budget"] = {"used": ps.budget_used, "per_day": ps.get_settings().budget_per_day}
                return payload
            latest = [i for i in ps.items.values() if i.type == "attention_digest" and i.payload.get("kind") == kind]
            if not latest:
                return {"kind": kind, "built_t": None, "needs_you": 0, "ran": 0, "can_ignore": 0, "lines": [], "counts": {"needs_you": 0, "ran": 0, "can_ignore": 0, "lines": 0}}
            it = max(latest, key=lambda i: i.first_t)
            return {**it.payload, "item_id": it.id, "state": it.state}

    def _today_detail(self, ps: PersonState) -> list[dict[str, Any]]:
        """Today's counts as rows a screen can show: what happened, why, how many, in the fixed words. Held items are counted live."""
        rows: list[dict[str, Any]] = []
        for key, n in sorted(ps.counters.items()):
            kind, _, code = key.partition(":")
            if kind == "dropped":
                rows.append({"state": "dropped", "code": code, "n": n, "reason_text": texts.reason_text(code)})
            elif kind == "shown":
                rows.append({"state": "shown", "code": code, "n": n, "reason_text": texts.CHANNEL_TEXT.get(code, "Shown on screen.")})
            elif kind == "passive":
                rows.append({"state": "passive", "code": code, "n": n, "reason_text": texts.CHANNEL_TEXT.get(code, "Counted, not shown on screen.")})
        held: dict[str, int] = {}
        for i in ps.items.values():
            if i.state == "held":
                held[i.reason_code] = held.get(i.reason_code, 0) + 1
        for code, n in sorted(held.items()):
            rows.append({"state": "held", "code": code, "n": n, "reason_text": texts.reason_text(code)})
        return rows

    # ------------------------------------------------------------------------------------------------ badges and markers
    def _badges(self, ps: PersonState) -> dict[str, Any]:
        open_ = [i for i in ps.items.values() if i.state not in V.TERMINAL]
        needs = [i for i in open_ if i.spec.needs_you and i.type != "attention_digest"]
        waiting = [i for i in open_ if i.spec.cls == V.WAIT and not i.spec.needs_you and i.type != "attention_digest" and i.state in ("held", "shown")]
        stopped = any(i.type == "kill_engaged" for i in open_)
        dig = [i for i in open_ if i.type == "attention_digest" and i.state in ("held", "shown", "reminded")]
        n_needs = sum(max(1, i.count) if i.type in ("approval_waiting", "approval_blocking") else 1 for i in needs if i.type != "kill_engaged")
        # `marker` is derived from open items and from nothing else: no worker state, no quiet rule and no lock can delay it.
        marker = "stopped" if stopped else ("needs_you" if n_needs > 0 else "none")
        return {"badges": {"needs_you": n_needs, "waiting": sum(max(1, i.count) for i in waiting), "marker": marker, "stopped": stopped},
                "digest_ready": bool(dig)}

    def badges(self, person: str) -> dict[str, Any]:
        with self.lock:
            return self._badges(self.store.person(person))

    # ------------------------------------------------------------------------------------------------ feedback
    def feedback(self, person: str, item_id: str, event: str, seconds: float | None = None, now: float | None = None) -> dict[str, Any]:
        if event not in V.FEEDBACK_EVENTS:
            raise EventError("bad_event", f"event must be one of {', '.join(V.FEEDBACK_EVENTS)}.")
        with self.lock:
            t = now if now is not None else self.clock()
            ps = self.store.person(person)
            it = ps.items.get(item_id)
            if it is None:
                raise EventError("unknown_item", "There is no such item.")
            if event == "deferred":
                self._defer(ps, it, t)
                self.store.save()
                return {"item_id": it.id, "state": it.state, "label": None}
            if event == "shown":
                if it.shown_t is None:
                    it.shown_t = t
                if it.state == "held":
                    self._set(ps, it, "shown", None, t)
                self.store.save()
                return {"item_id": it.id, "state": it.state, "label": None}
            label = self._react(ps, it, event, seconds, t)
            self.store.save()
            return {"item_id": it.id, "state": it.state, "label": label}

    def _defer(self, ps: PersonState, it: Item, now: float) -> None:
        """The desktop could not draw an item it was handed (the voice was taken, a render failed): give it back. The item is held again,
        the spacing clock and the day's counters return to what they were, no label is recorded and the lock is released."""
        if not it.interrupted or it.state not in ("shown", "reminded"):
            return
        if ps.lock and ps.lock["item_id"] == it.id:
            ps.lock = None
        if it.state == "reminded":
            it.reminders = max(0, it.reminders - 1)
            self._set(ps, it, "shown", "held_lock", now)
            return
        it.interrupted, it.shown_t, it.until, it.labelled = False, None, None, False
        ps.last_interruption_t = it.prev_interruption_t
        if len(it.prev_budget) == 2:
            ps.budget_used, ps.wait_toasts = it.prev_budget
        if it.type == "help_level_changed" and ps.level_glances:
            ps.level_glances.pop()
        self._set(ps, it, "held", "held_lock", now)

    def _react(self, ps: PersonState, it: Item, event: str, seconds: float | None, now: float, *, auto: bool = False) -> str | None:
        sp = it.spec
        label = label_of(event, seconds)
        if label is None:
            return None
        if ps.lock and ps.lock["item_id"] == it.id and event != "ignored":
            ps.lock = None
        if not it.labelled:
            it.labelled = True
            it.reacted = label
            if sp.cls != V.SAFETY and sp.cls != V.INFO and it.type != "attention_digest":
                ps.labels.append(Label(it.type, self._hour_of(ps, now), label, seconds, it.subject, now).to_dict())
                ps.labels = ps.labels[-(self.p.label_window * 6):]
                ps.acc.add(Label.from_dict(ps.labels[-1]))
        if event in ("followed", "opened"):
            self._set(ps, it, "acted", None, now)
        elif event == "dismissed":
            self._set(ps, it, "dismissed", None, now)
        elif event == "ignored":
            if sp.cls in (V.WAIT, V.HELPFUL, V.INFO):
                self._set(ps, it, "dismissed", None, now)              # it will not come back; a time-sensitive item stays shown for its reminder
        elif event == "never":
            if sp.cls != V.SAFETY and it.type != "approval_blocking":
                if it.subject not in ps.never_subjects:
                    ps.never_subjects.append(it.subject)
                self._set(ps, it, "suppressed" if sp.cls != V.TIME else "dismissed", "dropped_never_subject", now)
            else:
                self._set(ps, it, "dismissed", None, now)
        return label

    def _hour_of(self, ps: PersonState, now: float) -> int:
        d = ps.last_ws
        return int(d["ws"].get("local_hour", (now // 3600) % 24)) if d else int((now // 3600) % 24)

    # ------------------------------------------------------------------------------------------------ why, settings
    def why(self, item_id: str) -> dict[str, Any] | None:
        with self.lock:
            hit = self.store.find(item_id)
            if hit is None:
                return None
            ps, it = hit
            st = ps.get_settings()
            hour = self._hour_of(ps, it.shown_t or it.first_t)
            return {"id": it.id, "type": it.type, "state": it.state, "channel": it.channel, "deliver_at": it.deliver_at, "reason_code": it.reason_code,
                    "reason_text": texts.reason_text(it.reason_code), "mode": st.mode(it.type), "learned_drop": ps.acc.learned_drop(it.type, hour),
                    "count": it.count, "occurrences": it.occurrences, "dedup_key": it.dedup_key, "folded_into": it.folded_into,
                    "transitions": [{"t": t, "state": s, "reason_code": r, "reason_text": texts.reason_text(r)} for t, s, r in it.transitions],
                    "budget": {"used": ps.budget_used, "per_day": st.budget_per_day}}

    def get_settings(self, person: str) -> dict[str, Any]:
        with self.lock:
            ps = self.store.person(person)
            st = ps.get_settings()
            floors = [{"type": t, "floor": s.floor, "why": ("Safety stops are always shown once and stay visible." if s.cls == V.SAFETY else
                                                           "An approval that blocks a job always stays visible in the menu bar count.")}
                      for t, s in V.TYPES.items() if s.cls == V.SAFETY or t == "approval_blocking"]
            return {**st.to_dict(), "types": [{"type": t, "class": s.cls, "mode": st.mode(t), "fixed": s.cls == V.SAFETY} for t, s in V.TYPES.items()], "floors": floors, "learned": ps.acc.summary(), "defaults": Settings().to_dict()}

    def set_settings(self, person: str, *, modes: dict[str, str] | None = None, budget_per_day: int | None = None, level_glance: bool | None = None,
                     reset_learned: bool | list[str] | None = None) -> dict[str, Any]:
        with self.lock:
            ps = self.store.person(person)
            cur = dict(ps.settings)
            m = dict(cur.get("modes", {}))
            for t, mode in (modes or {}).items():
                if t not in V.TYPES:
                    raise EventError("invalid_setting", f"{t!r} is not a kind of notice.")
                if V.TYPES[t].cls == V.SAFETY:
                    raise EventError("safety_fixed", "Safety stops cannot be turned down.")
                if mode not in V.MODES:
                    raise EventError("invalid_setting", f"mode must be one of {', '.join(V.MODES)}.")
                if mode == "normal":
                    m.pop(t, None)
                else:
                    m[t] = mode
            cur["modes"] = m
            if budget_per_day is not None:
                if isinstance(budget_per_day, bool) or not isinstance(budget_per_day, int) or not 0 <= budget_per_day <= 40:
                    raise EventError("invalid_setting", "The budget is a whole number from 0 to 40.")
                cur["budget_per_day"] = budget_per_day
            if level_glance is not None:
                cur["level_glance"] = bool(level_glance)
            ps.settings = cur
            if reset_learned:
                types = None if reset_learned is True else [t for t in reset_learned if t in V.TYPES]
                ps.acc.reset(types)
                ps.labels = [x for x in ps.labels if types is not None and x["type"] not in types]
                if types is None:
                    ps.never_subjects = []
            self.store.save()
        return self.get_settings(person)

    def stats(self, person: str) -> dict[str, Any]:
        with self.lock:
            ps = self.store.person(person)
            return {"today": dict(ps.counters), "budget": {"used": ps.budget_used, "per_day": ps.get_settings().budget_per_day},
                    "learned": ps.acc.summary()}
