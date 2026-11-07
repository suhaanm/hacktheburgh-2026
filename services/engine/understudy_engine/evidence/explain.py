"""Explain (REQ-6): a language model turns an evidence packet into plain English; code decides whether to believe it.

    explain(packet, question="why did this case take 14 minutes?") -> dict

What happens, in order, all of it code:

1. The question is reduced to a closed **intent** (``intent.classify``); its words never reach a model. A duration the worker typed
   is kept as one number and compared with the packet.
2. The request (packet, intent, applicable coach-menu ids) is built as a ``SafePayload``. The **deterministic template reply** is
   built from it and checked by the same provenance check a model reply must pass: it is always available, so the feature works
   with no model.
3. Routing (code decides; the model is replaceable): mock mode uses the template only. Otherwise the LOCAL model (Qwen through the
   local-model server; it sees only the packet's facts) is tried first, then, only if the worker set ``UNDERSTUDY_EVIDENCE_CLOUD=1``,
   a cloud wording through ``egress.send`` (the privacy spine writes the ledger line; this module never imports a model client).
4. A model reply must match the strict reply schema and pass ``provenance.check_reply``. The first reply that does is used. Anything
   else (schema, a number that does not trace, a URL, an instruction, a causal claim, a model that is down) falls back to the next
   route and finally to the template. The response always says which source wrote the words and what the check found.
5. The model never writes advice: it may pick up to two ids from the vetted coach menu, code resolves them to text, and an id that
   does not apply is dropped. Limitation sentences are chosen and worded by code from the packet and are always appended.

The explainer improves readability, not accuracy. A faithful-sounding explanation can still rest on a wrong number: the check proves
that every number traces to the packet, not that the packet is true.
"""
from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass, field
from typing import Any, Protocol

from pydantic import ValidationError

from . import intent as I
from . import menu as M
from . import templates as T
from . import vocab as V
from .packet import EvidencePacket, ExplainRequest, FactTable, Question, facts
from .provenance import REPLY_SCHEMA, Verdict, check_reply

PURPOSE = "evidence.explain"
CLOUD_ENV = "UNDERSTUDY_EVIDENCE_CLOUD"
MAX_TOKENS_LOCAL = 700
_TRUE = ("1", "true", "yes", "on")

INSTRUCTIONS = (
    "You receive one JSON object with facts about one worker's case: seconds, intervals, counts, shares, fixed ids, an intent and a "
    "menu of coach ids. Write a short plain-English reply in the requested JSON format. "
    "Use only numbers that appear in the facts: copy a number exactly, or round it to a whole number with the word about. "
    "Never add, subtract, divide or compare numbers to make a new one, and never write twice, half or a share you worked out. "
    "A share or probability such as 0.103 is written as a percentage, 10%. "
    "Name only habits that appear in the facts. Say associated with, never because or caused. "
    "Never say anyone will improve or become an expert. Do not give advice in a sentence: choose up to two ids from menu for coach_actions. "
    "Give each sentence in uses the paths of the fields its numbers come from. In the packet, habits maps to habit, cohort_habits to "
    "cohort_habit, cogs to cog, consequences to consequence and routines to routine, so a habit's seconds are habit.<id>.seconds; the "
    "other blocks are gap.<field>, hazard.<field>, progress.<field>, coach.<field> and meta.<field>. "
    "State an interval together with its value when both are in the facts. Use a section of kind explanation for a summary and kind "
    "answer for an answer to the intent. At most four sentences per section."
)


class BackendError(Exception):
    """A route could not produce a reply. ``code`` is a short stable token; the message never carries packet or reply text."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class Backend(Protocol):
    name: str

    def ready(self) -> str | None:
        """None when usable now, else a short reason code."""

    def generate(self, req: ExplainRequest, tab: FactTable) -> Any:
        """A reply object (unchecked). Raises ``BackendError``."""


@dataclass
class Backends:
    """Injected routes (tests and the evaluation pass fakes here; the HTTP route never does, so it can only reach real ones)."""

    local: Backend | None = None
    cloud: Backend | None = None

    def ordered(self) -> list[Backend]:
        return [b for b in (self.local, self.cloud) if b is not None]


# ------------------------------------------------------------------------------------------------ the local model
_local_lock = threading.Lock()


def local_schema(tab: FactTable, menu: list[str]) -> dict[str, Any]:
    """The reply schema narrowed for this packet: ``uses`` and ``coach_actions`` can only name real fields and applicable ids, so a
    constrained decoder cannot cite a field that does not exist."""
    import copy

    s = copy.deepcopy(REPLY_SCHEMA)
    sent = s["properties"]["sections"]["items"]["properties"]["sentences"]["items"]["properties"]
    sent["uses"]["items"] = {"type": "string", "enum": tab.all_paths()}
    s["properties"]["coach_actions"]["items"] = {"type": "string", "enum": list(menu)}
    return s


def local_user_message(req: ExplainRequest, tab: FactTable) -> str:
    """What the local model is shown: the packet flattened to ``path -> value`` (every value is a field of the packet), the enums, the
    intent and the menu. Nothing else, and never the worker's words."""
    body = {"intent": req.question.intent, "menu": list(req.menu),
            "fields": {p: f.value for p, f in sorted(tab.facts.items())},
            "labels": {p: v for p, v in sorted(tab.labels.items()) if not p.startswith("question.")}}
    return json.dumps(body, sort_keys=True, separators=(",", ":"))


