"""Honest evaluation of the evidence layer (REQ-6): ``evaluate_evidence(fast=False) -> dict``.

Fast (about 10 to 25 seconds on a laptop), offline, deterministic (fixed seeds), no key, no model. What it measures, and what it does not:

* ``packets``: packets built from the synthetic apprentices through the real builders (genome, and the real stuck-hazard evaluation in
  the full run), plus scripted blocks (coach, routines, counterfactual, time to progress) added through the real builders so every
  wording path is exercised. Schema validity is the share that validates against ``packages/schema/evidence_packet.schema.json``,
  round-trips through the typed model and passes the privacy backstop as an ``evidence.explain`` request.
* ``templates``: the deterministic reply must pass its own check for every packet and every intent.
* ``faithful``: a stand-in model that is always faithful but speaks numbers in the other forms of the rounding table and words
  intervals three ways. Pass rate with a Wilson interval; its complement is the check's **false-reject rate on correct replies**.
  It is only as varied as the variations written for it, so on a real model the false-reject rate is likely higher (the live
  block measures that, small n).
* ``adversarial``: the same replies broken in 28 named ways (invented number, swapped interval, wrongly rounded figure,
  hallucinated habit, URL, email, path, prompt injection, causal claim, novice-becomes-expert claim, derived ratio, ...). Rejection
  rate per kind with a Wilson interval, and how often the refusal names the right reason. These are attacks **we wrote**; a rate of 100%
  here is a statement about this list, not about every possible reply.
* ``fallback``: end to end through ``explain`` with these backends: the share of replies that ended on the template.
* ``live``: ``not_run`` unless ``UNDERSTUDY_EVIDENCE_LIVE=local`` and the local model is available (then the real model's pass rate on
  the check, labelled small n); a cloud run needs ``UNDERSTUDY_EVIDENCE_LIVE=cloud`` plus a key, costs money, and has a hard budget.

Limitations are listed in the result. The explainer improves readability, not accuracy; the check proves traceability, not truth.
"""
from __future__ import annotations

import contextlib
import json
import os
import random
import sys
import tempfile
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import jsonschema

from ..trust.stats import wilson_interval
from . import explain as E
from . import fakes as F
from . import packet as P
from . import templates as T
from . import vocab as V
from .packet import EvidencePacket, ExplainRequest, facts
from .provenance import check_reply

LIVE_BUDGET_USD = 0.50
RECORDED_LIVE = Path(__file__).resolve().parents[4] / "data" / "eval" / "evidence_live.json"
LIVE_MAX_REPLIES_LOCAL = 30


def _rate(k: int, n: int) -> dict[str, Any]:
    lo, hi = wilson_interval(k, n) if n else (0.0, 1.0)
    return {"k": k, "n": n, "rate": round(k / n, 4) if n else None, "ci": [round(lo, 4), round(hi, 4)]}


@contextlib.contextmanager
def _isolated_data_dir():
    """The evaluation never writes to the real egress ledger or any shared file."""
    old = os.environ.get("UNDERSTUDY_DATA_DIR")
    with tempfile.TemporaryDirectory(prefix="evidence-eval-") as d:
        os.environ["UNDERSTUDY_DATA_DIR"] = d
        try:
            yield Path(d)
        finally:
            if old is None:
                os.environ.pop("UNDERSTUDY_DATA_DIR", None)
            else:
                os.environ["UNDERSTUDY_DATA_DIR"] = old


# ------------------------------------------------------------------------------------------------ the packets
def build_cohort_packets(root: Path, *, with_hazard: bool, seed: int = 0) -> tuple[list[tuple[str, str, EvidencePacket]], dict[str, Any]]:
    """One packet per novice case from synthetic apprentices (real genome builder); real stuck-hazard readings when ``with_hazard``."""
    from ..genome import TASK, GenomeService
    from ..personas import apprentices
    from ..store import EventStore

    apprentices.generate(root)
    svc = GenomeService(EventStore(root))
    b = svc.bundle(TASK)
    novices = sorted({e.person for e in b.cohort.novices})
    cases = {p: sorted(e.task_id for e in b.cohort.episodes if e.person == p) for p in novices}
    haz: dict[str, Any] | None = None
    if with_hazard:
        from ..hazard import evaluate_apprentice_hazard

        haz = evaluate_apprentice_hazard(n_boot=30)
    rng = random.Random(seed)
    out: list[tuple[str, str, EvidencePacket]] = []
    for p in novices:
        for t in cases[p]:
            data, meta = svc.genome(TASK, person=p, episode=t)
            pk = P.from_genome(data, meta)
            if haz is not None and p in haz["series_by_person"]:
                hz = P.from_hazard({"series": haz["series_by_person"][p], "model": haz["model"], "baselines": haz["baselines"],
                                    "false_alarms_per_hour": haz["false_alarms_per_hour"], "person": haz["per_person"][p]})
                pk = P.combine(pk, hazard=hz)
            out.append((p, t, F.enrich(pk, rng)))
    return out, {"hazard": "real (apprentice evaluation)" if haz is not None else "scripted fixture", "novices": len(novices)}


