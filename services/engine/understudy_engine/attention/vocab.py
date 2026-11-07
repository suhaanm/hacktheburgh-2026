"""The closed vocabularies of the attention layer (REQ-8): channels, classes, event types and what each type does in each mode.

Everything here is data: the router reads it, the tests lint it, the schema mirrors it. Nothing is generated at run time.

Channels, loudest last (a rung is the index in ``CHANNELS``): ``log`` (silent), ``badge`` (tray count, passive), ``banner`` (dashboard,
passive, seen on return), ``chip`` (in context: a Cue ring or chip), ``toast`` (compact, top right), ``question_card`` (needs a
decision), ``voice``. Only ``chip`` and above interrupt. There is no phone channel: nothing is ever pushed off the machine.

Markers are not event types and are not here on purpose: the kill state, the Stop all pill, the acting dot and the glance ring are
STATE drawn by their owners (the desktop kill switch and HUD). This layer never delays them and has no way to: ``kill_engaged`` below
is only the one-time "everything is stopped" notice and the count that mirrors the state; the state itself does not wait for it.
"""
from __future__ import annotations

from dataclasses import dataclass, field

LOG, BADGE, BANNER, CHIP, TOAST, QUESTION, VOICE = "log", "badge", "banner", "chip", "toast", "question_card", "voice"
CHANNELS = (LOG, BADGE, BANNER, CHIP, TOAST, QUESTION, VOICE)
RANK = {c: i for i, c in enumerate(CHANNELS)}
PASSIVE = frozenset({LOG, BADGE, BANNER})
INTERRUPTING = frozenset({CHIP, TOAST, QUESTION, VOICE})

NOW, BREAK, RETURN, DIGEST = "now", "next_natural_break", "on_return", "digest"
DELIVER_AT = (NOW, BREAK, RETURN, DIGEST)

MODES = ("loud", "normal", "quiet", "digest")
CLASSES = ("safety", "time", "now", "wait", "info")
SAFETY, TIME, HELPFUL, WAIT, INFO = CLASSES

# The notification life of an item. ``dismissed`` and ``acted`` are reactions to what was shown; the item itself stays counted until the
# producer resolves it or it expires (an approval the worker closed a toast for is still an approval).
STATES = ("held", "shown", "reminded", "dismissed", "acted", "expired", "resolved", "suppressed", "digested")
TERMINAL = frozenset({"expired", "resolved", "suppressed", "digested"})

FEEDBACK_EVENTS = ("shown", "followed", "dismissed", "ignored", "never", "opened", "deferred")
LABELS = ("followed", "dismissed_fast", "dismissed", "ignored", "never")        # implicit labels (Pupil's idea): see learning.py
RISK_CLASSES = ("irreversible", "outward", "normal")
OUTCOMES = ("done", "failed", "paused", "yielded", "stopped")
RUN_MODES = ("overnight", "background", "foreground")
SERVICES = ("engine", "agent", "model", "calendar")
OPS = ("raise", "resolve")
ORIGINS = ("real", "synthetic")
DIGEST_KINDS = ("morning", "return", "rollup", "now")

# What the router may say a source is called in a notification (a fixed set; see texts.py).
SOURCES = ("Understudy", "Your agent run", "Your overnight run", "Your background run", "Approval queue", "Briefing", "Your calendar", "Cue")

SubjectPattern = r"^[a-z0-9][a-z0-9_.:-]{0,63}$"
PersonPattern = r"^p_[a-z0-9_]{1,30}$"


def _m(loud, normal, quiet, digest) -> dict[str, tuple[str, str]]:
    return {"loud": loud, "normal": normal, "quiet": quiet, "digest": digest}


@dataclass(frozen=True)
class TypeSpec:
    id: str
    cls: str
    family: str
    needs_you: bool                      # counts in the tray badge while open
    ttl_s: float                         # default and maximum relevance
    modes: dict[str, tuple[str, str]]    # mode -> (channel, deliver_at) at the START of the ladder
    ladder: tuple[str, ...]              # allowed channels, loudest first; a learned drop walks down it
    floor: str                           # the quietest channel the type may ever reach
    reminders: bool = False              # time-sensitive items get at most ONE reminder (loud and normal modes)
    passthrough: bool = False            # the text belongs to the producer (a pack label): this layer admits, never words it
    notes: str = field(default="", compare=False)


_S = (TOAST, NOW)
_NB = (TOAST, BREAK)

