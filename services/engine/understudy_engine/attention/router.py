"""The attention router (REQ-8): ONE deterministic function decides whether, where, when and how loudly the worker is told anything.

    AttentionRouter.decide(event, worker_state, history) -> Decision
    Decision = {channel, deliver_at (now | next_natural_break | on_return | digest), text_id, dedup_key, expires_at, reason_code, ...}

Pure: the same three arguments and the same ``Params`` give the same answer. No clock, no randomness, no I/O, no model, no network.
An item is decided when it arrives and again at every poll, so a held item is simply re-decided with the worker's state of the moment.
A ``Decision`` whose channel is ``log`` is a drop (the reason is still recorded and shown by ``why``).

The rules, in order (the first that fires gives the reason code):

  1  resolved or expired                      dropped, nobody is bothered (the proactive layer's staleness check, for everything)
  2  "never for this" on the subject          dropped (safety and a blocking approval cannot be hidden this way)
  3  safety                                   toast, once, at once, whatever the quiet state, mode, budget or learning; away: marked now,
                                              first thing on return; preempts the lock; no reminders. Never held, never batched.
  4  mode and learning                        the worker's setting fixes the highest rung; reactions may lower low-value types one or two
                                              rungs (never below the floor, never safety, never a blocking approval); voice needs a voice
                                              session or an ask, else it degrades to a chip
  5  passive channels                         a badge or banner is never held: it is visible at once (a wait item waits for the digest)
  6  hard quiet (dnd, screen sharing, call, meeting) / unknown worker / away / typing / deep work / not a break
                                              time and wait items are held (and counted); helpful-now items are dropped: their moment passes
  7  one voice                                another item on screen: now items are dropped, the rest are held; the worker's ask preempts
                                              only a lighter holder
  8  spacing, budget                          a new interruption needs 90 s since the last and budget left; a wait item falls to the digest
  9  deliver

Cue stays the authority on whether Cue speaks: the router can only silence or delay a cue, never cause one.

The kill state, the Stop all pill, the acting dot and the glance ring are STATE drawn by their owners. They are not events, they do
not pass through here, and nothing in this module can delay them. ``kill_engaged`` is only the one-time notice and the count.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from . import texts
from . import vocab as V
from .events import Event, Item
from .state import DEFAULT, History, Params, WorkerState

PRIORITY = {V.SAFETY: 3, V.TIME: 2, V.HELPFUL: 1, V.WAIT: 1, V.INFO: 0}


@dataclass(frozen=True)
class Decision:
    channel: str
    deliver_at: str
    text_id: str
    dedup_key: str
    expires_at: float
    reason_code: str
    badge: bool                  # counts in the passive tray badge while the item is open
    priority: int
    owner: str                   # the one-voice lock owner while it is on screen
    preempt: bool = False
    display_s: float = 0.0
    ladder_drop: int = 0

    @property
    def drop(self) -> bool:
        return self.channel == V.LOG

    @property
    def interrupting(self) -> bool:
        return self.channel in V.INTERRUPTING

    def to_dict(self) -> dict[str, Any]:
        return {"channel": self.channel, "deliver_at": self.deliver_at, "text_id": self.text_id, "dedup_key": self.dedup_key,
                "expires_at": self.expires_at, "reason_code": self.reason_code, "badge": self.badge, "priority": self.priority,
                "preempt": self.preempt, "display_s": self.display_s}


def is_natural_break(ws: WorkerState, p: Params = DEFAULT) -> bool:
    """The first of: the dashboard has focus; just back from an absence (or the first activity of the day); quiet 3 s soon after a task
    ended; quiet 15 s with no task in progress; quiet 90 s while a task is in progress. Never while typing, away, locked or unknown.
    A long run of focused work is not a break until the worker has been quiet for the mid-task length."""
    if not ws.known or ws.absent or ws.typing_burst:
        return False
    if ws.dashboard_focused:
        return True
    if ws.returned_s is not None and ws.returned_s <= p.return_window_s:
        return True
    if ws.deep_work and ws.quiet_s < p.break_midtask_quiet_s:
        return False
    if ws.task_in_progress:
        return ws.quiet_s >= p.break_midtask_quiet_s
    if ws.task_marker_s is not None and ws.task_marker_s <= p.break_after_task_window_s and ws.quiet_s >= p.break_after_task_quiet_s:
        return True
    return ws.quiet_s >= p.break_idle_quiet_s


class AttentionRouter:
    def __init__(self, params: Params = DEFAULT) -> None:
        self.p = params

    # ---------------------------------------------------------------------------------------------- the decision
    def decide(self, event: Event | Item, ws: WorkerState, hist: History) -> Decision:
        it = event if isinstance(event, Item) else Item.from_event(event, "-", ws.now)
        return self._decide(it, ws, hist, reminder=False)

    def reminder(self, it: Item, ws: WorkerState, hist: History) -> Decision | None:
        """The ONE gentle reminder of a time-sensitive item, or None. Only for an item that was shown and not reacted to, after the
        stated interval (20 minutes; 10 when loud; never when quiet or digest), at a natural break under the same quiet rules, at most
        once (``max_reminders`` is a constant). After it: nothing, ever; the passive badge stays until the item is resolved."""
        p = self.p
        sp = it.spec
        if not sp.reminders or it.reminders >= p.max_reminders or not it.interrupted or it.state != "shown" or it.shown_t is None:
            return None
        after = p.reminder_after(hist.settings.mode(it.type))
        if after is None or ws.now - it.shown_t < after or ws.now >= it.expires_at:
            return None
        if it.type == "calendar_deadline" and it.expires_at - ws.now < p.deadline_reminder_min_s:
            return None
        probe = replace(it, state="held", first_t=ws.now, asked=False)          # a fresh hold: it waits for a natural break
        d = self._decide(probe, ws, hist, reminder=True)
        return d if d.channel == V.TOAST and d.deliver_at == V.NOW else None

    # ---------------------------------------------------------------------------------------------- the rules
    def _decide(self, it: Item, ws: WorkerState, hist: History, *, reminder: bool) -> Decision:
        p = self.p
        sp = it.spec
        cls = sp.cls
        now = ws.now
        asked = bool(it.asked and cls == V.HELPFUL)
        pri = max(PRIORITY[cls], 2) if asked else PRIORITY[cls]
        owner = "asked" if asked else V.LOCK_OWNER[cls]
        digest_kind = it.payload.get("kind") if it.type == "attention_digest" else None
        tid = texts.text_id_for(it.type, digest_kind=digest_kind, reminder=reminder)

        def out(channel: str, deliver: str, reason: str, *, badge: bool | None = None, preempt: bool = False, drop: int = 0) -> Decision:
            disp = min(V.DISPLAY_S.get(channel, 0.0), max(1.0, it.expires_at - now)) if channel in V.INTERRUPTING else 0.0
            return Decision(channel, deliver, tid, it.dedup_key, it.expires_at, reason, sp.needs_you if badge is None else badge, pri, owner,
                            preempt, disp, drop)

        # 1. resolved or expired
        if it.op == "resolve" or it.state == "resolved":
            return out(V.LOG, V.NOW, "dropped_resolved", badge=False)
        if now >= it.expires_at:
            return out(V.LOG, V.NOW, "dropped_expired", badge=False)
        # 2. never for this (a safety item and a blocking approval cannot be hidden by a subject-level never)
        if cls != V.SAFETY and it.type != "approval_blocking" and it.subject in hist.never_subjects:
            return out(V.LOG, V.NOW, "dropped_never_subject", badge=False)
        if it.type == "help_level_changed" and (not hist.settings.level_glance or hist.level_glance_env_off):
            return out(V.LOG, V.NOW, "dropped_mode", badge=False)

        # 3. safety: never suppressed, never batched, one toast; no mode, budget or learning applies
        if cls == V.SAFETY:
            lk = hist.lock if hist.lock is not None and hist.lock.until > now else None
            if ws.known and ws.absent:
                return out(V.TOAST, V.RETURN, "safety_on_return", badge=True)
            if lk is not None and lk.owner == "safety" and lk.family_key != it.dedup_key:
                return out(V.TOAST, V.BREAK, "held_lock", badge=True)           # another safety notice is on screen: seconds, not suppression
            return out(V.TOAST, V.NOW, "shown_safety", badge=True, preempt=True)

        # 4. mode and learning fix the channel
        mode = "normal" if asked else hist.settings.mode(it.type)
        chan0, deliver0 = sp.modes[mode]
        if it.type == "attention_digest":
            if digest_kind == "rollup":
                if chan0 == V.TOAST:
                    deliver0 = V.BREAK                    # the worker asked for toasts for these types: they get ONE, at a break
            elif chan0 == V.TOAST and it.needs_you_n <= 0:
                chan0, deliver0 = V.BANNER, V.NOW         # a morning or welcome-back summary is a toast only when something needs the worker
        ladder = list(sp.ladder)
        idx = ladder.index(chan0) if chan0 in ladder else 0
        if chan0 == V.VOICE and not (ws.voice_session or it.asked):
            idx += 1                                                  # voice never starts on its own: a chip instead
        learnable = cls in (V.HELPFUL, V.WAIT) and it.type not in ("approval_blocking", "attention_digest") and not asked
        drop = hist.learned_drop(it.type, ws.local_hour) if learnable else 0            # reactions can only quieten, and not these
        idx2 = min(len(ladder) - 1, idx + drop)
        chan = ladder[idx2]
        if V.RANK[chan] < V.RANK[sp.floor]:
            chan = sp.floor
        moved = chan != chan0
        deliver = deliver0 if not moved else V.deliver_for(sp, chan, deliver0)
        normal_chan = sp.modes["normal"][0]

        # 5. passive channels are visible at once and are never held by a quiet state
        if chan == V.LOG:
            code = "dropped_learned" if drop > 0 and chan0 != V.LOG else ("dropped_mode" if normal_chan != V.LOG else "log_only")
            return out(V.LOG, V.NOW, code, badge=False, drop=drop)
        if chan in V.PASSIVE:
            if moved and drop > 0:
                code = "passive_learned"
            elif chan0 != normal_chan:
                code = "passive_mode"
            else:
                code = "passive_digest" if deliver == V.DIGEST else ("passive_badge" if chan == V.BADGE else "passive_banner")
            return out(chan, deliver, code, drop=drop)

        # ---- interrupting from here on: a chip, a toast, a question card or a voice line
        passive = V.BADGE if V.RANK[sp.floor] == V.RANK[V.BADGE] else V.BANNER
        hq = ws.hard_quiet()
        absent = ws.known and ws.absent
        if not asked:
            # 6a. hard quiet: the worker (or their calendar, a call, a screen share) said not now
            if hq is not None:
                if cls in (V.HELPFUL, V.INFO):
                    return out(V.LOG, V.NOW, f"dropped_{hq}", badge=False, drop=drop)
                return out(chan, V.BREAK, f"held_{hq}", drop=drop)
            # 6b. a worker we cannot read is held, never interrupted
            if not ws.known:
                if cls in (V.HELPFUL, V.INFO):
                    return out(V.LOG, V.NOW, "dropped_state_unknown", badge=False, drop=drop)
                return out(chan, V.BREAK, "held_state_unknown", drop=drop)
            # 6c. away or locked: nobody to tell. Time items are waiting on return; wait items fold into the digest; helpful-now moments pass
            if absent:
                if cls in (V.HELPFUL, V.INFO):
                    return out(V.LOG, V.NOW, "dropped_away", badge=False, drop=drop)
                if cls == V.TIME or it.type == "attention_digest":
                    return out(chan, V.RETURN, "held_away", drop=drop)
                return out(passive, V.DIGEST, "held_away", drop=drop)
            # 6d. flow
            if cls in (V.HELPFUL, V.INFO):
                if ws.typing_burst or ws.quiet_s < p.flow_quiet_s:
                    return out(V.LOG, V.NOW, "dropped_flow", badge=False, drop=drop)
            else:
                capped = cls == V.TIME and now - it.first_t >= p.max_hold_soft_s and not ws.typing_burst and ws.quiet_s >= p.flow_quiet_s
                if not capped:
                    if ws.typing_burst:
                        return out(chan, V.BREAK, "held_typing", drop=drop)
                    if ws.deep_work and not is_natural_break(ws, p):
                        return out(chan, V.BREAK, "held_deep_work", drop=drop)
                    if not is_natural_break(ws, p):
                        return out(chan, V.BREAK, "held_not_a_break", drop=drop)

        # 7. one voice at a time
        lk = hist.lock if hist.lock is not None and hist.lock.until > now else None
        continuation = lk is not None and lk.family_key == it.dedup_key
        preempt = False
        if lk is not None and not continuation:
            if asked and lk.owner in V.PREEMPTS["asked"]:
                preempt = True
            elif cls in (V.HELPFUL, V.INFO):
                return out(V.LOG, V.NOW, "dropped_lock", badge=False, drop=drop)
            else:
                return out(chan, V.BREAK, "held_lock", drop=drop)

        # 8. spacing and the daily budget (helpful-now and can-wait; time and safety have their own caps; the digest is the overflow's home)
        if not asked and not continuation and cls in (V.HELPFUL, V.WAIT) and it.type != "attention_digest":
            last = hist.last_interruption_t
            if last is not None and now - last < p.min_gap_s:
                if cls == V.HELPFUL:
                    return out(V.LOG, V.NOW, "dropped_spacing", badge=False, drop=drop)
                return out(chan, V.BREAK, "held_spacing", drop=drop)
            mult = p.loud_budget_mult if mode == "loud" else (p.quiet_budget_mult if mode == "quiet" else 1.0)
            if hist.budget_used >= hist.settings.budget_per_day * mult:
                if cls == V.HELPFUL:
                    return out(V.LOG, V.NOW, "dropped_budget", badge=False, drop=drop)
                return out(passive, V.DIGEST, "passive_budget", drop=drop)
            if cls == V.WAIT and chan == V.TOAST and hist.wait_toasts >= p.wait_toasts_per_day:
                return out(passive, V.DIGEST, "passive_budget", drop=drop)
        if it.type == "help_level_changed":
            recent = [t for t in hist.level_glances if now - t < 3600.0]
            if len(recent) >= p.level_glance_per_hour:
                return out(V.LOG, V.NOW, "dropped_budget", badge=False, drop=drop)

        # 9. deliver
        if reminder:
            code = "shown_reminder"
        elif it.type == "attention_digest":
            code = "shown_digest"
        elif asked:
            code = "shown_asked"
        elif deliver0 in (V.BREAK, V.RETURN):
            code = "shown_break"
        else:
            code = "shown_now"
        return out(chan, V.NOW, code, preempt=preempt, drop=drop)