class LocalBackend:
    """The local model through the local-model server (``localmodel.server``), constrained to the reply schema.

    ``client`` may be any object with ``chat_json(messages, schema, name=, max_tokens=) -> result with .obj`` (tests pass a fake). With
    no client given, the server is used only when the local-model layer's own switches say so (flag on, not mock mode, binary and
    model present), started lazily exactly as the digest pipeline does."""

    name = "local"

    def __init__(self, client: Any | None = None) -> None:
        self._client = client
        self._own = client is None
        self.model = "local"

    def ready(self) -> str | None:
        if self._client is not None:
            return None
        try:
            from ..localmodel.server import get_server

            srv = get_server()
            reason = srv.unavailable_reason()
            if reason is not None:
                return f"local:{reason}"
            if not srv.running() and not srv.start():
                return "local:start_failed"
            self._client = srv.client()
            self.model = "local:" + (srv.status().get("model", {}).get("file") or "model")
            return None
        except Exception as exc:               # never let the optional model break the feature
            return f"local:{type(exc).__name__}"

    def generate(self, req: ExplainRequest, tab: FactTable) -> Any:
        why = self.ready()
        if why is not None:
            raise BackendError(why)
        messages = [{"role": "system", "content": INSTRUCTIONS}, {"role": "user", "content": local_user_message(req, tab)}]
        try:
            from ..localmodel.client import ClientError
        except Exception:                       # pragma: no cover
            ClientError = RuntimeError          # type: ignore[assignment,misc]
        try:
            with _local_lock:
                res = self._client.chat_json(messages, local_schema(tab, req.menu), name="evidence_reply", max_tokens=MAX_TOKENS_LOCAL)
        except ClientError as exc:
            raise BackendError(f"client:{getattr(exc, 'kind', 'error')}") from None
        except BackendError:
            raise
        except Exception as exc:
            raise BackendError(f"client:{type(exc).__name__}") from None
        return getattr(res, "obj", res)


# ------------------------------------------------------------------------------------------------ the cloud wording
def ensure_registered() -> None:
    """Register ``evidence.explain`` with the privacy spine (idempotent). The payload is the packet, the intent and the menu ids."""
    from ..privacy.payload import register_payload

    register_payload(PURPOSE, ExplainRequest, instructions=INSTRUCTIONS, response_schema=REPLY_SCHEMA, method="check",
                     description="Reword an evidence packet (numbers, intervals, ids, enums; no text) as plain English; the reply is checked by code.")


class CloudBackend:
    """Optional cloud wording through the egress guard (``egress.send``): validated, bucketed-scan, ledgered, then the fast model.
    Used only when the worker sets ``UNDERSTUDY_EVIDENCE_CLOUD=1`` (or a test passes a capturing port)."""

    name = "cloud"

    def __init__(self, port: Any | None = None) -> None:
        self.port = port
        self.last_ledger_id: str | None = None
        self.model: str | None = None

    def ready(self) -> str | None:
        return None

    def generate(self, req: ExplainRequest, tab: FactTable) -> Any:
        try:
            from ..privacy import egress
            from ..privacy.egress import EgressError

            ensure_registered()
            res = egress.send(PURPOSE, req, port=self.port)
        except ImportError:
            raise BackendError("egress:unavailable") from None
        except Exception as exc:
            code = getattr(exc, "code", None) or type(exc).__name__
            raise BackendError(f"egress:{code}") from None
        self.last_ledger_id, self.model = res.ledger_id, res.model
        return res.output


# ------------------------------------------------------------------------------------------------ routing
def cloud_allowed() -> bool:
    return os.environ.get(CLOUD_ENV, "").strip().lower() in _TRUE


def is_mock() -> bool:
    return os.environ.get("UNDERSTUDY_MOCK", "").strip().lower() in _TRUE


def plan_route(backends: Backends | None = None, *, mock: bool | None = None, allow_cloud: bool | None = None) -> list[Backend]:
    """Which routes to try, in order. Code decides.

    * Injected backends (tests, the evaluation) are used as given.
    * Mock mode (``UNDERSTUDY_MOCK=1``): none, so only the deterministic template is used.
    * Otherwise the local model first, then the cloud wording only if the worker allowed it."""
    if backends is not None and backends.ordered():
        return backends.ordered()
    mock = is_mock() if mock is None else mock
    if mock:
        return []
    out: list[Backend] = [LocalBackend()]
    if (cloud_allowed() if allow_cloud is None else allow_cloud):
        out.append(CloudBackend())
    return out


