"""Where packets come from at run time (REQ-6): the engine's own analytics, read through the same functions its API uses.

``Sources`` is a bundle of small callables, so the packet service is testable without an app and a missing layer is simply a missing
block. ``Sources.from_app(app)`` wires the real ones lazily: the genome service (``app.state.genome``), the coach brain
(``app.state.coach``, a dry read that changes nothing), the hazard evaluation (only if it is already cached, unless
``compute_hazard`` is set, because computing it takes seconds), the routines handler and, when the ML-V2 package offers a builder,
``EvidenceInputs``. Every callable returns the API's own shape (``{meta, data}`` or ``(data, meta)``) or None.

Nothing here reads a name, a path or any text: only the numeric and enum fields the builders keep.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from . import packet as P

Envelope = dict[str, Any]


class NoEvidence(LookupError):
    """No block could be built for this person and case. ``code`` is ``no_evidence``."""

    code = "no_evidence"


@dataclass
class Sources:
    genome: Callable[[str | None, str | None], tuple[dict, Any] | None] | None = None
    hazard: Callable[[str], Envelope | None] | None = None
    coach: Callable[[str], dict | None] | None = None
    routines: Callable[[str], Envelope | None] | None = None
    inputs: Callable[[str | None, str | None], Any] | None = None

    @classmethod
    def from_app(cls, app: Any, *, compute_hazard: bool = False) -> "Sources":
        def genome(person, case):
            from ..genome import TASK, GenomeError

            try:
                return app.state.genome.genome(TASK, person=person, episode=case)
            except GenomeError:
                return None

        def hazard(person):
            from .. import routes_analytics as ra

            try:
                key = (ra._data_signature(), "apprentices" if person.startswith(("p_exp", "p_nov")) else "personas")
                if not compute_hazard and key not in ra._cache:
                    return None
                out = ra.get_hazard(person, limit=None)
            except Exception:
                return None
            return out if isinstance(out, dict) else None

        def coach(person):
            from ..coach import CoachError

            try:
                return app.state.coach.next_step(person, None, commit=False).to_dict()
            except CoachError:
                return None
            except Exception:
                return None

        def routines(person):
            try:
                from .. import routes_handoff as rh

                out = rh.get_routines(person=person, case=None)
            except Exception:
                return None
            return out if isinstance(out, dict) else None

        def inputs(person, case):
            try:
                from ..mlv2 import evidence_inputs as ei
            except Exception:
                return None
            fn = getattr(ei, "build", None) or getattr(ei, "build_evidence_inputs", None)
            return fn(person, case) if callable(fn) else None

        return cls(genome=genome, hazard=hazard, coach=coach, routines=routines, inputs=inputs)


@dataclass
class Built:
    packet: P.EvidencePacket
    person: str | None
    case: str | None
    blocks: dict[str, str] = field(default_factory=dict)       # block -> "ok" | "absent" | "dropped: <why>"


def _try(fn: Callable[[], Any]) -> Any:
    try:
        return fn()
    except Exception:
        return None


def build_packet(person: str | None, case: str | None, src: Sources) -> Built:
    """Assemble the packet for ``person`` (and ``case``) from whatever blocks exist. ML-V2 inputs, when present and accepted, are the
    base; otherwise the v1 genome. Hazard, coach and routine blocks are added when their sources answer. Raises ``NoEvidence``."""
    blocks: dict[str, str] = {}
    pk: P.EvidencePacket | None = None
    pid, cid = person, case
    if src.inputs is not None:
        inp = _try(lambda: src.inputs(person, case))
        if inp is not None:
            try:
                pk = P.from_evidence_inputs(inp, person=person, case=case)
                blocks["mlv2"] = "ok"
            except P.InputNotAccepted:
                blocks["mlv2"] = "dropped: not accepted against v1"
            except Exception as exc:
                blocks["mlv2"] = f"dropped: {type(exc).__name__}"
        else:
            blocks["mlv2"] = "absent"
    if pk is None and src.genome is not None:
        got = _try(lambda: src.genome(person, case))
        if got is not None:
            data, meta = got
            pk = P.from_genome(data, meta)
            pid = pid or data.get("person")
            cid = cid or data.get("episode")
            blocks["genome"] = "ok"
        else:
            blocks["genome"] = "absent"
    meta_hint: dict[str, Any] | None = None
    hz = hazard_env = None
    if src.hazard is not None and pid:
        hazard_env = _try(lambda: src.hazard(pid))
        if hazard_env:
            hz = P.from_hazard(hazard_env["data"], hazard_env.get("meta"), person=pid)
            meta_hint = hazard_env.get("meta")
        blocks["hazard"] = "ok" if hz else "absent"
    coach = chz = None
    if src.coach is not None and pid:
        dec = _try(lambda: src.coach(pid))
        if dec:
            coach, chz = P.from_coach(dec)
        blocks["coach"] = "ok" if coach else "absent"
    routines: dict[str, P.Routine] = {}
    if src.routines is not None and pid:
        env = _try(lambda: src.routines(pid))
        if env:
            routines = P.from_routines(env.get("data") or [])
            meta_hint = meta_hint or env.get("meta")
        blocks["routines"] = "ok" if routines else "absent"
    if pk is None:
        if hz is None and coach is None and not routines:
            raise NoEvidence("No analytics are available for this person yet.")
        pk = P.empty_packet(P._meta_block(meta_hint, origin=None, split="leave_one_person_out" if hz else "none"))
    pk = P.combine(pk, hazard=hz or chz, coach=coach, routines=routines or None)
    if pk.is_empty():
        raise NoEvidence("No analytics are available for this person yet.")
    return Built(pk, pid, cid, blocks)