def _requests(pk: EvidencePacket) -> list[ExplainRequest]:
    out = []
    for it in V.INTENTS:
        out.append(E.build_request(pk, None, intent=it))
    return out


# ------------------------------------------------------------------------------------------------ measures
def _schema_validity(packets: list[tuple[str, str, EvidencePacket]]) -> dict[str, Any]:
    from ..privacy import egress

    schema = json.loads(P.SCHEMA_PATH.read_text()) if P.SCHEMA_PATH.is_file() else P.json_schema()
    E.ensure_registered()
    ok_schema = ok_roundtrip = ok_backstop = 0
    sizes: list[int] = []
    for _, _, pk in packets:
        w = pk.to_wire()
        try:
            jsonschema.validate(w, schema)
            ok_schema += 1
        except jsonschema.ValidationError:
            pass
        try:
            ok_roundtrip += int(EvidencePacket.model_validate_json(pk.model_dump_json()).to_wire() == w)
        except Exception:
            pass
        try:
            info = egress.preview(E.PURPOSE, E.build_request(pk, None))
            ok_backstop += 1
            sizes.append(info["bytes"])
        except Exception:
            pass
    n = len(packets)
    return {"n": n, "json_schema": _rate(ok_schema, n), "typed_roundtrip": _rate(ok_roundtrip, n), "privacy_backstop": _rate(ok_backstop, n),
            "request_bytes_max": max(sizes) if sizes else None, "request_bytes_median": sorted(sizes)[len(sizes) // 2] if sizes else None}


def _templates(packets: list[tuple[str, str, EvidencePacket]]) -> dict[str, Any]:
    k = n = 0
    bad: Counter[str] = Counter()
    for _, _, pk in packets:
        for req in _requests(pk):
            n += 1
            v = check_reply(T.build_reply(req), req, menu=req.menu)
            k += int(v.ok)
            bad.update(v.codes)
    return {"pass": _rate(k, n), "codes_when_rejected": dict(bad)}


def _faithful(packets: list[tuple[str, str, EvidencePacket]], draws: int, seed: int) -> dict[str, Any]:
    n = k = 0
    by_intent: dict[str, list[int]] = {i: [0, 0] for i in V.INTENTS}
    bad: Counter[str] = Counter()
    for pi, (_, _, pk) in enumerate(packets):
        for req in _requests(pk):
            tab = facts(req)
            for d in range(draws):
                fake = F.FaithfulFake(seed=seed + 1000 * pi + d)
                reply = fake.generate(req, tab)
                v = check_reply(reply, req, menu=req.menu)
                n += 1
                k += int(v.ok)
                by_intent[req.question.intent][0] += int(v.ok)
                by_intent[req.question.intent][1] += 1
                bad.update(v.codes)
    return {"pass": _rate(k, n), "false_reject_rate": round(1 - k / n, 4) if n else None,
            "by_intent": {i: _rate(a, b) for i, (a, b) in by_intent.items() if b}, "codes_when_rejected": dict(bad),
            "draws_per_request": draws}


def _paraphrase(packets: list[tuple[str, str, EvidencePacket]], draws: int, seed: int) -> dict[str, Any]:
    """Correct replies in hand-written ordinary English (frames the templates never use): the check's false-reject rate on natural phrasing."""
    n = k = 0
    bad: Counter[str] = Counter()
    for pi, (_, _, pk) in enumerate(packets):
        req = E.build_request(pk, None, intent="where_time_went")
        tab = facts(req)
        for d in range(draws):
            fake = F.ParaphraseFake(seed=seed + 100 * pi + d)
            try:
                reply = fake.generate(req, tab)
            except E.BackendError:
                continue
            v = check_reply(reply, req, menu=req.menu)
            n += 1
            k += int(v.ok)
            bad.update(v.codes)
    return {"pass": _rate(k, n), "false_reject_rate": round(1 - k / n, 4) if n else None, "codes_when_rejected": dict(bad),
            "note": "hand-written paraphrases (12 frames); small and written by us"}


def _adversarial(packets: list[tuple[str, str, EvidencePacket]], intents: tuple[str, ...], seed: int) -> dict[str, Any]:
    per: dict[str, dict[str, int]] = {k: {"n": 0, "rejected": 0, "right_reason": 0} for k in F.KINDS}
    tot_n = tot_rej = tot_right = 0
    for pi, (_, _, pk) in enumerate(packets):
        for it in intents:
            req = E.build_request(pk, None, intent=it)
            tab = facts(req)
            for kind in F.KINDS:
                rng = random.Random(f"{seed}:{pi}:{it}:{kind}")
                base = T.build_reply(req)
                base["coach_actions"] = list(req.menu[:1])
                bad = F.mutate(base, kind, req, tab, rng)
                if bad is None:
                    continue
                v = check_reply(bad, req, menu=req.menu)
                rej = not v.ok
                per[kind]["n"] += 1
                per[kind]["rejected"] += int(rej)
                right = bool(rej and (set(v.codes) & F.EXPECTED[kind]))
                per[kind]["right_reason"] += int(right)
                tot_n += 1
                tot_rej += int(rej)
                tot_right += int(right)
    return {"overall": {"rejected": _rate(tot_rej, tot_n), "right_reason": _rate(tot_right, tot_n)},
            "by_kind": {k: {"n": v["n"], "rejected": _rate(v["rejected"], v["n"]), "right_reason": _rate(v["right_reason"], v["n"])}
                        for k, v in per.items() if v["n"]},
            "kinds_never_applicable": [k for k, v in per.items() if v["n"] == 0], "intents": list(intents)}


def _fallback(packets: list[tuple[str, str, EvidencePacket]], seed: int, limit: int) -> dict[str, Any]:
    """End to end through ``explain``: which source wrote the words, with a faithful fake, an adversarial fake and no model."""
    sub = packets[:limit]
    out: dict[str, Any] = {}
    n = 0
    src: Counter[str] = Counter()
    for pi, (_, _, pk) in enumerate(sub):
        res = E.explain(pk, "why did this case take 14 minutes?", backends=E.Backends(local=F.FaithfulFake(seed=seed + pi)))
        src[res["source"]] += 1
        n += 1
    out["faithful_fake"] = {"n": n, "by_source": dict(src), "template_rate": _rate(src["template"], n)}
    n = 0
    src = Counter()
    reasons: Counter[str] = Counter()
    for pi, (_, _, pk) in enumerate(sub):
        for kind in F.KINDS:
            res = E.explain(pk, "where did my time go?", backends=E.Backends(local=F.AdversarialFake(kind, seed=seed + pi)))
            if res["attempts"] and res["attempts"][0]["reason"] == "inapplicable":
                continue
            src[res["source"]] += 1
            n += 1
            reasons[res["attempts"][0]["reason"] or "none"] += 1
    out["adversarial_fake"] = {"n": n, "by_source": dict(src), "template_rate": _rate(src["template"], n), "first_attempt_reason": dict(reasons)}
    n = 0
    src = Counter()
    for pi, (_, _, pk) in enumerate(sub):
        res = E.explain(pk, None, mock=True)
        src[res["source"]] += 1
        n += 1
    out["no_model_mock"] = {"n": n, "by_source": dict(src), "template_rate": _rate(src["template"], n)}
    return out


# ------------------------------------------------------------------------------------------------ the optional live block
def _live(packets: list[tuple[str, str, EvidencePacket]], seed: int) -> dict[str, Any]:
    try:
        return _live_inner(packets, seed)
    finally:                                         # a server this run started is stopped (the isolated data dir held its pid file)
        mod = sys.modules.get("understudy_engine.localmodel.server")
        if mod is not None:
            try:
                mod.get_server().stop_if_started_here()
            except Exception:
                pass


def _live_inner(packets: list[tuple[str, str, EvidencePacket]], seed: int) -> dict[str, Any]:
    mode = os.environ.get("UNDERSTUDY_EVIDENCE_LIVE", "").strip().lower()
    if mode not in ("local", "cloud"):
        return {"status": "not_run", "reason": "set UNDERSTUDY_EVIDENCE_LIVE=local to measure the real local model (free), or =cloud with a key "
                                              f"to measure a cloud model (costs money; hard budget US${LIVE_BUDGET_USD:.2f}); neither runs by default"}
    if mode == "cloud":
        return {"status": "not_run", "reason": "cloud live runs are not wired into the default evaluation: ask the owner first (budget "
                                              f"US${LIVE_BUDGET_USD:.2f}); use evidence.evaluate.live_cloud(port) explicitly"}
    be = E.LocalBackend()
    why = be.ready()
    if why is not None:
        return {"status": "not_run", "reason": f"local model unavailable ({why})"}
    n = k = schema_bad = backend_bad = 0
    bad: Counter[str] = Counter()
    lat: list[float] = []
    prompt_tokens: list[int] = []
    examples: list[dict[str, Any]] = []
    rng = random.Random(seed)
    picks = rng.sample(packets, min(len(packets), LIVE_MAX_REPLIES_LOCAL // 2))
    for _, _, pk in picks:
        for it in ("where_time_went", "why_slow"):
            req = E.build_request(pk, None, intent=it)
            tab = facts(req)
            t0 = time.perf_counter()
            try:
                reply = be.generate(req, tab)
            except E.BackendError as exc:
                backend_bad += 1
                n += 1
                bad[exc.code] += 1
                continue
            lat.append(time.perf_counter() - t0)
            if be.last_usage.get("prompt_tokens"):
                prompt_tokens.append(be.last_usage["prompt_tokens"])
            v = check_reply(reply, req, menu=req.menu)
            n += 1
            k += int(v.ok)
            schema_bad += int(not v.schema_ok)
            bad.update(v.codes)
            if not v.ok and v.schema_ok and len(examples) < 4:
                r0 = v.rejected[0]
                text = next((sec["sentences"][r0.index]["text"] for sec in v.expanded["sections"]
                             if sec["kind"] == r0.section and r0.index < len(sec["sentences"])), "")
                examples.append({"intent": it, "codes": r0.codes, "sentence": text[:240]})
    # the largest prompt of the cohort (by the estimate), measured once on the real model
    from . import context as C

    biggest = max(((C.trim(pk, it, system=E.REWORD_INSTRUCTIONS, budget=10**6, draft_fn=T.build_draft).tokens, it, pk) for _, _, pk in packets for it in V.INTENTS),
                  key=lambda t: t[0], default=None)
    largest = None
    if biggest is not None:
        req = E.build_request(biggest[2], None, intent=biggest[1])
        try:
            be.generate(req, facts(req))
        except E.BackendError:
            pass
        largest = {"intent": biggest[1], "tokens_est": biggest[0], "tokens_measured": be.last_usage.get("prompt_tokens"), "budget": C.PROMPT_TOKEN_BUDGET}
    lat.sort()
    return {"status": "ok", "model": be.model, "largest_case": largest, "n_replies": n, "pass": _rate(k, n), "schema_failures": schema_bad, "backend_failures": backend_bad,
            "codes_when_rejected": dict(bad), "examples_rejected": examples,
            "prompt_tokens": ({"min": min(prompt_tokens), "max": max(prompt_tokens), "mean": round(sum(prompt_tokens) / len(prompt_tokens))} if prompt_tokens else None),
            "mode": "reword: the model rewrites a code-written draft that carries {field.path} placeholders; code fills them in, then the same check runs",
            "latency_s": {"p50": round(lat[len(lat) // 2], 2), "p95": round(lat[int(0.95 * (len(lat) - 1))], 2)} if lat else None,
            "note": f"Small n ({n}): a pass rate on the check for the real local model on synthetic packets, not a statement about other models or real data."}


def recorded_live() -> dict[str, Any] | None:
    """The live results recorded on 7 Nov 2026 (``data/eval/evidence_live.json``: real models, small n, labelled with their origin), if the
    file exists. It is shown beside a default run's ``not_run``; it is never recomputed here."""
    try:
        return json.loads(RECORDED_LIVE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def live_cloud(port: Any, packets: list[tuple[str, str, EvidencePacket]], *, max_calls: int = 20, est_usd_per_call: float = 0.002,
               seed: int = 0) -> dict[str, Any]:
    """Cloud wording on the check, through ``egress.send`` (``port`` is the real model port). Hard budget US$0.50 on a conservative
    per-call estimate. Costs money: only ever called explicitly, after the owner agrees."""
    calls = min(max_calls, int(LIVE_BUDGET_USD / est_usd_per_call))
    be = E.CloudBackend(port=port)
    rng = random.Random(seed)
    n = k = 0
    bad: Counter[str] = Counter()
    for _, _, pk in rng.sample(packets, min(len(packets), calls)):
        req = E.build_request(pk, None, intent="where_time_went")
        try:
            reply = be.generate(req, facts(req))
        except E.BackendError as exc:
            bad[exc.code] += 1
            n += 1
            continue
        v = check_reply(reply, req, menu=req.menu)
        n += 1
        k += int(v.ok)
        bad.update(v.codes)
    return {"status": "ok", "n_replies": n, "pass": _rate(k, n), "codes_when_rejected": dict(bad), "est_cost_usd": round(n * est_usd_per_call, 3),
            "budget_usd": LIVE_BUDGET_USD}


# ------------------------------------------------------------------------------------------------ limitations
def limitations(result: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {"id": "explainer_readability_not_accuracy", "severity": "high",
         "text": "The explainer improves readability, not accuracy. A faithful-sounding explanation can still rest on a wrong number: the check proves each "
                 "number traces to a field of the packet, not that the packet is true."},
        {"id": "faithful_fake_is_ours", "severity": "medium",
         "text": "The false-reject rate is measured on a stand-in model that varies numbers and interval wording in the ways we wrote down. A real model "
                 "phrases things we did not anticipate, so its false-reject rate is likely higher; a rejected reply costs nothing (the template is used)."},
        {"id": "adversarial_set_is_ours", "severity": "medium",
         "text": "The adversarial rejection rate is against the 28 attacks we wrote. The unknown-habit rule is a set of cue patterns (a cause or a share of "
                 "time attributed to a phrase that names nothing in the vocabulary), not a language model: a novel phrasing with no cue can pass."},
        {"id": "packet_from_synthetic_and_fixtures", "severity": "medium",
         "text": "Packets come from synthetic apprentices (and the real stuck-hazard evaluation in the full run); the coach, routine, counterfactual and "
                 "time-to-progress blocks are scripted fixtures that exercise wording and the check, not measurements."},
        {"id": "live_small_n", "severity": "low",
         "text": "The live block, when it is run, is a small-n pass rate for one local model on synthetic packets; it says nothing about other models."},
    ]


# ------------------------------------------------------------------------------------------------ entry point
def evaluate_evidence(fast: bool = False, *, seed: int = 0, with_live: bool = True) -> dict[str, Any]:
    t0 = time.time()
    with _isolated_data_dir() as tmp:
        packets, info = build_cohort_packets(tmp / "synthetic", with_hazard=not fast, seed=seed)
        adv_intents = ("where_time_went", "why_slow") if fast else ("where_time_went", "why_slow", "compare_expert", "stuck_reading")
        result: dict[str, Any] = {
            "status": "ok",
            "packets": {**info, **_schema_validity(packets)},
            "templates": _templates(packets),
            "faithful": _faithful(packets, 1 if fast else 2, seed),
            "faithful_paraphrase": _paraphrase(packets, 3 if fast else 6, seed),
            "adversarial": _adversarial(packets, adv_intents, seed),
            "fallback": _fallback(packets, seed, 8 if fast else 16),
            "live": _live(packets, seed) if with_live else {"status": "not_run", "reason": "disabled for this call"},
        }
        rec = recorded_live()
        if rec is not None:
            result["live"]["recorded"] = rec
    result["limitations"] = limitations(result)
    result["statement"] = ("No real people are involved. Packets come from synthetic apprentices; no model was called in the default run, and no "
                           "number here comes from a live service.")
    result["meta"] = {
        "origin": "synthetic", "n": len(packets), "n_unit": "episodes", "split": "none; hermetic fakes with fixed seeds",
        "interval_level": 0.95,
        "note": ("Packets from synthetic apprentices through the real builders. Faithful and adversarial replies come from stand-in models written for this "
                 "evaluation; the live block is not_run unless explicitly enabled. " + ("Fast run." if fast else "")),
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    result["elapsed_s"] = round(time.time() - t0, 1)
    return result
