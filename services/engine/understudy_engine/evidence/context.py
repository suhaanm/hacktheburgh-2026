"""Context budget and prompt order for the explainer (REQ-8): what the model is shown, how big it may be, and what goes first.

**Order (cache-friendly).** The prompt is a fixed system section (``explain.INSTRUCTIONS`` or ``explain.REWORD_INSTRUCTIONS``: constants,
nothing per request) followed by one user message whose parts run from the most stable to the least: the packet's numeric ``fields``
(sorted by path), its enum ``labels``, the habit ``names``, then the coach ``menu`` (the status, source and age of each block are in
``labels`` and ``fields`` under ``block.*``), then the ``intent``, a number the worker typed (``asked``), and last (local reword mode)
the code-written ``draft``. A server that caches the prompt prefix (llama.cpp
does, ``cache_prompt``) re-reads only the tail when the same case is asked a second question.

**Budget.** ``PROMPT_TOKEN_BUDGET`` (2500) tokens for the whole prompt (system plus user message), estimated at ``CHARS_PER_TOKEN`` (3.1)
characters per token, calibrated against the ``prompt_tokens`` the real local model reported (3.2 to 3.3 characters per token on 12
prompts). The largest case in the synthetic cohort (the routine question with two routines) estimates at about 2400 tokens and the
typical one at about 1900, so no packet in the cohort is trimmed; measured prompts were 1280 to 1610 tokens. When the prompt is over budget the packet is trimmed by ``trim``, in a fixed order, lowest priority first. What is
dropped is dropped from the packet itself, before the request is built, so the model, the check and the template all see the same
smaller packet: a sentence can never cite a number the model was not shown, and the response lists what was dropped.

Drop order (each step is skipped for the intents named, which need what it removes; it stops as soon as the prompt fits):

    1. cogs                          (no sentence template cites a cog)
    2. gap.null_lo, gap.null_hi      (shuffled-label control; kept for how_sure)
    3. hazard intervals              (p_lo, p_hi, fa_lo, fa_hi; kept for stuck_reading, how_sure)
    4. progress                      (time to progress; kept for stuck_reading)
    5. cohort habits below the top 3 (by seconds)
    6. habits below the top 4        (by absolute seconds)
    7. routines below the top 2      (by minutes a week)
    8. consequences                  (kept for how_sure, where_time_went)
    9. hazard scores                 (log losses, ece, bins; kept for how_sure, stuck_reading)

Never dropped: ``meta``, the case and cohort gap and the placebo control, the top habits, the coach decision, the hazard readings and
threshold, ``blocks`` and ``limitations``. If the prompt is still over budget after step 10 it is sent as it is and the response says so.
"""
from __future__ import annotations

import json
import math
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from . import menu as M
from . import vocab as V
from .packet import EvidencePacket, ExplainRequest, FactTable, Question, facts, finalise

PROMPT_TOKEN_BUDGET = 2500      # about 30% of the local model's 8192-token context; the reply gets up to 700 more (explain.MAX_TOKENS_LOCAL)
CHARS_PER_TOKEN = 3.1           # measured on the real local model (Qwen2.5-7B, 12 prompts of 1279 to 1610 tokens): 3.19 to 3.30 characters per
                                # token including the chat template, so 3.1 over-estimates a little, which is the safe side


def estimate_tokens(text: str) -> int:
    return math.ceil(len(text) / CHARS_PER_TOKEN)


def user_message(req: ExplainRequest, tab: FactTable, draft: list[dict[str, Any]] | None = None) -> str:
    """The user message for the local model, parts ordered from most to least stable (see the module doc). Never the worker's words."""
    body: dict[str, Any] = {
        "fields": {p: f.value for p, f in sorted(tab.facts.items()) if not p.startswith("question.")},
        "labels": {p: v for p, v in sorted(tab.labels.items()) if not p.startswith("question.")},
        "names": {h: V.HABIT_NAME[h] for h in sorted(set(tab.habits) | set(tab.cohort_habits))},
        "menu": list(req.menu),
        "intent": req.question.intent,
    }
    asked = {p: f.value for p, f in tab.facts.items() if p.startswith("question.")}
    if asked:                                   # a number the worker typed varies per question, so it sits after the stable part
        body["asked"] = {**asked, "matches_case": req.question.matches_case}
    if draft is not None:
        body["draft"] = draft
    return json.dumps(body, separators=(",", ":"))


def prompt_tokens(req: ExplainRequest, tab: FactTable, system: str, draft: list[dict[str, Any]] | None = None) -> int:
    return estimate_tokens(system) + estimate_tokens(user_message(req, tab, draft))


# ------------------------------------------------------------------------------------------------ trimming
def _drop_cogs(pk: EvidencePacket) -> EvidencePacket | None:
    return pk.model_copy(update={"cogs": {}}) if pk.cogs else None


def _drop_null(pk: EvidencePacket) -> EvidencePacket | None:
    if pk.gap is None or (pk.gap.null_lo is None and pk.gap.null_hi is None):
        return None
    return pk.model_copy(update={"gap": pk.gap.model_copy(update={"null_lo": None, "null_hi": None})})


