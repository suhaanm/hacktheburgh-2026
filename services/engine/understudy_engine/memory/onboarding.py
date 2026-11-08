"""Onboarding writer (ROL-4): a role pack plus five answers become the worker's starting memory file.

Everything that makes two roles look different comes from the pack: the questions and their options, the
tone defaults, the expert checklist (Procedure), the curriculum (Skill state), the risk patterns (Never).
Nothing here calls a model. The write is the worker's own action (``actor="worker"``).
"""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone
from typing import Any

from . import doc as D
from .packinfo import PackView, list_pack_ids, load_pack
from .store import MemoryStore, today_iso

DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
_PACE_WORDS = {"gentle": "slowly", "steady": "steadily", "quick": "quickly", "slow": "slowly", "medium": "steadily", "fast": "quickly"}
_DEFAULT_PERSON = "p_me"
PERSON_RE = __import__("re").compile(r"^p_[a-z0-9]{2,16}$")


def new_person_id(store: MemoryStore) -> str:
    """The engine owns the person id: stable for this install (hash of its home directory), created at first onboarding."""
    import hashlib

    return "p_" + hashlib.sha1(str(store.home.resolve()).encode()).hexdigest()[:8]


class OnboardingError(ValueError):
    code = "bad_onboarding"


class UnknownRole(OnboardingError):
    """The role id is not one of the packs. ``valid`` is the closed list, so the screen can say what is available."""
    code = "unknown_role"

    def __init__(self, role: Any) -> None:
        self.valid = list_pack_ids()
        super().__init__(f"There is no role {str(role)[:40]!r}. Choose one of: {', '.join(self.valid)}.")


class NotOnboarded(OnboardingError):
    code = "not_onboarded"


#: "leave it as it is" for the optional name (None and "" both mean "clear it")
_KEEP: Any = object()
NAME_PREFIX = "Name: "
NAME_ID = "l_name"
NAME_MAX = 60


def clean_name(value: Any) -> str:
    """The worker's own name, as one short line: letters (any script), spaces, hyphens, apostrophes and full stops. ``""`` clears it."""
    if value is None:
        return ""
    if not isinstance(value, str):
        raise OnboardingError("name must be text")
    t = re.sub(r"\s+", " ", unicodedata.normalize("NFC", value)).strip()
    if not t:
        return ""
    if len(t) > NAME_MAX:
        raise OnboardingError(f"name must be {NAME_MAX} characters or fewer")
    if unicodedata.category(t[0])[0] != "L" or any(not (unicodedata.category(c)[0] in "LM" or c in " -'’.") for c in t):
        raise OnboardingError("name can use letters, spaces, hyphens, apostrophes and full stops")
    return t


def profile_name(doc: D.MemoryDoc) -> str | None:
    """The name line in Preferences, if there is one. Deleting the line removes the name (the worker owns the file)."""
    sec = doc.section("Preferences", create=False)
    for ln in (sec.lines() if sec else []):
        if ln.text.startswith(NAME_PREFIX) and len(ln.text) > len(NAME_PREFIX):
            return ln.text[len(NAME_PREFIX):]
    return None


def questions_payload(role: str) -> dict[str, Any]:
    """GET /onboarding/questions?role= : the pack summary and the five questions, ready for the screen."""
    pack = load_pack(role)
    qs = []
    for q in pack.questions:
        out = {"id": q["id"], "prompt": q.get("prompt", ""), "kind": q.get("kind", "single")}
        if q.get("why"):
            out["why"] = q["why"]
        if q.get("options") is not None:
            out["options"] = [
                {k: o[k] for k in ("value", "label", "default") if k in o} for o in q.get("options", [])
            ]
        if q.get("kind") == "hours":
            out["default_hours"] = q.get("default_hours") or pack.presence_prior()["hours"]
        qs.append(out)
    return {"role": pack.id, "pack": pack.pack_summary(), "questions": qs}


# ----------------------------------------------------------------------------------------------
def _option_values(pack: PackView, qid: str) -> dict[str, dict[str, Any]]:
    q = pack.question(qid) or {}
    return {o["value"]: o for o in q.get("options", []) if isinstance(o, dict) and "value" in o}


def _as_list(v: Any) -> list[str]:
    if v is None:
        return []
    if isinstance(v, str):
        return [v]
    return [str(x) for x in v]