# ------------------------------------------------------------------------------------------------ the result
def _matches(asked: float | None, case_s: float | None) -> bool | None:
    """Does the duration the worker typed match the case's recorded seconds? Within 5% or 5 seconds, whichever is larger."""
    if asked is None or case_s is None:
        return None
    return abs(asked - case_s) <= max(0.05 * case_s, 5.0)


def build_request(packet: EvidencePacket, question: str | None = None, intent: str | None = None) -> ExplainRequest:
    it, asked = I.classify(question)
    if intent is not None:
        it = intent
    case_s = packet.gap.case_s if packet.gap else None
    q = Question(intent=it, asked_s=asked, matches_case=_matches(asked, case_s))
    return ExplainRequest(packet=packet, question=q, menu=M.applicable(packet))


@dataclass
class Attempt:
    route: str
    ok: bool
    reason: str | None = None            # a backend code, "schema", or the provenance codes joined by ","
    codes: list[str] = field(default_factory=list)


def _substance_ok(reply: Any, intent: str) -> bool:
    """A reply that cites nothing says nothing a worker can check; only the refusal intent may be a reply with no citation."""
    if intent == "unsupported":
        return True
    return any(s.get("uses") for sec in reply["sections"] for s in sec["sentences"])


def _limits(pk: EvidencePacket) -> list[dict[str, str]]:
    return [{"id": i, "text": V.LIMITATIONS[i]} for i in pk.limitations]


def _footer(pk: EvidencePacket) -> str:
    m = pk.meta
    return f"Based on n = {m.n} {V.N_UNIT_PHRASE[m.n_unit]}; {V.ORIGIN_PHRASE[m.origin]}."


def explain(packet: EvidencePacket, question: str | None = None, *, intent: str | None = None, backends: Backends | None = None,
            mock: bool | None = None, allow_cloud: bool | None = None) -> dict[str, Any]:
    """The explanation, the coaching and the limits for one packet, with the source and the check's verdict.

    Never raises for a model problem: the template is the floor. Raises ``ValueError`` only for a packet that cannot be sent as a
    request (a bug in a builder)."""
    try:
        req = build_request(packet, question, intent)
    except ValidationError as exc:
        raise ValueError("the packet cannot be put in a request: " + "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}"
                                                                              for e in exc.errors(include_input=False)[:4])) from None
    tab = facts(req)
    menu = list(req.menu)
    template = T.build_reply(req)
    t_verdict = check_reply(template, req, menu=menu)
    attempts: list[Attempt] = []
    chosen: dict[str, Any] | None = None
    source, model, ledger_id, verdict = "template", None, None, t_verdict
    for be in plan_route(backends, mock=mock, allow_cloud=allow_cloud):
        why = be.ready()
        if why is not None:
            attempts.append(Attempt(be.name, False, why))
            continue
        try:
            reply = be.generate(req, tab)
        except BackendError as exc:
            attempts.append(Attempt(be.name, False, exc.code))
            continue
        v = check_reply(reply, req, menu=menu)
        if v.ok and not _substance_ok(reply, req.question.intent):
            v.ok = False
            v.rejected.append(_no_substance())
        if not v.ok:
            attempts.append(Attempt(be.name, False, "schema" if not v.schema_ok else "provenance", v.codes))
            continue
        attempts.append(Attempt(be.name, True))
        chosen, source, verdict = reply, be.name, v
        model = getattr(be, "model", None) or be.name
        ledger_id = getattr(be, "last_ledger_id", None)
        break
    reply = chosen if chosen is not None else template
    # coach actions: the model proposes (ids from the menu), code decides what applies and writes the text
    picked = list(reply.get("coach_actions") or [])
    actions = M.resolve(picked, packet) if chosen is not None else []
    by = "model"
    if not actions:
        actions = M.resolve(M.default_choice(packet), packet)
        by = "code"
    sections: list[dict[str, Any]] = [{"kind": sec["kind"], "sentences": [dict(s) for s in sec["sentences"]]} for sec in reply["sections"]]
    sections.append({"kind": "coaching", "actions": [dict(a, chosen_by=by) for a in actions]})
    sections.append({"kind": "limits", "sentences": _limits(packet)})
    fallback = None
    if chosen is None and attempts:
        fallback = next((a.reason for a in reversed(attempts) if a.reason), None)
    return {
        "intent": req.question.intent,
        "source": source,
        "model": model,
        "ledger_id": ledger_id,
        "sections": sections,
        "footer": _footer(packet),
        "badge": {"origin": packet.meta.origin, "n": packet.meta.n, "n_unit": packet.meta.n_unit, "split": packet.meta.split},
        "check": {**verdict.to_dict(), "subject": "template" if chosen is None else "model", "template_ok": t_verdict.ok},
        "attempts": [{"route": a.route, "ok": a.ok, "reason": a.reason, "codes": a.codes} for a in attempts],
        "fallback_reason": fallback,
        "question": {"asked_s": req.question.asked_s, "matches_case": req.question.matches_case},
    }


def _no_substance():
    from .provenance import SentenceResult

    return SentenceResult("reply", 0, ["no_substance"])