def _drop_hazard_intervals(pk: EvidencePacket) -> EvidencePacket | None:
    h = pk.hazard
    if h is None or all(getattr(h, f) is None for f in ("p_lo", "p_hi", "fa_lo", "fa_hi")):
        return None
    return pk.model_copy(update={"hazard": h.model_copy(update={"p_lo": None, "p_hi": None, "fa_lo": None, "fa_hi": None})})


def _drop_progress(pk: EvidencePacket) -> EvidencePacket | None:
    return pk.model_copy(update={"progress": None}) if pk.progress else None


def _keep_top(d: dict[str, Any], k: int, key: Callable[[Any], float]) -> dict[str, Any] | None:
    if len(d) <= k:
        return None
    return dict(sorted(d.items(), key=lambda kv: -key(kv[1]))[:k])


def _drop_cohort_habits(pk: EvidencePacket) -> EvidencePacket | None:
    kept = _keep_top(pk.cohort_habits, 3, lambda h: h.seconds)
    return pk.model_copy(update={"cohort_habits": kept}) if kept is not None else None


def _drop_habits(pk: EvidencePacket) -> EvidencePacket | None:
    kept = _keep_top(pk.habits, 4, lambda h: abs(h.seconds))
    return pk.model_copy(update={"habits": kept}) if kept is not None else None


def _drop_routines(pk: EvidencePacket) -> EvidencePacket | None:
    kept = _keep_top(pk.routines, 2, lambda r: r.minutes_per_week or 0.0)
    return pk.model_copy(update={"routines": kept}) if kept is not None else None


def _drop_consequences(pk: EvidencePacket) -> EvidencePacket | None:
    return pk.model_copy(update={"consequences": {}}) if pk.consequences else None


def _drop_hazard_scores(pk: EvidencePacket) -> EvidencePacket | None:
    h = pk.hazard
    if h is None or all(getattr(h, f) is None for f in ("model_log_loss", "baseline_log_loss", "ece", "n_bins")):
        return None
    return pk.model_copy(update={"hazard": h.model_copy(update={"model_log_loss": None, "baseline_log_loss": None, "ece": None, "n_bins": None})})


@dataclass(frozen=True)
class Step:
    name: str
    keep_for: frozenset[str]
    fn: Callable[[EvidencePacket], EvidencePacket | None]


DROP_ORDER: tuple[Step, ...] = (
    Step("cogs", frozenset(), _drop_cogs),
    Step("gap.null_lo,gap.null_hi", frozenset({"how_sure"}), _drop_null),
    Step("hazard.p_lo,p_hi,fa_lo,fa_hi", frozenset({"stuck_reading", "how_sure"}), _drop_hazard_intervals),
    Step("progress", frozenset({"stuck_reading"}), _drop_progress),
    Step("cohort_habits below top 3", frozenset(), _drop_cohort_habits),
    Step("habits below top 4", frozenset(), _drop_habits),
    Step("routines below top 2", frozenset(), _drop_routines),
    Step("consequences", frozenset({"how_sure", "where_time_went"}), _drop_consequences),
    Step("hazard.scores", frozenset({"how_sure", "stuck_reading"}), _drop_hazard_scores),
)


@dataclass
class Trimmed:
    packet: EvidencePacket
    dropped: list[str] = field(default_factory=list)
    tokens: int = 0
    budget: int = PROMPT_TOKEN_BUDGET
    over_budget: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {"tokens_est": self.tokens, "budget": self.budget, "dropped": list(self.dropped), "over_budget": self.over_budget,
                "chars_per_token": CHARS_PER_TOKEN}


def _measure(pk: EvidencePacket, intent: str, system: str, with_draft: Callable[[ExplainRequest], list[dict[str, Any]]] | None) -> int:
    req = ExplainRequest(packet=pk, question=Question(intent=intent), menu=M.applicable(pk))
    return prompt_tokens(req, facts(req), system, with_draft(req) if with_draft else None)


def trim(packet: EvidencePacket, intent: str, *, system: str, budget: int = PROMPT_TOKEN_BUDGET,
         draft_fn: Callable[[ExplainRequest], list[dict[str, Any]]] | None = None) -> Trimmed:
    """The packet trimmed to the budget by the documented order. ``draft_fn`` (local reword mode) builds the draft for a request so its
    size is counted too. A packet that already fits is returned untouched."""
    pk = packet
    tokens = _measure(pk, intent, system, draft_fn)
    dropped: list[str] = []
    for step in DROP_ORDER:
        if tokens <= budget:
            break
        if intent in step.keep_for:
            continue
        new = step.fn(pk)
        if new is None:
            continue
        pk = finalise(EvidencePacket.model_validate_json(new.model_dump_json()))
        dropped.append(step.name)
        tokens = _measure(pk, intent, system, draft_fn)
    return Trimmed(pk, dropped, tokens, budget, tokens > budget)
