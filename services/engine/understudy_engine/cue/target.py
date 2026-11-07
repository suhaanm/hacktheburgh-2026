"""Where the control for a Cue step is, in a closed shape the desktop's DOM tracker can follow: ``{zone, label_hint, role_hint}`` or None.

The coach already answers "which control does this step need next" from the pack's own cog mapping (``coach.messages.target_for``).
Cue calls that helper instead of keeping a second set of rules, so a ring Cue draws and a ring the coach draws for the same step land on
the same zone. This module only narrows the coach's answer to what a Cue decision may carry:

* ``zone``: an id from the pack's mapping, matching ``ext_rect.schema.json`` (never a selector, never page text).
* ``label_hint``: the pack's own words for the control (the step label, or the pack's ``coach.target`` override), at most 80 characters.
* ``role_hint``: a role word from the helper or the pack ("button", "textbox", "select", "region"), lowercase, at most 32 characters.

``site`` and ``fallback_zones``, which the coach's answer may also carry, are left out: the first depends on what the worker has done in
this task (Cue's gate is pure and has no access to it) and the desktop reads neither from a coach target either. A step whose cog the
pack's mapping gives no zone gets None, and the cue stays text only. Nothing here comes from a model or from the screen.
"""
from __future__ import annotations

import re

from ..coach.messages import short_label, target_for
from ..coach.steps import Step
from ..cogs.mapper import Mapping

ZONE_RE = re.compile(r"[a-z][a-z0-9_]{1,30}")          # ext_rect.schema.json
ROLE_RE = re.compile(r"[a-z][a-z0-9_-]{0,31}")
LABEL_MAX = 80
DEFAULT_ROLE = "region"                                 # the coach's own word for "not a button or a text box"


def _label(text: object) -> str:
    """One line of pack text, at most ``LABEL_MAX`` characters, cut at a word boundary when it has to be cut."""
    s = re.sub(r"\s+", " ", text).strip() if isinstance(text, str) else ""
    if len(s) <= LABEL_MAX:
        return s
    return s[:LABEL_MAX].rsplit(" ", 1)[0] or s[:LABEL_MAX]


def step_target(step: Step | None, mapping: Mapping | None) -> dict | None:
    """``{zone, label_hint, role_hint}`` for ``step`` from the pack's mapping (through the coach's helper), or None when the pack has no
    usable zone for it. A zone that is not a plain id gives None; a role that is not a plain word falls back to ``region``."""
    if step is None or mapping is None or not step.cogs:
        return None
    raw = target_for(step, mapping)
    zone = raw.get("zone")
    if not isinstance(zone, str) or not ZONE_RE.fullmatch(zone):
        return None
    label = _label(raw.get("label_hint")) or _label(short_label(step.label))
    if not label:
        return None
    role = raw.get("role_hint")
    if not isinstance(role, str) or not ROLE_RE.fullmatch(role):
        role = DEFAULT_ROLE
    return {"zone": zone, "label_hint": label, "role_hint": role}