TYPES: dict[str, TypeSpec] = {t.id: t for t in (
    # ---- safety-critical: never suppressed, never batched, one toast then a marker; no mode, budget or learning can lower them
    TypeSpec("kill_engaged", SAFETY, "kill", True, 86400, _m(_S, _S, _S, _S), (TOAST,), TOAST, notes="the one-time notice; the stopped state itself is a marker"),
    TypeSpec("injection_pause", SAFETY, "run", True, 604800, _m(_S, _S, _S, _S), (TOAST,), TOAST),
    TypeSpec("irreversible_decision", SAFETY, "run", True, 172800, _m(_S, _S, _S, _S), (TOAST,), TOAST),
    # ---- time-sensitive: badge from birth, one toast, ONE reminder, then nothing
    TypeSpec("run_blocked_target", TIME, "run", True, 1800, _m(_NB, _NB, (BADGE, NOW), (BADGE, NOW)), (TOAST, BADGE), BADGE, reminders=True),
    TypeSpec("run_blocked_error", TIME, "run", True, 1800, _m(_NB, _NB, (BADGE, NOW), (BADGE, NOW)), (TOAST, BADGE), BADGE, reminders=True),
    TypeSpec("approval_blocking", TIME, "approval", True, 86400, _m(_NB, _NB, _NB, (BADGE, NOW)), (TOAST, BADGE), BADGE, reminders=True),
    TypeSpec("calendar_deadline", TIME, "deadline", True, 86400, _m(_NB, _NB, _NB, (BADGE, NOW)), (TOAST, BADGE), BADGE, reminders=True),
    # ---- helpful-now: Cue's own gate decides whether Cue speaks; the router can only silence or delay (a cue's moment is seconds)
    TypeSpec("cue_cue", HELPFUL, "cue", False, 20, _m((CHIP, NOW), (CHIP, NOW), (CHIP, NOW), (LOG, NOW)), (CHIP, LOG), LOG, passthrough=True),
    TypeSpec("cue_ask", HELPFUL, "cue", False, 20, _m((QUESTION, NOW), (QUESTION, NOW), (LOG, NOW), (LOG, NOW)), (QUESTION, LOG), LOG, passthrough=True),
    TypeSpec("cue_offer", HELPFUL, "cue", False, 20, _m((CHIP, NOW), (CHIP, NOW), (LOG, NOW), (LOG, NOW)), (CHIP, LOG), LOG, passthrough=True),
    TypeSpec("voice_line", HELPFUL, "cue", False, 15, _m((VOICE, NOW), (VOICE, NOW), (LOG, NOW), (LOG, NOW)), (VOICE, CHIP, LOG), LOG, passthrough=True,
             notes="voice only when asked or a voice session is already open; otherwise it degrades to a chip"),
    # ---- informational: silent log, except the 2 s level glance (the owner's "help fades" interaction)
    TypeSpec("kill_cleared", INFO, "kill", False, 60, _m((LOG, NOW), (LOG, NOW), (LOG, NOW), (LOG, NOW)), (LOG,), LOG),
    TypeSpec("help_level_changed", INFO, "level", False, 60, _m((CHIP, NOW), (CHIP, NOW), (LOG, NOW), (LOG, NOW)), (CHIP, LOG), LOG, passthrough=True,
             notes="the 2 s glance; settings.level_glance=false or UNDERSTUDY_ATTENTION_LEVEL_GLANCE=0 turns it off entirely"),
    # ---- can-wait: held for the next natural break, or folded into one digest
    TypeSpec("routine_proposal", WAIT, "proposal", False, 259200, _m(_NB, _NB, (BANNER, DIGEST), (BANNER, DIGEST)), (TOAST, BANNER, LOG), LOG),
    TypeSpec("briefing_ready", WAIT, "briefing", False, 259200, _m(_NB, (BANNER, DIGEST), (BANNER, DIGEST), (BANNER, DIGEST)), (TOAST, BANNER, LOG), LOG),
    TypeSpec("approval_waiting", WAIT, "approval", True, 86400, _m(_NB, (BADGE, DIGEST), (BADGE, DIGEST), (BADGE, DIGEST)), (TOAST, BADGE), BADGE),
    TypeSpec("run_finished", WAIT, "run", False, 86400, _m(_NB, (BANNER, DIGEST), (BANNER, DIGEST), (BANNER, DIGEST)), (TOAST, BANNER, LOG), LOG),
    TypeSpec("morning_report", WAIT, "report", False, 86400, _m(_NB, (BANNER, DIGEST), (BANNER, DIGEST), (BANNER, DIGEST)), (TOAST, BANNER, LOG), LOG),
    TypeSpec("service_degraded", WAIT, "service", False, 86400, _m((BANNER, NOW), (BANNER, NOW), (BANNER, NOW), (BANNER, NOW)), (BANNER,), BANNER,
             notes="passive: a banner on the dashboard, never an interruption"),
    TypeSpec("attention_digest", WAIT, "digest", False, 43200, _m((TOAST, RETURN), (TOAST, RETURN), (BANNER, NOW), (BANNER, NOW)), (TOAST, BANNER), BANNER,
             notes="built by the router; a toast only when it lists something that needs the worker, else a banner"),
)}
EVENT_TYPES = tuple(TYPES)

# Producers may submit these; the router builds ``attention_digest`` itself.
SUBMITTABLE = tuple(t for t in EVENT_TYPES if t != "attention_digest")

# Same story, different type: a newer item in the same family and subject replaces an older unseen one.
FAMILIES = tuple(sorted({t.family for t in TYPES.values()}))

# Urgency order, for digest ordering and for who goes first when several are deliverable at once.
CLASS_ORDER = {SAFETY: 0, TIME: 1, HELPFUL: 2, WAIT: 3, INFO: 4}

# Lock owners: the one-voice lock is held by whatever is on screen. Only safety preempts, plus a worker's own ask over lighter holders.
LOCK_OWNER = {SAFETY: "safety", TIME: "decision", HELPFUL: "cue", WAIT: "notice", INFO: "glance"}
PREEMPTS = {"safety": frozenset({"decision", "asked", "cue", "notice", "glance"}), "asked": frozenset({"cue", "notice", "glance"})}

# How long an interrupting item holds the lock (and stays on screen) when the producer gave none, seconds.
DISPLAY_S = {CHIP: 12.0, TOAST: 20.0, QUESTION: 12.0, VOICE: 10.0}


def spec(type_id: str) -> TypeSpec:
    return TYPES[type_id]


def deliver_for(sp: TypeSpec, channel: str, base_deliver: str) -> str:
    """The delivery moment of an item at ``channel`` (a learned drop or a mode may have moved it off its table channel).

    An interrupting channel keeps the table's moment. A passive one is visible at once (a count or a banner), except that a can-wait
    item waits for the digest, which is how it folds into one summary instead of N pings."""
    if channel in INTERRUPTING:
        return base_deliver
    if channel != LOG and sp.cls == WAIT and sp.id not in ("service_degraded", "attention_digest"):
        return DIGEST
    return NOW
