"""Demo seed: three believable cards for the demo person, idempotently.

``seed_demo(home, data_dir)`` is called by the engine-handoff demo seed (``understudy_engine.demo``). It puts three cards in
``<data_dir>/briefing.json`` for ``p_learn01``: a practice card, the automation card for ``calc-entry-3x`` and a focus-block
card. They go through the real pipeline (judge's scoring for the explanation, verification, prepare), with two honest differences:

* the judge's minimum score is waived (a demo needs its three cards; the card says so in its ranking);
* where a live source is missing (the calendar track has not produced a suggestion for this person), the focus-block card is built
  from a stated stand-in reading with plain numbers, and its meta says ``value_source: demo stand-in``. The person is synthetic and
  the card is labelled synthetic.

Idempotent: a person who already has a seeded briefing is left alone unless ``reseed=True``. Reads use the dirs you pass (the
environment variables are set for the duration of the call and put back).
"""
from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .acceptance import AcceptanceModel, role_prior
from .candidates import Candidate, Ctx, Reading, automate_candidates, calendar_candidates, collect, practice_candidates
from .cards import iso, new_card
from .judge import rank
from .prepare import prepare
from .sources import Readers
from .store import BriefingStore
from .verify import verify_all

DEMO_PERSON = "p_learn01"
SEED_TAG = "demo_v1"
DEMO_ROUTINE = "calc-entry-3x"

#: stand-ins used only when the live source has nothing for the demo person (synthetic numbers, labelled as such)
_ROUTINE_FALLBACK = {"id": DEMO_ROUTINE, "title": "Enter the household into three calculators", "status": "proposed", "proposable": True,
                     "automatable": True, "episodes": 14, "minutes_per_week": 96.0, "hours_lo": 3.1, "hours_hi": 5.2, "confidence": 0.82,
                     "horizon_weeks": 4, "skill_gate_ok": True, "skill_cogs": ["ENTER_HOUSEHOLD"], "touches": ["GovCalc", "Quick Estimator", "EntitledTo", "case note"],
                     "never": ["submit", "submit to claimant record"], "irreversible_classes": ["submit"], "last_seen": None, "buy_after_runs": 3}
_SKILL_FALLBACK = {"id": "check-the-cliff", "label": "Probe the cliff edge on every calculator", "order": 3, "cogs": ["CHECK_CLIFF"],
                   "prerequisites": [], "expert_signal": "Re-runs each calculator with a figure nudged near a limit.",
                   "prompts": {"L1": "Is any figure close to a limit? What changes if it moves a little?", "L2": "Close to a limit anywhere?", "L3": "Probe the edge."},
                   "level": 2, "mastery": 0.45, "days_idle": 3.0, "days_until_drop": 2.0}
_CALENDAR_FALLBACK = {"id": "protect_focus_block", "template": "protect_focus_block", "can_draft": True,
                      "numbers": {"longest_focus_min": 55, "focus_blocks_90": 0, "meeting_h": 14.5, "suggested_min": 120, "gain_h": 2.5},
                      "expert_ref": {"longest_focus_min": 110, "focus_blocks_90": 4}}


@contextmanager
def _env(home: Path, data: Path) -> Iterator[None]:
    old = {k: os.environ.get(k) for k in ("UNDERSTUDY_HOME", "UNDERSTUDY_DATA_DIR")}
    os.environ["UNDERSTUDY_HOME"], os.environ["UNDERSTUDY_DATA_DIR"] = str(home), str(data)
    try:
        yield
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _first(cands: list[Candidate], kind: str) -> Candidate | None:
    return next((c for c in sorted(cands, key=lambda c: -c.value) if c.kind == kind), None)


def seed_demo(home: Path | str, data_dir: Path | str, *, person: str = DEMO_PERSON, now: datetime | None = None,
              reseed: bool = False, readers: Readers | None = None) -> dict[str, Any]:
    """Seed ``person``'s briefing. Returns ``{seeded, person, cards: [ids], kinds, note}``; ``seeded`` is False when it was already there."""
    home, data = Path(home), Path(data_dir)
    t = now or datetime.now(timezone.utc)
    store = BriefingStore(data / "briefing.json")
    st = store.person(person)
    if st.get("seed") == SEED_TAG and st.get("cards") and not reseed:
        return {"seeded": False, "person": person, "cards": [c["id"] for c in st["cards"]], "kinds": [c["kind"] for c in st["cards"]],
                "note": "already seeded; nothing changed"}
    readers = readers or Readers()
    with _env(home, data):
        ctx = Ctx(person=person, now=t, role="benefits-processor")
        now_c = collect(ctx, readers, only=("routines", "skills", "calendar"))
        def live_or_standin(kind: str, source: str, build, standin: dict[str, Any]) -> Candidate | None:
            """The live candidate if there is one; a stated stand-in only when the source cannot be read at all (otherwise the first
            re-check would drop it as stale, and an honest empty source means there is nothing to show)."""
            got = _first(now_c.candidates, kind)
            if got is not None:
                return got
            rd = now_c.readings.get(source)
            if rd is None or not rd.available:
                return _first(build(ctx, Reading([standin])), kind)
            return None

        auto = live_or_standin("automate", "routines", automate_candidates, _ROUTINE_FALLBACK)
        prac = live_or_standin("practice", "skills", practice_candidates, _SKILL_FALLBACK)
        cal = live_or_standin("focus_block", "calendar", calendar_candidates, _CALENDAR_FALLBACK)
        chosen = [c for c in (prac, auto, cal) if c is not None]
        accept = AcceptanceModel.from_labels(st.get("labels", []), role_prior("benefits-processor"))
        res = rank(chosen, p_accept=accept.p, now_ts=t.timestamp(), cap=3, min_score=0.0, max_per_kind={k: 1 for k in ("practice", "automate", "focus_block")})
        verdicts = verify_all([r.candidate for r in res.selected], now_c, ctx, in_flight=readers.in_flight)
        cards = []
        for r in res.selected:
            v = verdicts[r.candidate.id]
            cand = v.candidate or r.candidate
            ranking = {**r.explain(), "note": "Seeded for the demo; the minimum score was waived."}
            card = new_card(cand, prepare(cand), now_ts=t.timestamp(), score=r.score, ranking=ranking,
                            verdict="confirmed", verify_note=v.note, origin="synthetic")
            cards.append(card)

    def save(s: dict[str, Any]) -> None:
        s["cards"] = [c.to_dict() for c in cards]
        s["generated_at"] = iso(t)
        s["seed"] = SEED_TAG
        s["suppress"] = {}

    store.mutate(person, save)
    return {"seeded": True, "person": person, "cards": [c.id for c in cards], "kinds": [c.kind for c in cards],
            "note": f"seeded {len(cards)} cards for {person}"}
