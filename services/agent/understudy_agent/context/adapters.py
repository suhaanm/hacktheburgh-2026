"""Adapters: the few lines each model-facing owner adds to adopt the library. Pure functions; no model call, no network.

    manifest_of_parts     measure only. Any owner can record a manifest for a prompt it already builds, changing nothing else.
    computer_use_text     tier 3. One text for `ModelPort.computer_step(goal=..., screenshot=current, history=[])`: the goal and facts
                          first (stable), then task state, a rolling summary of older steps and the last K steps (all typed, built
                          by code), the refusal feedback, the frame hint, and the one-action instruction last.
    tier2_messages        tier 2. Re-orders the messages `Guard.planner_messages` already returns so the stable help text is in the
                          system message (before everything that changes) and the volatile STATE comes last. The guard's own
                          raw-text leak check still runs: this calls `guard.planner_messages` and only moves strings.

Passing `history=[]` to `computer_step` is deliberate: both providers then build the prompt from `goal` and ONE fresh screenshot and
add no history text of their own (the OpenAI provider's chained mode is used only when `history` is non-empty), so the prompt cost
is whatever this library assembled, a bounded number of tokens.
"""
from __future__ import annotations

import json
from typing import Any, Mapping, Sequence

from .frames import FramePlan
from .manifest import Manifest
from .packet import Assembled, ContextPacket, Section, Trust
from .working import WorkingMemory

TIER3_BUDGET_TOKENS = 3000
TIER2_STABLE_STATE_KEYS = ("param_meaning",)   # `params` stays in STATE: the heuristic test double and the planner both read it there


def manifest_of_parts(audience: str, parts: Sequence[tuple[str, str, bool]], *, trust: Trust = Trust.CODE, now: float = 0.0) -> Manifest:
    """A manifest for a prompt built elsewhere. `parts` are (section name, text, is_stable). Records sizes and the prefix hash
    only; the text is not kept. Every part is declared with one trust level (default code): if a prompt mixes levels, call the
    function once per level or use ContextPacket directly."""
    pk = ContextPacket(audience, now=now)
    for i, (name, text, stable) in enumerate(parts):
        pk.add(Section.of_text(name, trust, "adopter", text, stable=stable, order=i, required=True,
                               checked=(trust is Trust.UNTRUSTED)))
    return pk.assemble().manifest


def computer_use_text(goal: str, wm: WorkingMemory, plan: FramePlan | None = None, *, feedback: str = "",
                      budget_tokens: int = TIER3_BUDGET_TOKENS, now: float = 0.0, pack_lines: Sequence[str] = (),
                      with_previous: bool = False, image_profile: str = "default") -> Assembled:
    """Tier 3. `goal` is the trusted goal text including the fact-handle block. `feedback` is a code-written note about the last
    refused action (the OpenAI chained mode used to drop it). `plan` is this step's FramePlan: its hint is added and its frames are
    counted. `with_previous=False` (the default, because the frozen `ModelPort.computer_step` carries one image) counts and
    describes only the current frame; set it True only when the provider call really sends the previous thumbnail too.
    `image_profile="openai_cu"` counts a frame at the calibrated OpenAI computer-use cost (about 1860 tokens) instead of the default 1150.
    The caller sends its ORIGINAL screenshot as the `screenshot` argument (push with `passthrough=True`): the model's click
    coordinates come back in the pixel space of the image it was given."""
    pk = ContextPacket("computer_use", budget_tokens=budget_tokens, now=now)
    pk.add(Section.of_text("task_spec", Trust.CODE, "navigator.goal", "Goal: " + goal, stable=True, required=True, priority=100, order=0))
    if pack_lines:
        pk.add(Section.of_lines("pack_hints", Trust.CODE, "pack.role", pack_lines, stable=True, priority=60, order=20))
    pk.extend(wm.sections(order_base=200))
    if feedback:
        pk.add(Section.of_text("feedback", Trust.CODE, "tiers.computer_use", feedback.strip(), required=True, priority=100, order=300))
    if plan is not None:
        frames = plan.frames if with_previous else plan.frames[:1]
        hint = plan.hint if (with_previous and len(plan.frames) == 2) else plan.single_hint
        pk.add(Section.of_text("frame_hint", Trust.CODE, "context.frames", hint, priority=70, order=350))
        pk.attach_frames(frames, image_profile=image_profile)
    pk.add(Section.of_text("current_step", Trust.CODE, "tiers.computer_use", "Take exactly one action toward the goal.",
                           required=True, priority=100, order=400))
    return pk.assemble()


def split_tier2_state(state: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """(stable, volatile) halves of the tier-2 STATE dict: the meaning of each household parameter never changes within a run."""
    stable = {k: state[k] for k in TIER2_STABLE_STATE_KEYS if k in state}
    volatile = {k: v for k, v in state.items() if k not in TIER2_STABLE_STATE_KEYS}
    return stable, volatile


def tier2_messages(guard: Any, goal: str, seen: Any, *, tool_help: str, state: Mapping[str, Any], labels_block: str,
                   progress: str = "") -> list[dict[str, str]]:
    """Tier 2. `labels_block` is the already-wrapped untrusted element-label block (`wrap_untrusted(labels, source="web")`), as
    today. The result has the same two messages the pipeline produces, with `tool_help` and the stable half of STATE moved into the
    system message, and the volatile STATE and labels last in the user message."""
    stable, volatile = split_tier2_state(state)
    extra = "STATE: " + json.dumps(volatile, sort_keys=True) + "\nELEMENT LABELS (copied from the page):\n" + labels_block
    msgs = guard.planner_messages(goal, seen, history_summary=progress, extra=extra)
    msgs[0] = {"role": msgs[0]["role"], "content": msgs[0]["content"] + "\n\n" + tool_help + "\n\nFIXED FOR THIS RUN: "
               + json.dumps(stable, sort_keys=True)}
    return msgs
