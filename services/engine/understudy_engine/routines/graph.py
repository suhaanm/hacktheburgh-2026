"""The work graph (VIS-3, D9): routines, skills, memory and automations as nodes; links when related, combined when two routines
always run together; strength fades with disuse along the level engine's decay curve.

* **routine** nodes: size is weekly minutes, strength fades since the routine was last seen.
* **skill** nodes: one per Skill state line of the memory file; size and strength follow the skill's level, and fade with the
  skills module's forgetting curve from the line's ``last seen`` date. ``memory_line_id`` is that line.
* **memory** nodes: lines of Procedure, Corrections, Never and Preferences (rules first), capped. Deleting one edits the file.
* **automation** nodes: a routine the worker switched on, at its rung. ``memory_line_id`` is its Routines line, so deleting
  the node's line switches the routine off.

Links. ``related`` when two routines share steps (Jaccard of cogs at least 0.5) or run close together in time, or a skill
covers a routine's cogs, or a memory line names a routine. ``combined`` when two routines nearly always run within ten minutes of
each other (at least 80% of each one's runs have the other nearby) **and** their step sequences are close (alignment distance at
most 0.6): the dashboard can draw them as one. Every node has a plain ``why``.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..memory import doc as D
from ..memory.packinfo import PackView
from .finder import edit_distance
from .store import RoutineStore

TOGETHER_S = 600.0
LEVEL_MASTERY = {1: 0.2, 2: 0.4, 3: 0.65, 4: 0.85}


def fade(days: float, half_life_days: float) -> float:
    return 0.5 ** (max(0.0, days) / max(half_life_days, 1e-6))


def _iso(ts: float | None) -> str | None:
    return None if ts is None else datetime.fromtimestamp(ts, timezone.utc).isoformat().replace("+00:00", "Z")


def co_occurrence(a: list[float], b: list[float], window: float = TOGETHER_S) -> tuple[float, float]:
    """(share of a's runs with a b run within the window, share of b's runs with an a run within it)."""
    if not a or not b:
        return 0.0, 0.0
    bs, as_ = sorted(b), sorted(a)

    def near(x: float, ys: list[float]) -> bool:
        import bisect

        i = bisect.bisect_left(ys, x)
        return any(0 <= j < len(ys) and abs(ys[j] - x) <= window for j in (i - 1, i))

    return sum(near(x, bs) for x in a) / len(a), sum(near(x, as_) for x in b) / len(b)


def build_work_graph(store: RoutineStore, doc: D.MemoryDoc, pack: PackView, now: float, *, max_memory_nodes: int = 24,
                     skill_snapshot: dict[str, dict[str, Any]] | None = None, person: str | None = None) -> dict[str, Any]:
    half = float((pack.priors.get("mastery") or {}).get("decay_half_life_days", 21.0))
    nodes: list[dict[str, Any]] = []
    links: list[dict[str, Any]] = []
    raw = {r["id"]: r for r in store._load()["routines"].values() if person is None or r.get("person") == person}
    eff = {rid: store.effective(r, doc) for rid, r in raw.items()}
    routines_sec = doc.section("Routines", create=False)
    routine_lines = {ln.text.split("|")[0].strip(): ln for ln in (routines_sec.lines() if routines_sec else [])}

    # ----- routines (and their automations)
    for rid, r in eff.items():
        days = max(0.0, (now - float(r.get("last_seen") or now)) / 86400.0)
        line = routine_lines.get(rid)
        nodes.append({
            "id": f"routine:{rid}", "type": "routine", "label": r["title"], "size": round(float(r["minutes_per_week"]), 1),
            "strength": round(fade(days, half), 3), "last_seen": _iso(r.get("last_seen")),
            "why": f"Found because you did these steps {r['episodes']} times, about {r['minutes_per_week']:.0f} minutes a week. "
                   + ("It is switched off until you opt in." if r["consent"]["mode"] in ("none", "not_now", "never") else f"You switched it on ({r['consent']['mode']})."),
            "editable": True, "memory_line_id": line.id if line else None,
        })
        if r["consent"]["mode"] in ("shadow", "approval", "unattended"):
            sh = r["shadow"]
            nodes.append({
                "id": f"automation:{rid}", "type": "automation", "label": f"{r['title']} ({r['consent']['mode']}, {r['rung']})",
                "size": round(max(2.0, float(r["minutes_per_week"]) * 0.5), 1), "strength": round(fade(days, half) * (0.4 + 0.2 * "A0 A1 A2 A3".split().index(r["rung"])), 3),
                "last_seen": _iso(r.get("last_seen")),
                "why": f"You switched this on in {r['consent']['mode']} mode. Its shadow runs matched {sh['matches']} of {sh['runs']} so far; it stands at {r['rung']}.",
                "editable": True, "memory_line_id": line.id if line else None,
            })
            links.append({"a": f"routine:{rid}", "b": f"automation:{rid}", "kind": "related", "weight": 1.0})

    # ----- skills: from a tracker snapshot (learner trajectories) when given, else one per Skill state line of the memory file
    skill_cogs = {str(s["id"]): list(s.get("cogs", [])) for s in pack.skills}
    skill_label = {str(s["id"]): s.get("label", str(s["id"])) for s in pack.skills}

    def link_skill(skill_id: str, level: int) -> None:
        for rid, r in eff.items():
            if set(r.get("signature", [])) & set(skill_cogs.get(skill_id, [])):
                links.append({"a": f"skill:{skill_id}", "b": f"routine:{rid}", "kind": "related", "weight": round(0.5 + 0.1 * level, 2)})

    if skill_snapshot is not None:
        for sk in pack.skills:
            sid = str(sk["id"])
            cogs = skill_cogs[sid]
            seen = [skill_snapshot[c] for c in cogs if c in skill_snapshot]
            level = min((skill_snapshot[c]["level"] if c in skill_snapshot else 1) for c in cogs) if cogs else 1
            mastery = sum(x["mastery"] for x in seen) / len(seen) if seen else 0.15
            last = max((x["last_seen"] for x in seen if x.get("last_seen")), default=None)
            nodes.append({
                "id": f"skill:{sid}", "type": "skill", "label": skill_label[sid], "size": round(mastery * 10, 1),
                "strength": round(float(mastery), 3), "last_seen": last,
                "why": f"Your level on this skill is L{level} (mastery {mastery:.0%})"
                       + (f", last practised {last}" if last else ", not practised yet") + ". Mastery fades along the forgetting curve when you do not practise.",
                "editable": False, "memory_line_id": None,
            })
            link_skill(sid, level)
    else:
        sk_sec = doc.section("Skill state", create=False)
        for ln in (sk_sec.lines() if sk_sec else []):
            p = D.parse_skill_line(ln.text)
            if not p:
                continue
            seen = None
            if p["last_seen"]:
                try:
                    seen = datetime.fromisoformat(p["last_seen"]).replace(tzinfo=timezone.utc).timestamp()
                except ValueError:
                    seen = None
            m = LEVEL_MASTERY[p["level"]]
            try:
                from ..skills.tracing import CogMastery, decayed

                strength = decayed(CogMastery(m=m, stability_days=14.0, t=seen), now) if seen else m * 0.5
            except Exception:  # the skills module is another track's; fall back to the same shape of curve
                strength = m * fade((now - seen) / 86400.0, half) if seen else m * 0.5
            nodes.append({
                "id": f"skill:{p['skill']}", "type": "skill", "label": skill_label.get(p["skill"], p["skill"]),
                "size": round(m * 10, 1), "strength": round(float(strength), 3), "last_seen": p["last_seen"],
                "why": f"Your level on this skill is L{p['level']}"
                       + (f", last practised {p['last_seen']}" if p["last_seen"] else ", not practised yet") + ". It fades when you do not use it.",
                "editable": True, "memory_line_id": ln.id,
            })
            link_skill(p["skill"], p["level"])

    # ----- memory lines (rules and procedure first), capped
    mem_nodes = []
    order = ("Procedure", "Corrections", "Never", "Preferences")
    for name in order:
        sec = doc.section(name, create=False)
        for ln in (sec.lines() if sec else []):
            is_rule = ln.note.startswith("rule:")
            mem_nodes.append((0 if is_rule else order.index(name) + 1, name, ln))
    mem_nodes.sort(key=lambda t: t[0])
    for _, name, ln in mem_nodes[:max_memory_nodes]:
        is_rule = ln.note.startswith("rule:")
        nodes.append({
            "id": f"memory:{ln.id}", "type": "memory", "label": ln.text if len(ln.text) <= 70 else ln.text[:67] + "...",
            "size": 3.0, "strength": 1.0 if name in ("Never", "Procedure") or is_rule else 0.7, "last_seen": None,
            "why": ("A rule you approved. " if is_rule else "") + f"It is a line in your {name} section; delete it and the system stops using it.",
            "editable": True, "memory_line_id": ln.id,
        })
        for rid in eff:
            if rid in ln.text or rid in ln.note:
                links.append({"a": f"memory:{ln.id}", "b": f"routine:{rid}", "kind": "related", "weight": 0.6})

    # ----- routine <-> routine: combined when they always run together and look alike, else related
    ids = list(eff)
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            ra, rb = eff[a], eff[b]
            ta, tb = ra.get("member_t0", []), rb.get("member_t0", [])
            pa, pb = co_occurrence(ta, tb)
            dist = edit_distance(tuple(ra.get("signature", [])), tuple(rb.get("signature", [])))
            ja = set(ra.get("signature", [])) & set(rb.get("signature", []))
            jac = len(ja) / max(1, len(set(ra.get("signature", [])) | set(rb.get("signature", []))))
            if min(pa, pb) >= 0.8 and dist <= 0.6:
                links.append({"a": f"routine:{a}", "b": f"routine:{b}", "kind": "combined", "weight": round(min(pa, pb), 2)})
            elif jac >= 0.5 or max(pa, pb) >= 0.4:
                links.append({"a": f"routine:{a}", "b": f"routine:{b}", "kind": "related", "weight": round(max(jac, min(pa, pb)), 2)})
    return {"nodes": nodes, "links": links}
