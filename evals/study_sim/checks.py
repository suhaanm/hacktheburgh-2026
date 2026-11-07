"""Pure checks on a case: was the shared sandbox touched by anyone but this participant?

The state of the shared sites (``GET /__state``) is what the post-test is scored from, so activity that the participant did not cause
would silently change a score. Every count in the state is compared with what the participant's own actions can explain (an upper bound:
a failed click can only make the state smaller than the bound, never larger).
"""
from __future__ import annotations

from .observe import Executed

def counts_of(state: dict) -> dict:
    return {"calculations": len(state.get("calculations", [])), "cliff_opens": len(state.get("cliff_opens", [])), "notes": len(state.get("notes", {}))}


def contamination(state: dict, executed: list[Executed], prev: dict | None = None, saved: bool = False) -> str:
    """'' when the state is explained by the participant's own actions, else a short reason. Besides activity the participant cannot have caused,
    a state that SHRANK since the last look (``prev``: the counts then), or that lacks what the participant's own successful actions must have
    produced (every successful press of 'Check cliff edges' is logged by the sandbox; a saved draft leaves a note), means someone reset it."""
    ok = [e for e in executed if e.ok or e.kind == "click"]          # a click that errored may still have gone through
    own_calc = sum(1 for e in ok if e.kind == "click" and e.dom_id == "calculate")
    own_cliff = sum(1 for e in ok if e.kind == "click" and e.dom_id == "cliff-btn")
    own_save = sum(1 for e in ok if e.kind == "click" and e.dom_id in ("save-draft", "cn-save"))
    visited = {e.site for e in executed if e.site}
    calcs = state.get("calculations", [])
    if len(calcs) > own_calc:
        return f"{len(calcs)} calculations in the sandbox, the participant made at most {own_calc}"
    for c in calcs:
        if c.get("site") not in visited:
            return f"a calculation on site {c.get('site')} that the participant never visited"
    cliffs = state.get("cliff_opens", [])
    if len(cliffs) > own_cliff:
        return f"{len(cliffs)} cliff panels opened in the sandbox, the participant opened at most {own_cliff}"
    for o in cliffs:
        if o.get("site") not in visited:
            return f"a cliff panel opened on site {o.get('site')} that the participant never visited"
    if len(state.get("notes", {})) > own_save:
        return f"{len(state['notes'])} notes in the sandbox, the participant saved at most {own_save}"
    now = counts_of(state)
    if prev and any(now[k] < prev.get(k, 0) for k in now):
        return f"the sandbox state shrank ({prev} -> {now}): someone reset it during the case"
    own_cliff_ok = sum(1 for e in executed if e.ok and e.kind == "click" and e.dom_id == "cliff-btn")
    if len(cliffs) < own_cliff_ok:
        return f"{len(cliffs)} cliff panels logged by the sandbox but the participant opened {own_cliff_ok}: someone reset it during the case"
    if saved and not state.get("notes"):
        return "the participant saved a draft but the sandbox holds no note: someone reset it during the case"
    if state.get("submissions"):
        return "a submission to the claimant record"
    if state.get("exfil_hits"):
        return "an exfil hit (injected-variant traffic)"
    return ""