def _default_option(pack: PackView, qid: str) -> str | None:
    q = pack.question(qid) or {}
    for o in q.get("options", []):
        if o.get("default"):
            return o["value"]
    return None


def _default_options(pack: PackView, qid: str) -> list[str]:
    q = pack.question(qid) or {}
    return [o["value"] for o in q.get("options", []) if o.get("default")]


def normalise_hours(h: Any, pack: PackView) -> dict[str, Any]:
    base = (pack.question("hours") or {}).get("default_hours") or pack.presence_prior()["hours"]
    if not h:
        return {"start": base["start"], "end": base["end"], "days": list(base["days"])}
    try:
        start, end = str(h["start"]), str(h["end"])
        days = [str(d).lower()[:3] for d in (h.get("days") or base["days"])]
    except (KeyError, AttributeError, TypeError) as e:
        raise OnboardingError("hours must be {start, end, days}") from e
    for t in (start, end):
        hh, _, mm = t.partition(":")
        if not (hh.isdigit() and mm.isdigit() and 0 <= int(hh) < 24 and 0 <= int(mm) < 60 and len(mm) == 2):
            raise OnboardingError(f"bad time {t!r}, expected HH:MM")
    bad = [d for d in days if d not in DAYS]
    if bad or not days:
        raise OnboardingError(f"bad days {bad or days!r}")
    return {"start": start.zfill(5), "end": end.zfill(5), "days": [d for d in DAYS if d in days]}


def _fmt_days(days: list[str]) -> str:
    idx = sorted(DAYS.index(d) for d in days)
    if len(idx) > 2 and idx == list(range(idx[0], idx[-1] + 1)):
        return f"{DAYS[idx[0]]} to {DAYS[idx[-1]]}"
    return ", ".join(DAYS[i] for i in idx)


