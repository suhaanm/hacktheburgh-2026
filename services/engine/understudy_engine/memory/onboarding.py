"""Onboarding writer (ROL-4): a role pack plus five answers become the worker's starting memory file.

Everything that makes two roles look different comes from the pack: the questions and their options, the
tone defaults, the expert checklist (Procedure), the curriculum (Skill state), the risk patterns (Never).
Nothing here calls a model. The write is the worker's own action (``actor="worker"``).
"""
from __future__ import annotations

from typing import Any

from . import doc as D
from .packinfo import PackView, load_pack
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
    pass


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


def _checklist_text(pack: PackView) -> str | None:
    if not pack.expert_checks:
        return None
    parts = []
    for layer in checklist_layers(pack.expert_checks):
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
KEEP_IDS = ("l_quiet_hours",)


def capture_enabled(doc: D.MemoryDoc) -> bool:
    """PR3: desk capture is on only while this line is in the Preferences section. Deleting the line turns it off."""
    sec = doc.section("Preferences", create=False)
    return any(ln.text.strip().lower().startswith("capture: times only") for ln in (sec.lines() if sec else []))


def _seed(doc: D.MemoryDoc, pack: PackView, profile: dict[str, Any], today: str, keep_skills: bool, same_role: bool = False) -> None:
    """Replace the seeded sections. The worker's own Routines, Corrections and extra sections are left alone, and on
    a same-role re-run so are approved rules and the quiet-hours line."""
    for name in ("Preferences", "Procedure", "Never"):
        sec = doc.section(name)
        sec.items = [i for i in sec.items if not isinstance(i, D.Line)
                     or (same_role and (i.note.startswith("rule:") or i.id in KEEP_IDS))]
    skills = doc.section("Skill state")
    old_skill = {ln.text.split(":", 1)[0]: ln for ln in skills.lines()} if keep_skills else {}
    skills.items = [ln for ln in skills.lines() if ln.text.split(":", 1)[0] in old_skill]

    tone = profile["tone"]
    doc.add("Preferences", f"Summaries: {tone['length']}. Voice: {tone['voice']}.", note=f"onboarding {today}")
    doc.add("Preferences", f"Help fades {_PACE_WORDS.get(profile['pace'], profile['pace'])}.", note=f"onboarding {today}")
    h = profile["hours"]
    doc.add("Preferences", f"Usual hours: {h['start']} to {h['end']}, {_fmt_days(h['days'])}.", note=f"onboarding {today}")
    if profile["tool_labels"]:
        doc.add("Preferences", "Tools: " + ", ".join(profile["tool_labels"]) + ".", note=f"onboarding {today}")
    if profile.get("capture"):
        doc.add("Preferences", CAPTURE_LINE, note=f"you agreed {today}", line_id=CAPTURE_ID)

    checklist = _checklist_text(pack)
    if checklist:
        doc.add("Procedure", checklist, note=f"from the {pack.name} pack")
    crit = [c["id"] for c in pack.expert_checks if c.get("critical")]
    if crit:
        doc.add("Procedure", "Never skipped: " + ", ".join(crit) + ".", note=f"from the {pack.name} pack")

    for sk in pack.skills:
        sid = str(sk["id"])
        if sid in old_skill:
            continue
        doc.add("Skill state", f"{sid}: L1, streak 0, last seen never", note=sk.get("label", ""))

    irr = profile["risk_classes"]["irreversible"]
    if irr:
        doc.add("Never", "Run without my click: " + ", ".join(irr) + ".", note="role default plus your answers")
    out = profile["risk_classes"]["outward"]
    if out:
        doc.add("Never", "Send outward without asking: " + ", ".join(out) + ".", note="role default")
    for lab in profile["risky_labels"]:
        doc.add("Never", f"Never without me: {lab}.", note=f"you said so {today}")


def onboard(store: MemoryStore, role: str, answers: dict[str, Any] | None, person: str | None = None,
            *, now=None) -> dict[str, Any]:
    """POST /onboarding. Writes the memory file and the profile sidecar. Returns the response body."""
    try:
        pack = load_pack(role)
    except KeyError as e:
        raise OnboardingError(f"unknown role {role!r}") from e
    profile = build_profile(pack, answers or {})
    today = today_iso(now)
    if person is not None and not PERSON_RE.match(str(person)):
        raise OnboardingError("person must look like p_ followed by 2 to 16 lower-case letters or digits")
    person = person or (store.load_state().get("profile") or {}).get("person") or new_person_id(store)

    def mutate(doc: D.MemoryDoc) -> None:
        same_role = doc.front.get("role") == pack.id
        if not same_role:
            for sec in doc.sections:
                if sec.known:
                    sec.items = []
        doc.role = pack.id
        _seed(doc, pack, profile, today, keep_skills=same_role, same_role=same_role)

    doc, _ = store.mutate("worker", mutate)
    state = store.load_state()
    state["profile"] = {"person": person, **{k: profile[k] for k in ("role", "answers", "tone", "pace", "hours", "risk_classes", "capture")}}
    store.save_state(state, actor="worker")
    return {
        "person": person,
        "role": pack.id,
        "revision": doc.revision,
        "memory_markdown": D.render(doc),
        "risk_classes": profile["risk_classes"],
        "tone": profile["tone"],
        "pace": profile["pace"],
        "capture": capture_enabled(doc),
    }


def load_profile(store: MemoryStore) -> dict[str, Any] | None:
    return store.load_state().get("profile")