def checklist_layers(checks: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Layer the expert's partial order: checks in one layer may be done in either order."""
    by_id = {c["id"]: c for c in checks}
    depth: dict[str, int] = {}

    def d(cid: str, seen: tuple[str, ...] = ()) -> int:
        if cid in depth:
            return depth[cid]
        if cid in seen:  # cyclic pack data: cut the cycle rather than loop
            return 0
        deps = [a for a in by_id[cid].get("after", []) if a in by_id]
        depth[cid] = 0 if not deps else 1 + max(d(a, seen + (cid,)) for a in deps)
        return depth[cid]

    for c in checks:
        d(c["id"])
    layers: dict[int, list[dict[str, Any]]] = {}
    for c in checks:
        layers.setdefault(depth[c["id"]], []).append(c)
    return [layers[k] for k in sorted(layers)]


def _main_checks(pack: PackView) -> list[dict[str, Any]]:
    """The checks of the pack's one task. A check with a ``family`` (RD, 7 Nov 2026) belongs to another task family: optional, listed on a line of its own,
    never part of the checklist or of "Never skipped"."""
    return [c for c in pack.expert_checks if "family" not in c]


def _families(pack: PackView) -> list[str]:
    return list(dict.fromkeys(str(c["family"]) for c in pack.expert_checks if "family" in c))


def _checklist_text(pack: PackView) -> str | None:
    main = _main_checks(pack)
    if not main:
        return None
    parts = []
    for layer in checklist_layers(main):
        ids = [c["id"] for c in layer]
        parts.append(" or ".join(ids) if len(ids) > 1 else ids[0])
    return "Checklist: " + ", then ".join(parts) + "."


def build_profile(pack: PackView, answers: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalise the answers against the pack. Raises OnboardingError on a bad value."""
    answers = answers or {}
    capture = answers.get("capture", False)
    if not isinstance(capture, bool):
        raise OnboardingError("capture must be true or false")
    tools_opts, risky_opts = _option_values(pack, "tools"), _option_values(pack, "risky")
    tone_opts, pace_opts = _option_values(pack, "tone"), _option_values(pack, "pace")

    tools = _as_list(answers["tools"]) if answers.get("tools") is not None else _default_options(pack, "tools")
    risky = _as_list(answers["risky"]) if answers.get("risky") is not None else _default_options(pack, "risky")
    for name, vals, opts in (("tools", tools, tools_opts), ("risky", risky, risky_opts)):
        bad = [v for v in vals if opts and v not in opts]
        if bad:
            raise OnboardingError(f"unknown {name} option(s) for {pack.id}: {', '.join(bad)}")

    tone = answers.get("tone") or _default_option(pack, "tone") or pack.tone_defaults.get("length", "short")
    if tone_opts and tone not in tone_opts:
        raise OnboardingError(f"unknown tone {tone!r} for {pack.id}")
    pace = answers.get("pace") or _default_option(pack, "pace") or pack.tone_defaults.get("pace", "steady")
    if pace_opts and pace not in pace_opts:
        raise OnboardingError(f"unknown pace {pace!r} for {pack.id}")
    hours = normalise_hours(answers.get("hours"), pack)

    irreversible = list(dict.fromkeys(pack.risk_irreversible + [
        p for v in risky if risky_opts.get(v, {}).get("risk_class", "irreversible") == "irreversible"
        for p in (risky_opts.get(v, {}).get("patterns") or [v])
    ]))
    outward = list(dict.fromkeys(pack.risk_outward + [
        p for v in risky if risky_opts.get(v, {}).get("risk_class") == "outward"
        for p in (risky_opts.get(v, {}).get("patterns") or [v])
    ]))
    return {
        "role": pack.id,
        "answers": {"tools": tools, "risky": risky, "tone": tone, "pace": pace, "hours": hours, "capture": capture},
        "capture": capture,
        "tone": {"length": tone, "voice": pack.tone_defaults.get("voice", "plain")},
        "pace": pace,
        "hours": hours,
        "risk_classes": {"irreversible": irreversible, "outward": outward},
        "tool_labels": [tools_opts.get(t, {}).get("label", t) for t in tools],
        "risky_labels": [risky_opts.get(r, {}).get("label", r) for r in risky],
    }


CAPTURE_LINE = "Capture: times only"
CAPTURE_ID = "l_capture"
KEEP_IDS = ("l_quiet_hours", NAME_ID)           # the worker's own, whatever the role: they survive a re-run and a role change


def capture_enabled(doc: D.MemoryDoc) -> bool:
    """PR3: desk capture is on only while this line is in the Preferences section. Deleting the line turns it off."""
    sec = doc.section("Preferences", create=False)
    return any(ln.text.strip().lower().startswith("capture: times only") for ln in (sec.lines() if sec else []))


def _seed(doc: D.MemoryDoc, pack: PackView, profile: dict[str, Any], today: str, keep_skills: bool, same_role: bool = False,
          notes: dict[tuple[str, str], str] | None = None) -> None:
    """Replace the seeded sections. The worker's own Routines, Corrections and extra sections are left alone. Lines that are the worker's own whatever
    the role (quiet hours, the name) are kept and put after the seeded ones, and on a same-role re-run so are approved rules; that keeps a repeated run
    byte-for-byte the same file. ``notes`` maps (section, text) to the note an unchanged line already had, so the date on it does not move."""
    kept: dict[str, list[D.Line]] = {}
    for name in ("Preferences", "Procedure", "Never"):
        sec = doc.section(name)
        kept[name] = [i for i in sec.items if isinstance(i, D.Line) and (i.id in KEEP_IDS or (same_role and i.note.startswith("rule:")))]
        sec.items = [i for i in sec.items if not isinstance(i, D.Line)]
    skills = doc.section("Skill state")
    old_skill = {ln.text.split(":", 1)[0]: ln for ln in skills.lines()} if keep_skills else {}
    skills.items = [ln for ln in skills.lines() if ln.text.split(":", 1)[0] in old_skill]
    old_notes = notes or {}

    def add(section: str, text: str, note: str, line_id: str | None = None) -> None:
        doc.add(section, text, note=old_notes.get((section, D.clean_text(text)), note), line_id=line_id)

    tone = profile["tone"]
    add("Preferences", f"Summaries: {tone['length']}. Voice: {tone['voice']}.", f"onboarding {today}")
    add("Preferences", f"Help fades {_PACE_WORDS.get(profile['pace'], profile['pace'])}.", f"onboarding {today}")
    h = profile["hours"]
    add("Preferences", f"Usual hours: {h['start']} to {h['end']}, {_fmt_days(h['days'])}.", f"onboarding {today}")
    if profile["tool_labels"]:
        add("Preferences", "Tools: " + ", ".join(profile["tool_labels"]) + ".", f"onboarding {today}")
    if profile.get("capture"):
        add("Preferences", CAPTURE_LINE, f"you agreed {today}", CAPTURE_ID)

    checklist = _checklist_text(pack)
    if checklist:
        add("Procedure", checklist, f"from the {pack.name} pack")
    crit = [c["id"] for c in _main_checks(pack) if c.get("critical")]
    if crit:
        add("Procedure", "Never skipped: " + ", ".join(crit) + ".", f"from the {pack.name} pack")
    families = _families(pack)
    if families:
        add("Procedure", "Also, when the task needs them: " + ", ".join(families) + ".", f"from the {pack.name} pack")

    for sk in pack.skills:
        sid = str(sk["id"])
        if sid in old_skill:
            continue
        doc.add("Skill state", f"{sid}: L1, streak 0, last seen never", note=sk.get("label", ""))

    irr = profile["risk_classes"]["irreversible"]
    if irr:
        add("Never", "Run without my click: " + ", ".join(irr) + ".", "role default plus your answers")
    out = profile["risk_classes"]["outward"]
    if out:
        add("Never", "Send outward without asking: " + ", ".join(out) + ".", "role default")
    for lab in profile["risky_labels"]:
        add("Never", f"Never without me: {lab}.", f"you said so {today}")
    for name, lines in kept.items():
        sec = doc.section(name)
        have = doc.all_ids()
        sec.items.extend(ln for ln in lines if ln.id not in have)


def _carry(prev: dict[str, Any], pack: PackView, answers: dict[str, Any]) -> dict[str, Any]:
    """A role change keeps what is the worker's own and not the role's: the capture choice, usual hours, and tone or pace when the new pack offers the same
    option. The role's own questions (tools, risky) start from the new pack's defaults. Whatever the caller sends explicitly wins."""
    before = prev.get("answers") or {}
    out: dict[str, Any] = {}
    if isinstance(before.get("capture"), bool):
        out["capture"] = before["capture"]
    if before.get("hours"):
        out["hours"] = before["hours"]
    for k in ("tone", "pace"):
        opts = _option_values(pack, k)
        if before.get(k) and (not opts or before[k] in opts):
            out[k] = before[k]
    out.update(answers)
    return out


def _now_iso(now: datetime | None) -> str:
    return (now or datetime.now(timezone.utc)).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _set_name(doc: D.MemoryDoc, name: str, today: str) -> None:
    """Put the name line in Preferences (or take it out when ``name`` is empty)."""
    found = doc.find(NAME_ID)
    if not name:
        if found is not None:
            doc.remove(NAME_ID)
        return
    text = D.clean_text(NAME_PREFIX + name)
    if found is not None:
        if found[1].text != text:
            found[1].text = text
            found[1].note = f"you said so {today}"
        return
    doc.add("Preferences", text, note=f"you said so {today}", line_id=NAME_ID)


def _response(store: MemoryStore, doc: D.MemoryDoc, profile: dict[str, Any], person: str, **extra: Any) -> dict[str, Any]:
    state = store.load_state().get("profile") or {}
    out = {
        "person": person,
        "role": doc.role,
        "revision": doc.revision,
        "memory_markdown": D.render(doc),
        "risk_classes": profile["risk_classes"],
        "tone": profile["tone"],
        "pace": profile["pace"],
        "capture": capture_enabled(doc),
        "since": state.get("role_since"),
        **extra,
    }
    nm = profile_name(doc)
    if nm:
        out["name"] = nm
    return out


def onboard(store: MemoryStore, role: str, answers: dict[str, Any] | None, person: str | None = None,
            *, now=None, name: Any = _KEEP, carry: bool = False) -> dict[str, Any]:
    """POST /onboarding. Writes the memory file and the profile sidecar. Returns the response body.

    Safe to repeat and to use on an existing worker. The same request twice leaves the memory file and the sidecar exactly as they were (no new revision, no
    duplicate lines). A different role starts the new pack clean (skills at L1, no rules) but keeps the person id, the name, the quiet hours and, with
    ``carry=True``, the capture choice and usual hours; the sidecar remembers the earlier role and when it ended (``history``), nothing else about it.
    ``name``: leave out to keep it, ``""`` or None to clear it."""
    try:
        pack = load_pack(role)
    except KeyError as e:
        raise UnknownRole(role) from e
    state0 = store.load_state()
    prev = state0.get("profile") or {}
    answers = _carry(prev, pack, dict(answers or {})) if (carry and prev) else (answers or {})
    profile = build_profile(pack, answers)
    new_name = None if name is _KEEP else clean_name(name)
    today = today_iso(now)
    if person is not None and not PERSON_RE.match(str(person)):
        raise OnboardingError("person must look like p_ followed by 2 to 16 lower-case letters or digits")
    person = person or prev.get("person") or new_person_id(store)
    before = store.read()
    prev_role = prev.get("role") or (before.role if before.role != "unknown" else None)
    changed_role = bool(prev_role) and prev_role != pack.id
    stamp = _now_iso(now)

    def mutate(doc: D.MemoryDoc) -> None:
        same_role = doc.front.get("role") == pack.id
        notes = {(sec.name, ln.text): ln.note for sec in doc.sections if sec.known for ln in sec.lines()} if same_role else {}
        if not same_role:
            for sec in doc.sections:
                if sec.known:
                    sec.items = [i for i in sec.items if isinstance(i, D.Line) and i.id in KEEP_IDS]
        doc.role = pack.id
        _seed(doc, pack, profile, today, keep_skills=same_role, same_role=same_role, notes=notes)
        if new_name is not None:
            _set_name(doc, new_name, today)

    doc, _ = store.mutate("worker", mutate, idempotent=True)
    history = list(prev.get("history") or [])
    since = prev.get("role_since")
    if changed_role:
        history.append({"role": prev_role, "since": since, "until": stamp})
        since = stamp
    elif not since:
        since = stamp
    profile_state = {"person": person, **{k: profile[k] for k in ("role", "answers", "tone", "pace", "hours", "risk_classes", "capture")},
                     "role_since": since, "history": history[-20:]}
    if profile_state != prev:
        state = store.load_state()
        state["profile"] = profile_state
        store.save_state(state, actor="worker")
    return _response(store, doc, profile, person, role_changed=changed_role, previous_role=prev_role if changed_role else None)


def change_profile(store: MemoryStore, *, role: str | None = None, name: Any = _KEEP, answers: dict[str, Any] | None = None,
                   person: str | None = None, now=None) -> dict[str, Any]:
    """POST /profile: change an existing worker's role and/or name (also the first call, when a role comes with it).

    * a new role switches the pack (``onboard`` with ``carry=True``);
    * the same role again with no answers touches nothing but what was asked (a name change writes the one name line, so the worker's own edits to
      the seeded lines survive);
    * a name alone never re-seeds anything.
    Repeating a request changes nothing."""
    prev = load_profile(store)
    if role is None and name is _KEEP and not answers:
        raise OnboardingError("Nothing to change: send a role, a name, or both.")
    if not prev or not prev.get("person"):
        if role is None:
            raise NotOnboarded("Choose a role first. Nothing has been set up yet.")
        return {**onboard(store, role, answers, person, now=now, name=name), "created": True}
    if role is not None:
        try:
            load_pack(role)
        except KeyError as e:
            raise UnknownRole(role) from e
    if role is not None and (role != prev.get("role") or answers):
        return {**onboard(store, role, answers, person or prev["person"], now=now, name=name, carry=True), "created": False}
    new_name = None if name is _KEEP else clean_name(name)
    today = today_iso(now)
    if new_name is not None:
        doc, _ = store.mutate("worker", lambda d: _set_name(d, new_name, today), idempotent=True)
    else:
        doc = store.read()
    profile = {"tone": prev.get("tone") or {"length": "short", "voice": "plain"}, "pace": prev.get("pace", "steady"),
               "risk_classes": prev.get("risk_classes") or {"irreversible": [], "outward": []}}
    return {**_response(store, doc, profile, prev["person"], role_changed=False, previous_role=None), "created": False}


def profile_view(store: MemoryStore) -> dict[str, Any] | None:
    """GET /profile: who the worker is on this device, the roles they can switch to, and the roles they have had. The name is a line in the memory file
    the worker can read and delete; it is never written to a log."""
    prev = load_profile(store)
    if not prev or not prev.get("person"):
        return None
    doc = store.read()
    roles = []
    for rid in list_pack_ids():
        try:
            p = load_pack(rid)
            roles.append({"id": rid, "name": p.name, "summary": p.summary, "depth": p.depth})
        except KeyError:
            continue
    out: dict[str, Any] = {"person": prev["person"], "role": prev.get("role") or doc.role, "since": prev.get("role_since"),
                           "history": [dict(h) for h in (prev.get("history") or [])], "roles": roles}
    nm = profile_name(doc)
    if nm:
        out["name"] = nm
    return out


def load_profile(store: MemoryStore) -> dict[str, Any] | None:
    return store.load_state().get("profile")
