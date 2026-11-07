"""Honest evaluation of the privacy layer (NFR-11): ``evaluate_privacy() -> dict`` for the eval harness.

What it measures, and what it does not claim
--------------------------------------------
* **Canary leaks.** Each registered flow is run several times, each with fresh fixtures seeded with unique planted tokens
  (person names, emails, meeting titles, file paths, commit messages, customer names), against a ``CapturingPort`` that records
  every request body. The count is how many planted tokens appear in any captured request. The HEADLINE interval is per RUN (a
  leak belongs to a code path, and tokens planted in one run are not independent): a one-sided exact (Clopper-Pearson) 95% upper
  bound on the share of runs that leak (0 of 80 is about 3.7%), with the per-flow bound (0 of 10 is about 26%) beside it. The
  token-level bound is reported too, labelled as assuming independence.
* **Logs, audit, queue (PRV-4).** After each run the ledger files, ``audit.jsonl``, the ``queue/`` items and ``logs/`` under the
  data dir, and every ``logging`` record emitted while the flow ran, are searched for the planted tokens.
* **Ledger completeness.** For every flow run: one ledger line per captured request, no request that bypassed the guard, and
  each line's payload equal to the payload the request carried.
* **Flows covered.** Flows come from two places and are reported separately. ``reference`` flows are this layer's own stand-in
  upstream code feeding its four built-in purposes (they test the guard, not another team's code). ``integration`` flows are a
  layer's real code, supplied by that layer in ``understudy_engine/<layer>/canary_flows.py`` (``FLOWS = [CanaryFlow(...)]``).
  A layer that supplies none is listed as ``none_registered``; it is never counted as passed.
* **Negative controls.** The instrument is shown to be able to fail: a deliberately leaky flow must be caught, free text must be
  refused, an unknown purpose refused, a PII-shaped id blocked, a PII-bearing model answer discarded, and a ledger that cannot
  be written must stop the call.
* **Bucketing properties.** Exhaustive and seeded-random sweeps of the five generalisation rules.
* **The canary scan itself.** Its detection rate on tokens rewritten in nine known ways, and its false positives on thousands of clean
  bodies, so "zero leaks" is read together with how able the scan is to see one.
* **Backstop corpus.** Shapes it must catch (by rule) and ordinary vocabulary it must not flag.
* **Static guard.** Modules scanned and violations, from ``guard.scan_tree`` (the extension layers) and ``guard.scan_runtime``
  (the agent runtime, which plans through the model port by design: it must record every visible direct call).

Everything runs offline on synthetic fixtures in a temporary data directory (the real ledger is not touched); the aggregate is
recorded for ``GET /privacy/summary`` only when ``record=True``. Nothing here validates behaviour on real data, and
the real provider is never called.
"""
from __future__ import annotations

import base64
import contextlib
import hashlib
import importlib
import itertools
import json
import logging
import os
import random
import tempfile
import threading
from datetime import datetime, timezone
from typing import Any, Iterable

from . import bucket as B
from . import canary, egress, guard, ledger, patterns
from .egress import EgressError
from .payload import UnsafeFieldError
from .purposes import BriefingCardWording, CalendarSuggestionWording, DigestMeta, GitHabitWording
from .payload import purposes as all_purposes
from .testing import CanaryFlow, CapturingPort, FlowResult, ImageCanaryFlow, image_canary_flow, run_flow, vocabulary_problems

_env_lock = threading.RLock()
LAYERS = guard.GUARDED_DIRS


# ----------------------------------------------------------------------------------------------------- reference flows
def _cal_fixture() -> dict[str, Any]:
    ev = []
    for i, (s, e) in enumerate([(540, 600), (600, 660), (660, 690), (720, 780), (840, 900), (900, 960), (1000, 1030)]):
        ev.append({"title": f"Planning session {i}", "start": s, "end": e, "attendees": [f"Colleague {i}", f"Colleague {i + 10}"],
                   "organizer": f"Organiser {i}", "location": f"Room {i}", "customer": f"Client {i}"})
    return {"owner": {"name": "Ada Lovelace", "email": "ada@corp.example"}, "events": ev}


def _cal_run(fx: dict[str, Any], port: CapturingPort) -> None:
    ev = sorted(fx["events"], key=lambda e: e["start"])
    meeting_min = sum(e["end"] - e["start"] for e in ev)
    b2b = sum(1 for a, b in zip(ev, ev[1:]) if b["start"] == a["end"])
    payload = CalendarSuggestionWording(template="reduce_back_to_back", role="programmer", risk="low",
                                        learner={"meeting_h": meeting_min / 60.0, "back_to_back_runs": b2b, "n_meetings": len(ev)},
                                        expert={"meeting_h": 8.0, "back_to_back_runs": 1})
    egress.send("calendar.suggestion_wording", payload, port=port)


def _git_fixture() -> dict[str, Any]:
    msgs = ["fix rounding bug", "add export", "refactor loader", "wip", "update docs", "fix typo"]
    return {"repo": "/Users/ada/Projects/payroll",
            "commits": [{"author": f"Dev {i}", "email": f"dev{i}@corp.example", "message": m,
                         "files": [{"path": ("tests/test_x.py" if i % 3 == 0 else f"src/mod{i}.py"), "added": 10 + i, "deleted": i}]}
                        for i, m in enumerate(msgs)]}


def _git_run(fx: dict[str, Any], port: CapturingPort) -> None:
    c = fx["commits"]
    touched = sum(1 for x in c if any("test" in f["path"] for f in x["files"]))
    payload = GitHabitWording(habit="no_tests", learner_ratio=1 - touched / len(c), expert_ratio=0.1, n_commits=len(c) + 10)
    egress.send("git.habit_wording", payload, port=port)


def _brief_fixture() -> dict[str, Any]:
    return {"routines": [{"title": "Enter the household into three calculators", "why": "Done 14 times in three weeks",
                          "customer": "Acme Housing", "episodes": 14, "minutes_per_week": 96},
                         {"title": "Weekly case note", "why": "Same steps each Friday", "customer": "Beta Trust", "episodes": 6,
                          "minutes_per_week": 30}]}


def _brief_run(fx: dict[str, Any], port: CapturingPort) -> None:
    for r in fx["routines"]:
        payload = BriefingCardWording(kind="automate", risk="normal", sources=["routine"],
                                      numbers={"n_meetings": r["episodes"], "meeting_share": min(1.0, r["minutes_per_week"] / 240)})
        egress.send("briefing.card_wording", payload, port=port)


def _digest_fixture() -> dict[str, Any]:
    return {"items": [{"message": m, "author": f"Dev {i}", "path": f"src/a{i}.py"} for i, m in enumerate(
        ["fix payroll rounding for Acme", "add csv export", "refactor loader", "fix crash on empty file", "update docs", "revert bad merge"])]}


def _digest_run(fx: dict[str, Any], port: CapturingPort) -> None:
    cats = {"bugfix": 0, "feature": 0, "refactor": 0, "docs": 0, "revert": 0}
    for it in fx["items"]:
        m = it["message"].lower()
        key = "bugfix" if "fix" in m else "revert" if "revert" in m else "refactor" if "refactor" in m else "docs" if "doc" in m else "feature"
        cats[key] += 1
    payload = DigestMeta(kind="commit", window_days=7, counts=cats, minutes={"focus": 125, "meeting": 40})
    egress.send("digest.meta", payload, port=port)


def reference_flows() -> list[CanaryFlow]:
    """This layer's own stand-in upstream code feeding the four built-in purposes. They test the guard, not another team's code."""
    return [
        CanaryFlow("reference.calendar_suggestion_wording", _cal_fixture, _cal_run, layer="privacy", kind="reference"),
        CanaryFlow("reference.git_habit_wording", _git_fixture, _git_run, layer="privacy", kind="reference", mode="append"),
        CanaryFlow("reference.briefing_card_wording", _brief_fixture, _brief_run, layer="privacy", kind="reference", min_requests=2),
        CanaryFlow("reference.digest_meta", _digest_fixture, _digest_run, layer="privacy", kind="reference"),
    ]


# ----------------------------------------------------------------------------------------------------- discovery
def _proactive_adapter() -> CanaryFlow:
    """Fallback adapter for the proactive layer when it has not supplied ``canary_flows``: plant canaries in a card's title and
    reason, run its real ``reword_why`` through a capturing port. Raises ImportError when the layer is not importable."""
    from understudy_engine.proactive.candidates import Candidate, FireSpec
    from understudy_engine.proactive.reword import reword_why

    def fixture() -> dict[str, Any]:
        return {"card": {"title": "Enter the household into three calculators", "why": "Done 14 times in three weeks",
                         "customer": "Acme Housing", "owner": "Ada Lovelace"}}

    def run(fx: dict[str, Any], port: CapturingPort) -> None:
        c = Candidate(kind="automate", title=fx["card"]["title"], why=fx["card"]["why"],
                      numbers={"episodes": 14, "minutes_per_week": 96, "confidence": 0.8}, source_tags=["routines"], risk_class="normal",
                      value=0.7, urgency=0.5, freshness=0.9, prepared_template={"template": "t", "params": {}},
                      fire=FireSpec("queue"), subject=fx["card"]["customer"], person="p_x")
        reword_why(c, port=port)

    return CanaryFlow("proactive.reword_why (adapter)", fixture, run, layer="proactive", kind="integration")


def discover_image_flows() -> list[ImageCanaryFlow]:
    """Layer-supplied image flows: ``understudy_engine.<layer>.canary_flows.IMAGE_FLOWS``."""
    out: list[ImageCanaryFlow] = []
    for layer in LAYERS:
        try:
            mod = importlib.import_module(f"understudy_engine.{layer}.canary_flows")
        except Exception:
            continue
        out.extend(f for f in getattr(mod, "IMAGE_FLOWS", []) if isinstance(f, ImageCanaryFlow))
    return out


def discover_flows() -> tuple[list[CanaryFlow], dict[str, dict[str, Any]]]:
    """Layer-supplied flows from ``understudy_engine.<layer>.canary_flows.FLOWS`` plus adapters for known entry points."""
    flows: list[CanaryFlow] = []
    layers: dict[str, dict[str, Any]] = {}
    for layer in LAYERS:
        name = f"understudy_engine.{layer}.canary_flows"
        try:
            mod = importlib.import_module(name)
            got = list(getattr(mod, "FLOWS", []))
            flows.extend(got)
            img = [f for f in getattr(mod, "IMAGE_FLOWS", []) if isinstance(f, ImageCanaryFlow)]
            na = getattr(mod, "NOT_APPLICABLE", None)
            if got or img:
                layers[layer] = {"status": "registered", "flows": [f.name for f in got], "image_flows": [f.name for f in img]}
            elif isinstance(na, str) and na.strip():
                # the layer says it has no model path (for example sources only); the static guard is what covers it
                layers[layer] = {"status": "not_applicable", "flows": [], "note": na.strip()[:240]}
            else:
                layers[layer] = {"status": "none_registered", "flows": []}
        except ModuleNotFoundError as exc:
            if not (guard.ENGINE_PKG / layer).is_dir():
                layers[layer] = {"status": "not_present", "flows": [], "note": "the layer's directory does not exist yet"}
            elif exc.name == name:
                layers[layer] = {"status": "none_registered", "flows": [], "note": "no canary_flows module"}
            else:
                layers[layer] = {"status": "error", "flows": [], "note": f"import failed: {exc.name}"}
        except Exception as exc:  # a broken layer must not break the evaluation
            layers[layer] = {"status": "error", "flows": [], "note": f"{type(exc).__name__} while importing"}
    for layer in guard.PURE_COMPUTE_DIRS:
        if layers.get(layer, {}).get("status") == "none_registered":
            layers[layer] = {"status": "pure_compute", "flows": [], "note": "no model or network path by rule; the static guard (no client, no process, "
                                                                           "no URL, no reviewed exceptions) is the control"}
    if layers.get("proactive", {}).get("status") != "registered":
        try:
            f = _proactive_adapter()
            flows.append(f)
            layers["proactive"] = {"status": "adapter", "flows": [f.name],
                                   "note": "evaluated through privacy-layer adapter, not a layer-supplied flow"}
        except Exception as exc:
            layers.setdefault("proactive", {"status": "none_registered", "flows": []})["note"] = f"adapter unavailable ({type(exc).__name__})"
    return flows, layers


# ----------------------------------------------------------------------------------------------------- statistics
def upper_bound_95(k: int, n: int) -> float:
    """One-sided exact (Clopper-Pearson) 95% upper bound on a proportion with k events in n trials."""
    if n <= 0:
        return 1.0
    if k >= n:
        return 1.0
    from scipy.stats import beta

    return float(beta.ppf(0.95, k + 1, n - k))


# ----------------------------------------------------------------------------------------------------- negative controls
def _control(name: str, expected: str, fn) -> dict[str, Any]:
    try:
        observed, ok = fn()
    except Exception as exc:  # pragma: no cover - a control that errors is a failed control
        observed, ok = f"control raised {type(exc).__name__}", False
    return {"name": name, "expected": expected, "observed": observed, "passed": bool(ok)}


def negative_controls() -> list[dict[str, Any]]:
    """Each control must come out as expected; if the instrument could not fail, zero leaks would mean nothing."""
    out: list[dict[str, Any]] = []

    def leaky() -> tuple[str, bool]:
        def run(fx, port):
            port.plan([{"role": "user", "content": "Reword: " + fx["events"][0]["title"]}], None)

        r = run_flow(CanaryFlow("control.leaky", _cal_fixture, run, min_requests=0), seed=1)
        return (f"leaked={r.leaked}, ledger_complete={r.ledger_complete}", r.leaked >= 1 and not r.ledger_complete)

    out.append(_control("a flow that bypasses the guard and sends a meeting title is caught", "leak detected and ledger incomplete", leaky))

    def rewritten() -> tuple[str, bool]:
        def run(fx, port):
            port.plan([{"role": "user", "content": fx["owner"]["name"].upper().replace(" ", "_")}], None)

        r = run_flow(CanaryFlow("control.rewritten", _cal_fixture, run, min_requests=0), seed=2)
        return (f"leaked={r.leaked}", r.leaked >= 1)

    out.append(_control("a leaked name that was upper-cased and underscored is still caught", "leak detected", rewritten))

    def logs_title() -> tuple[str, bool]:
        import logging

        def run(fx, port):
            _cal_run(fx, port)
            logging.getLogger("control.calendar").info("handling %s", fx["events"][0]["title"])

        r = run_flow(CanaryFlow("control.logs_title", _cal_fixture, run), seed=3)
        return (f"artifact_leaked={r.artifact_leaked}, model_leaked={r.leaked}", r.artifact_leaked >= 1 and r.leaked == 0)

    out.append(_control("a flow that writes a planted meeting title into a log record is caught (PRV-4)", "log leak detected, none at the model", logs_title))

    def queue_title() -> tuple[str, bool]:
        from ._paths import data_dir

        def run(fx, port):
            _cal_run(fx, port)
            q = data_dir() / "queue"
            q.mkdir(parents=True, exist_ok=True)
            (q / "q_control.json").write_text(json.dumps({"summary": fx["events"][0]["title"]}))

        r = run_flow(CanaryFlow("control.queue_title", _cal_fixture, run), seed=4)
        return (f"artifact_leaked={r.artifact_leaked}, model_leaked={r.leaked}", r.artifact_leaked >= 1 and r.leaked == 0)

    out.append(_control("a flow that writes a planted title into an approval-queue item is caught (PRV-4)", "queue leak detected, none at the model", queue_title))

    def free_text() -> tuple[str, bool]:
        port = CapturingPort()
        try:
            egress.send("calendar.suggestion_wording", dict(template="Redundancy plan for Ada Lovelace", role="programmer", risk="low",
                                                            learner={}, expert={}), port=port)
        except EgressError as exc:
            return (f"{type(exc).__name__}; requests at the port: {len(port)}", len(port) == 0)
        return ("accepted", False)

    out.append(_control("free text in a payload field is refused and nothing reaches the port", "PayloadRejected, 0 requests", free_text))

    def free_key() -> tuple[str, bool]:
        port = CapturingPort()
        try:
            egress.send("calendar.suggestion_wording", dict(template="protect_focus_block", role="programmer", risk="low",
                                                            learner={"Quarterly planning with Bob": 3}, expert={}), port=port)
        except EgressError as exc:
            return (f"{type(exc).__name__}; requests at the port: {len(port)}", len(port) == 0)
        return ("accepted", False)

    out.append(_control("free text smuggled in as a dictionary key is refused", "PayloadRejected, 0 requests", free_key))

    def unknown() -> tuple[str, bool]:
        port = CapturingPort()
        try:
            egress.send("calendar.not_a_purpose", {"x": 1}, port=port)
        except EgressError as exc:
            return (f"{type(exc).__name__}; requests at the port: {len(port)}", len(port) == 0)
        return ("accepted", False)

    out.append(_control("an unregistered purpose is refused", "UnknownPurpose, 0 requests", unknown))

    def definition_time() -> tuple[str, bool]:
        from .payload import SafePayload

        try:
            type("Bad", (SafePayload,), {"__annotations__": {"title": str}})
        except UnsafeFieldError:
            return ("UnsafeFieldError at class definition", True)
        return ("class defined", False)

    out.append(_control("a payload class with a free string field cannot even be defined", "UnsafeFieldError", definition_time))

    def pii_answer() -> tuple[str, bool]:
        port = CapturingPort().script("plan", {"text": "Email ada@example.com about it"})
        try:
            egress.send("calendar.suggestion_wording", dict(template="protect_focus_block", role="programmer", risk="low", learner={}, expert={}), port=port)
        except EgressError as exc:
            return (type(exc).__name__, type(exc).__name__ == "ModelOutputRejected")
        return ("accepted", False)

    out.append(_control("a model answer containing an email address is discarded", "ModelOutputRejected", pii_answer))

    def ledger_down() -> tuple[str, bool]:
        port = CapturingPort()
        real = ledger.append

        def boom(_e):
            raise OSError("disk full")

        ledger.append = boom  # type: ignore[assignment]
        try:
            try:
                egress.send("git.habit_wording", dict(habit="no_tests", learner_ratio=0.2, expert_ratio=0.1, n_commits=30), port=port)
            except EgressError as exc:
                return (f"{type(exc).__name__}; requests at the port: {len(port)}", len(port) == 0)
            return ("sent without a ledger line", False)
        finally:
            ledger.append = real  # type: ignore[assignment]

    out.append(_control("if the ledger cannot be written, the model is not called", "EgressUnavailable, 0 requests", ledger_down))

    def big_number() -> tuple[str, bool]:
        from .payload import SafePayload, register_payload, unregister_purpose

        class Probe(SafePayload):
            n: int

        unregister_purpose("control.big_number")
        register_payload("control.big_number", Probe)
        port = CapturingPort()
        try:
            try:
                egress.send("control.big_number", {"n": 4_123_456}, port=port)
            except EgressError as exc:
                return (f"{type(exc).__name__}; requests at the port: {len(port)}", len(port) == 0)
            return ("accepted", False)
        finally:
            unregister_purpose("control.big_number")

    out.append(_control("an id- or timestamp-sized integer is blocked by the backstop", "EgressBlocked, 0 requests", big_number))
    return out


# ----------------------------------------------------------------------------------------------------- bucketing properties
def bucketing_properties(seed: int = 20261107) -> list[dict[str, Any]]:
    """Sweeps of the generalisation rules. Each row: the rule, the property, how many cases, how many failed."""
    rng = random.Random(seed)
    rows: list[dict[str, Any]] = []

    def row(rule: str, prop: str, cases: int, failures: int, how: str) -> None:
        rows.append({"rule": rule, "property": prop, "cases": cases, "failures": failures, "method": how})

    f = n = 0
    for k in range(0, 20001):
        out = B.bucket_count(k)
        n += 1
        f += 0 if ((out == "lt5") if k < 5 else (out == k)) else 1
    row("count", "under 5 becomes lt5; 5 and more unchanged", n, f, "exhaustive 0..20000")
    f = n = 0
    for k in range(0, 20001):
        n += 1
        f += 0 if B.bucket_count(B.bucket_count(k)) == B.bucket_count(k) else 1
    row("count", "idempotent", n, f, "exhaustive 0..20000")

    def sweep(rule: str, fn, step: float, lo: float, hi: float, tol: float, grid: float, count: int, exhaustive: bool,
              grid_tol: float = 1e-9, unit: float = 1.0) -> None:
        f1 = f2 = f3 = f4 = c = 0
        prev = -1e18
        xs = ([lo + i * (hi - lo) / count for i in range(count + 1)] if exhaustive else sorted(rng.uniform(lo, hi) for _ in range(count)))
        for x in xs:
            c += 1
            y = fn(x)
            f1 += 0 if abs(y - x) <= tol + 1e-9 else 1
            f2 += 0 if abs(y * unit / grid - round(y * unit / grid)) * grid <= grid_tol else 1
            f3 += 0 if y >= prev else 1
            f4 += 0 if fn(y) == y else 1
            prev = y
        how = f"{'grid' if exhaustive else 'seeded random'} of {count + 1} points in [{lo}, {hi}]"
        row(rule, f"within half a step ({tol}) of the input", c, f1, how)
        row(rule, f"always on the {grid:g} grid" + (" (in minutes, to within the two-decimal representation)" if unit != 1.0 else ""), c, f2, how)
        row(rule, "monotone (a bigger input never gives a smaller output)", c, f3, how)
        row(rule, "idempotent", c, f4, how)

    sweep("time_15min", B.round_time_minutes, 15, 0.0, 1440.0, 7.5, 15.0, 14400, True)
    sweep("duration_5min", B.round_duration_minutes, 5, 0.0, 2000.0, 2.5, 5.0, 20000, True)
    sweep("ratio_10pct", B.bucket_ratio, 0.1, 0.0, 1.0, 0.05, 0.1, 100000, True)
    sweep("hours_5min", B.bucket_hours, 5, 0.0, 80.0, 2.5 / 60 + 0.006, 5.0, 4000, False, grid_tol=0.31, unit=60.0)
    order = {"lt5": 0, "5to9": 1, "10plus": 2}
    f = c = 0
    prev = 0
    for k in range(0, 500):
        o = B.bucket_attendees(k)
        c += 1
        expect = "lt5" if k < 5 else "5to9" if k <= 9 else "10plus"
        f += 0 if (o == expect and order[o] >= prev) else 1
        prev = order[o]
    row("attendees", "lt5 / 5to9 / 10plus partition, monotone", c, f, "exhaustive 0..499")
    return rows


# ----------------------------------------------------------------------------------------------------- the canary scan itself
def _transforms() -> dict[str, Any]:
    import base64
    import urllib.parse

    return {
        "verbatim": lambda s: s, "upper": lambda s: s.upper(), "lower": lambda s: s.lower(),
        "separators_to_underscore": lambda s: "".join(c if c.isalnum() else "_" for c in s),
        "separators_removed": lambda s: "".join(c for c in s if c.isalnum()),
        "url_encoded": lambda s: urllib.parse.quote(s), "base64": lambda s: base64.b64encode(s.encode()).decode(),
        "hex": lambda s: s.encode().hex(), "truncated_to_half_plus_6": lambda s: s[: len(s) // 2 + 6],
    }


def scan_sensitivity(seeds: int = 20) -> dict[str, Any]:
    """How often the canary scan finds a planted token that was rewritten in a known way, per rewrite. Not detected by design:
    a paraphrase, a translation, a hash, a character-code encoding (listed in ``not_tested``)."""
    tf = _transforms()
    by: dict[str, dict[str, int]] = {name: {"cases": 0, "detected": 0} for name in tf}
    for seed in range(seeds):
        p = canary.Planted(seed)
        for kind in canary.KINDS:
            tok = p.make(kind)
            for name, fn in tf.items():
                single = canary.Planted(seed)
                single.tokens.append(next(t for t in p.tokens if t.value == tok))
                port = CapturingPort()
                port.plan([{"role": "user", "content": "context " + fn(tok) + " end"}], None)
                by[name]["cases"] += 1
                by[name]["detected"] += 1 if canary.scan(port, single).leaked == 1 else 0
    cases = sum(v["cases"] for v in by.values())
    detected = sum(v["detected"] for v in by.values())
    return {"cases": cases, "detected": detected, "by_rewrite": by, "kinds": list(canary.KINDS),
            "not_tested": ["paraphrase", "translation", "hashing", "character-code encoding", "image or audio content"]}


def scan_specificity(n: int = 3000, seed: int = 11) -> dict[str, Any]:
    """How often the scan flags a token that is NOT in a clean body (ordinary wording, vocabulary ids, numbers, hashed ids)."""
    rng = random.Random(seed)
    words = ("try protect one longer focus block before lunch meetings back to back review slot batch similar work hours "
             "share ratio commits tests habit expert learner reference week day morning afternoon calendar suggestion "
             "automate break handoff fewer than five percent about").split()
    vocab = ["protect_focus_block", "batch_similar_work", "add_review_slot", "no_tests", "huge_commits", "meeting_h", "lt5", "5to9", "10plus"]
    planted = canary.Planted(3)
    for _ in range(20):
        for k in canary.KINDS:
            planted.make(k)
    false_pos = 0
    for _ in range(n):
        body = " ".join(rng.choice(words) for _ in range(rng.randint(5, 30))) + " " + " ".join(rng.sample(vocab, 3)) \
            + f" {rng.uniform(0, 100):.2f} h:{''.join(rng.choice('0123456789abcdef') for _ in range(12))}"
        port = CapturingPort()
        port.plan([{"role": "user", "content": body}], None)
        false_pos += canary.scan(port, planted).leaked
    return {"clean_bodies": n, "planted_tokens_searched": len(planted), "false_positives": false_pos}


# ----------------------------------------------------------------------------------------------------- backstop corpus
_MUST_CATCH: dict[str, list[str]] = {
    "email": ["ada.lovelace@example.com", "mail ADA@Corp.CO.UK now", "x_y+tag@sub.domain.org"],
    "url": ["https://example.org/plan", "see www.example.net/x", "visit corp.internal", "ftp://files.example.org/a"],
    "path": ["/Users/ada/Projects/x/notes.txt", "~/Documents/plan", "C:\\Users\\ada\\notes.docx", "src/payroll/rounding.py", "secrets.env"],
    "phone": ["+44 7700 900123", "07700 900123", "(415) 555-0132", "+1 415 555 0132"],
    "ni_number": ["AB 12 34 56 C", "ab123456c", "JG 10 33 99 B"],
    "long_digits": ["account 12345678", "4111 1111 1111 1111", "ref 9876543210"],
    "ip_address": ["192.168.0.12", "10.0.0.1"],
    "secret_like": ["sk-abcdefghijklmnop1234", "ghp_abcdefghijklmnopqrstuv", "AKIAABCDEFGHIJKLMNOP"],
}
_MUST_PASS: list[str] = [
    "lt5", "5to9", "10plus", "protect_focus_block", "batch_similar_work", "add_review_slot", "auto_hold_scheduling", "offcomputer_break",
    "reduce_back_to_back", "benefits-processor", "data-analyst", "programmer", "READ", "ENTER", "COMPARE", "meeting_h", "focus_blocks_60",
    "back_to_back_runs", "work_span_h", "n_commits", "huge_commits", "no_tests", "fix_after_fix", "practice", "automate", "agent_result",
    "calendar.suggestion_wording", "git.habit_wording", "briefing.card_wording", "digest.meta", "0.3", "14.08", "bugfix", "refactor",
]


def backstop_corpus(seed: int = 7) -> dict[str, Any]:
    caught: dict[str, dict[str, int]] = {}
    for rule, samples in _MUST_CATCH.items():
        hit = sum(1 for s in samples if rule in patterns.scan_text(s, names=False))
        caught[rule] = {"samples": len(samples), "caught": hit}
    fp = [s for s in _MUST_PASS if patterns.scan_text(s)]
    rng = random.Random(seed)
    hashes = ["".join(rng.choice("0123456789abcdef") for _ in range(rng.randint(4, 16))) for _ in range(5000)]
    hash_fp = sum(1 for h in hashes if patterns.scan_text(f"h:{h}", names=False) or patterns.scan_text(f"d:{h}", names=False))
    sens_ok = all(patterns.scan_text(n.upper(), pii=False) for n in ("password_hint", "api_key", "token_count", "national_insurance", "card_number"))
    return {"must_catch": caught, "must_catch_total": sum(v["samples"] for v in caught.values()),
            "must_catch_caught": sum(v["caught"] for v in caught.values()),
            "ordinary_values": len(_MUST_PASS), "ordinary_false_positives": len(fp), "ordinary_false_positive_values": fp,
            "hashed_ids_tested": len(hashes), "hashed_id_false_positives": hash_fp, "sensitive_snake_case_names_matched": sens_ok}


# ----------------------------------------------------------------------------------------------------- images (REQ-5)
IMAGE_ROW_KEYS = frozenset({"id", "t", "kind", "status", "purpose", "schema", "method", "fields", "payload", "image", "source", "provider",
                            "model", "bytes", "mock", "ok", "latency_ms", "input_tokens", "output_tokens", "cost_estimate_usd", "error",
                            "reason"})
IMAGE_META_KEYS = frozenset({"sha8", "bytes", "width", "height", "kind", "mime", "source"})
_GOOD_GLANCE = {"mode": "triggered", "trigger": "stuck", "strict": False}

IMAGE_CAVEATS = [
    {"id": "img_raw_by_nature", "severity": "high",
     "text": "A screen frame is raw content. The guard decides whether a frame may leave, from which kind of source, what may come back and "
             "what is ever recorded; it does not redact or generalise pixels, and when a frame is allowed the provider sees everything on "
             "the screen. What a provider does with a frame it received is the provider's policy and is not measured here."},
    {"id": "img_answer_closed_not_sight", "severity": "medium",
     "text": "Closed answer schemas (every string is an enum) stop text read off the screen from coming back. They cannot stop the model "
             "from seeing it."},
    {"id": "img_memory_best_effort", "severity": "medium",
     "text": "A frame is held in a buffer that is wiped after the call and is never written by this layer. Copies handed to a provider SDK "
             "or the HTTP stack, and freed memory the interpreter has not reused, cannot be wiped or controlled from here; swap and core "
             "dumps are outside this check."},
    {"id": "img_scan_exact", "severity": "medium",
     "text": "The residue scan looks for the planted PNG's raw bytes, the token written into its metadata, its full SHA-256, and base64 or "
             "hex renderings of the file. It cannot see pixels, a re-encoded copy (a JPEG of the same frame), or a description of the frame."},
    {"id": "img_gate_is_caller_truth", "severity": "high",
     "text": "The gate is a pure function of four booleans and a source that the caller computes. The guard cannot check that secure input or "
             "a denylisted app was detected correctly, or that a frame really came from the source it declares."},
    {"id": "img_sandbox_convention", "severity": "high",
     "text": "ENFORCED: the Python awareness package and the awareness, Live and hotkey TypeScript may not contain the string 'sandbox' "
             "(static scan, test files skipped); the frame route can refuse another machine, an unknown source, and a sandbox claim from a "
             "web page whose Origin is not one of our sandbox sites (frame_request_problem). BY CONVENTION ONLY: a local process on this Mac "
             "sends no Origin header, so the route cannot tell the Electron main process from the agent service; a local process that wrongly "
             "declares sandbox is not stopped, only visible in the ledger's source column."},
    {"id": "img_old_ts_provider_code", "severity": "medium",
     "text": "Old project TypeScript under apps/desktop still names Gemini and OpenAI hosts behind flags (listed in static_guard_ts_references, "
             "report only). The rule is that frames reach a provider through the engine's egress guard; the Python tree is checked for it, the "
             "TypeScript is not enforced."},
    {"id": "img_no_real_provider", "severity": "medium",
     "text": "No real provider was called: a capturing port and a fake client check request shapes and the guard. Gemini and OpenAI behaviour "
             "(latency, accuracy, cost) is the MODELS track's own measurement."},
]


def _gate_reference(consent: bool, deny: bool, secure: bool, unattended: bool, source: str) -> str | None:
    """An independent restatement of the gate rules, for checking ``ImageGate`` against."""
    if source == "real_screen":
        for cond, name in ((unattended, "unattended"), (secure, "secure_input"), (deny, "denylisted_app"), (not consent, "no_consent")):
            if cond:
                return name
        return None
    for cond, name in ((secure, "secure_input"), (deny, "denylisted_app")):
        if cond:
            return name
    return None


def image_evaluation(seeds: Iterable[int] = tuple(range(8))) -> dict[str, Any]:
    """Run the image flows with a planted PNG per seed and report: sends, gate blocks by reason, failures, and every place the planted
    image could have left a residue (files, temp files, log records, error messages, ledger rows). Offline; isolated data dir."""
    from .canary import plant_image, scan_image_residue
    from .egress import ImageBlocked, ImageRejected, send_image
    from .image import ImageGate, SafeImage, register_image_purpose, unregister_image_purpose
    from .payload import PurposeError, SafePayload
    from .testing import LogCapture

    seeds = list(seeds)
    with _isolated_data_dir():
        from ._paths import data_dir

        root = data_dir()
        tmpmon = root / "_tmpmon"
        tmpmon.mkdir(parents=True, exist_ok=True)
        old_tmp = tempfile.tempdir
        tempfile.tempdir = str(tmpmon)
        stats: dict[str, Any] = {"runs": 0, "attempts": 0, "refused_before_send": 0, "failed_calls": 0, "output_rejected": 0,
                                 "port_calls_when_blocked": 0, "unattended_real_screen_attempts": 0, "unattended_real_screen_sent": 0,
                                 "residue": [], "log_records": 0, "error_messages": 0, "files_scanned": 0}
        flows_run: list[str] = []
        try:
            for seed in seeds:
                pi = plant_image(seed)
                errors: list[str] = []
                with LogCapture() as logs:
                    def attempt(name: str, fn: Any) -> None:
                        stats["runs"] += 1
                        stats["attempts"] += 1
                        if name not in flows_run:
                            flows_run.append(name)
                        try:
                            fn()
                        except Exception as exc:     # every refusal and failure is expected here; keep only its text for the scan
                            errors.append(f"{type(exc).__name__}: {exc}")

                    open_gate = ImageGate(True, False, False, False)
                    attempt("sent_real_screen", lambda: send_image("glance.screen_state", pi.safe_image(), _GOOD_GLANCE, gate=open_gate,
                                                                   port=CapturingPort().with_usage(input_tokens=300, output_tokens=30, cost_estimate_usd=0.0002)))
                    attempt("sent_sandbox_unattended", lambda: send_image(
                        "verify.agent_run", pi.safe_image("verify", "sandbox"), {"check": "page_shows_result"},
                        gate=ImageGate(False, False, False, True, "sandbox"), port=CapturingPort()))
                    for gate in (ImageGate(False, False, False, False), ImageGate(True, True, False, False), ImageGate(True, False, True, False),
                                 ImageGate(True, False, False, True)):
                        port = CapturingPort()
                        if gate.unattended:
                            stats["unattended_real_screen_attempts"] += 1
                        attempt(f"blocked_{gate.reason()}", lambda g=gate, p=port: send_image("glance.screen_state", pi.safe_image(), _GOOD_GLANCE, gate=g, port=p))
                        stats["port_calls_when_blocked"] += len(port)
                        if gate.unattended:
                            stats["unattended_real_screen_sent"] += len(port)

                    class _Boom(CapturingPort):
                        def vision(self, image, prompt, schema=None):  # noqa: A003
                            raise RuntimeError("upstream said " + base64.b64encode(image[:60]).decode() + " " + repr(image[:40]))

                    attempt("provider_fails", lambda: send_image("glance.screen_state", pi.safe_image(), _GOOD_GLANCE, gate=open_gate, port=_Boom()))
                    attempt("answer_with_free_text", lambda: send_image(
                        "glance.screen_state", pi.safe_image(), _GOOD_GLANCE, gate=open_gate,
                        port=CapturingPort().script("vision", {"app_kind": pi.token, "task_phase": "start", "blocker": "none", "confidence": 1})))
                    attempt("free_text_beside_frame", lambda: send_image("glance.screen_state", pi.safe_image(), {**_GOOD_GLANCE, "mode": pi.token},
                                                                         gate=open_gate, port=CapturingPort()))
                    attempt("frame_too_large", lambda: SafeImage(pi.data + b"\x00" * (410 * 1024), "glance"))
                    attempt("declared_size_lies", lambda: SafeImage(pi.data, "glance", width=7, height=7))
                    logging.getLogger("understudy.privacy.eval").info("image flows done for one planted frame (%s)", "capture is live")
                rows = ledger.read_all()
                for r in rows:
                    if set(r) - IMAGE_ROW_KEYS or (r.get("image") and set(r["image"]) - IMAGE_META_KEYS):
                        stats["residue"].append(f"seed {seed}: a ledger row has a field outside the allowed set")
                stats["log_records"] += len(logs.texts)
                stats["error_messages"] += len(errors)
                found = scan_image_residue(pi, paths=[root, ], texts=logs.texts + errors + [json.dumps(rows)])
                found = [f for f in found if "_tmpmon" not in f]
                stats["residue"].extend(f"seed {seed}: {f}" for f in found)
                stats["files_scanned"] += sum(1 for p in root.rglob("*") if p.is_file())
                left = [p.name for p in tmpmon.iterdir()]
                if left:
                    stats["residue"].append(f"seed {seed}: {len(left)} temporary file(s) left behind")
            rows = ledger.read_all()
            image_rows = [r for r in rows if r.get("kind") == "image"]
            blocked: dict[str, int] = {}
            for r in image_rows:
                if r.get("status") == "blocked":
                    blocked[str(r["reason"])] = blocked.get(str(r["reason"]), 0) + 1
            by_status: dict[str, int] = {}
            for r in image_rows:
                by_status[str(r.get("status"))] = by_status.get(str(r.get("status")), 0) + 1
            physical = [json.loads(x) for x in (root / "egress_ledger.jsonl").read_text().splitlines() if x.strip()] if (root / "egress_ledger.jsonl").exists() else []
            one_row_per_call = len(image_rows) == sum(1 for x in physical if x.get("kind") == "image")

            controls: list[dict[str, Any]] = []

            def control(name: str, expected: str, fn: Any) -> None:
                try:
                    observed, ok = fn()
                except Exception as exc:  # pragma: no cover
                    observed, ok = f"control raised {type(exc).__name__}", False
                controls.append({"name": name, "expected": expected, "observed": observed, "passed": bool(ok)})

            ctl = plant_image(99)

            def log_dump() -> tuple[str, bool]:
                with LogCapture() as lc:
                    logging.getLogger("control").info("frame %s", base64.b64encode(ctl.data).decode())
                f = scan_image_residue(ctl, texts=lc.texts)
                return (f"{len(f)} hit(s)", bool(f))

            def file_dump() -> tuple[str, bool]:
                p = root / "_control_dump.bin"
                p.write_bytes(ctl.data)
                try:
                    f = scan_image_residue(ctl, paths=[root])
                finally:
                    p.unlink()
                return (f"{len(f)} hit(s)", bool(f))

            def hash_in_name() -> tuple[str, bool]:
                p = root / f"{hashlib.sha256(ctl.data).hexdigest()}.cache"
                p.write_text("x")
                try:
                    f = scan_image_residue(ctl, paths=[root])
                finally:
                    p.unlink()
                return (f"{len(f)} hit(s)", bool(f))

            def tmp_file() -> tuple[str, bool]:
                fd, name = tempfile.mkstemp()
                os.write(fd, ctl.data)
                os.close(fd)
                left = os.listdir(tmpmon)
                os.unlink(name)
                return (f"{len(left)} temporary file(s) seen", len(left) == 1)

            def free_schema() -> tuple[str, bool]:
                class P(SafePayload):
                    n: int = 0

                bad = {"type": "object", "additionalProperties": False, "properties": {"text": {"type": "string"}}, "required": ["text"]}
                try:
                    register_image_purpose("control.free_text", P, response_schema=bad, kinds=("glance",))
                except PurposeError:
                    return ("PurposeError at registration", True)
                unregister_image_purpose("control.free_text")
                return ("registered", False)

            def unattended_real() -> tuple[str, bool]:
                class Remote:
                    name = "gemini"
                    calls = 0

                    def vision(self, *a, **k):
                        Remote.calls += 1
                        return {}

                ok = True
                for consent, deny, secure in itertools.product([True, False], repeat=3):
                    try:
                        send_image("glance.screen_state", ctl.safe_image(), _GOOD_GLANCE, gate=ImageGate(consent, deny, secure, True), port=Remote())
                        ok = False
                    except ImageBlocked as exc:
                        ok = ok and exc.reason == "unattended"
                return (f"8 combinations blocked, provider calls: {Remote.calls}", ok and Remote.calls == 0)

            def source_mismatch() -> tuple[str, bool]:
                try:
                    send_image("verify.agent_run", ctl.safe_image("verify", "sandbox"), {"check": "form_saved"}, gate=ImageGate(True, False, False, False), port=CapturingPort())
                except ImageRejected:
                    return ("ImageRejected", True)
                return ("sent", False)

            control("a frame dumped into a log record as base64 is found by the residue scan", "found", log_dump)
            control("a frame written into the data directory is found", "found", file_dump)
            control("a file named by the frame's full hash is found", "found", hash_in_name)
            control("a temporary file holding a frame is seen by the temp-file check", "seen", tmp_file)
            control("an image purpose whose answer could carry free text cannot be registered", "PurposeError", free_schema)
            control("unattended + real_screen never reaches a provider, with or without consent", "blocked in 8 of 8", unattended_real)
            control("an image declaring a different source than its gate is refused", "ImageRejected", source_mismatch)

            gate_cases = fails = 0
            for source in ("real_screen", "sandbox"):
                for consent, deny, secure, unattended in itertools.product([True, False], repeat=4):
                    gate_cases += 1
                    fails += 0 if ImageGate(consent, deny, secure, unattended, source).reason() == _gate_reference(consent, deny, secure, unattended, source) else 1
            gate_cases += 1
            fails += 0 if all(ImageGate(c, d, s, True).reason() == "unattended" for c, d, s in itertools.product([True, False], repeat=3)) else 1
            summary = ledger.summary()["images"]
        finally:
            tempfile.tempdir = old_tmp
    from . import guard as _guard

    prov = _guard.scan_provider_endpoints()
    claims = _guard.scan_sandbox_claims()
    return {
        "runs": stats["runs"], "seeds": len(seeds), "flows": flows_run, "frames_planted": len(seeds),
        "sent": by_status.get("ok", 0), "blocked_by_reason": dict(sorted(blocked.items())), "provider_failed": by_status.get("failed", 0),
        "output_rejected": by_status.get("output_rejected", 0),
        "unattended_real_screen": {"attempts": stats["unattended_real_screen_attempts"], "reached_a_provider": stats["unattended_real_screen_sent"]},
        "provider_calls_after_a_block": stats["port_calls_when_blocked"],
        "leaks": len(stats["residue"]), "leak_details": stats["residue"][:10],
        "scanned": {"data_dir_files": stats["files_scanned"], "log_records": stats["log_records"], "error_messages": stats["error_messages"],
                    "ledger_rows": len(rows), "temp_dir": "empty after every seed" if not any("temporary file" in r for r in stats["residue"]) else "files left"},
        "ledger": {"image_rows": len(image_rows), "one_row_per_call": one_row_per_call, "physical_lines": len(physical),
                   "rows_with_disallowed_fields": len([r for r in stats["residue"] if "outside the allowed set" in r]), "summary": summary},
        "gate": {"cases": gate_cases, "failures": fails},
        "controls": controls,
        "static_guard": {"provider_endpoint_files": len(prov.files), "provider_endpoint_violations": [str(v) for v in prov.violations],
                         "sandbox_claim_files": len(claims.files), "sandbox_claim_violations": [str(v) for v in claims.violations],
                         "ts_provider_references": _guard.ts_provider_references()},
        "caveats": IMAGE_CAVEATS,
    }


# ----------------------------------------------------------------------------------------------------- the evaluation
@contextlib.contextmanager
def _isolated_data_dir() -> Iterable[None]:
    """A temporary data dir for the duration of the run, restored afterwards (the real ledger is never written)."""
    with _env_lock:
        old = os.environ.get("UNDERSTUDY_DATA_DIR")
        with tempfile.TemporaryDirectory(prefix="understudy-privacy-eval-") as tmp:
            os.environ["UNDERSTUDY_DATA_DIR"] = tmp
            try:
                yield
            finally:
                if old is None:
                    os.environ.pop("UNDERSTUDY_DATA_DIR", None)
                else:
                    os.environ["UNDERSTUDY_DATA_DIR"] = old


LIMITATIONS = [
    {"id": "prv_canary_exact", "severity": "medium",
     "text": "The canary scan looks for the exact planted strings, their invented words, simple rewrites (case, separators, URL "
             "encoding, base64, hex). A paraphrase, a translation, a hash or a character-code encoding of a token would not be caught. "
             "The claim measured is: these planted strings did not reach the model port, in these flows."},
    {"id": "prv_leak_bound_unit", "severity": "high",
     "text": "The leak bound is read per RUN, not per token. A leak is a property of a code path, and the many tokens planted in one run share that "
             "path, so they are not independent trials. With 0 leaks the one-sided 95% upper bound is about 3 divided by the number of independent "
             "units: per run (for example 0 of 80) about 3.7%, per flow (0 of 10) about 26%; the token-level figure (0 of thousands, well under "
             "0.1%) assumes independence that does not hold and is shown only for comparison. Eight seeds per flow vary the planted strings, not the "
             "code path, so more seeds do not shrink the per-flow bound."},
    {"id": "prv_flow_coverage", "severity": "high",
     "text": "Reference flows test the privacy layer with stand-in upstream code. Only integration flows test another layer's own code, "
             "and a layer that supplied none is listed as none_registered, not as passed. Zero leaks says nothing about a flow that was not run."},
    {"id": "prv_form_not_meaning", "severity": "medium",
     "text": "A SafePayload limits the form of what is sent (numbers, codes, fixed ids, bucketed values), not its meaning: a bucketed count of "
             "the worker's own meetings is still a fact about the worker. Generalisation reduces precision; it is not anonymisation."},
    {"id": "prv_covert_channel", "severity": "low",
     "text": "Lists of integers could carry text as character codes. Lists are capped at 64 items and integers at 1e9, which bounds that; "
             "the threat model is accidental leakage by honest code, not an author trying to smuggle data out."},
    {"id": "prv_worker_requested", "severity": "medium",
     "text": "Model calls the worker asked for (agent runs, the coach, the quarantined reader) are not routed through the egress guard and "
             "send raw content to the provider by design. They appear in the ledger only as metadata lines when the port is wrapped "
             "(direct.LedgeredPort). The Privacy screen therefore does not claim that nothing else leaves this laptop."},
    {"id": "prv_static_guard", "severity": "low",
     "text": "The static guard is name-based. It does not follow a module name held in a variable and cannot see code added at run time; "
             "it catches honest mistakes such as importing an SDK 'just for wording'."},
    {"id": "prv_synthetic", "severity": "medium",
     "text": "All fixtures are synthetic and the real provider is never called here (a fake client checks only the request shape). "
             "Nothing is validated on real calendars, repositories or accounts."},
    {"id": "prv_ledger_trust", "severity": "low",
     "text": "The ledger is a plain local file the worker can clear (the clear is itself counted). It records what the guard sent; it cannot "
             "record what a module sends by bypassing the guard, which is what the static guard and the canary flows are for."},
]


def guard_battery() -> dict[str, Any]:
    """Run the static guard over its own battery: the reviewer's evasions, further evasions, and clean code that must not be flagged.
    Reports how many evasions each scan catches and how many clean samples it wrongly flags, so "0 violations" is read next to
    "and it can see these"."""
    from . import guard_samples as gs

    def flagged(src: str, path: str) -> bool:
        return bool(guard.scan_source(src, path)[0])

    cases = [(n, src, "calendar/x.py") for n, (src, _) in sorted(gs.REVIEWER_LAYER.items())]
    cases += [(f"extra_{i:02d}", src, "calendar/x.py") for i, (src, _) in enumerate(gs.EXTRA)]
    cases += [(f"round2_{n}", src, "calendar/x.py") for n, src in sorted(gs.ROUND2.items())]
    pure = [(n, src, "mlv2/x.py") for n, (src, _) in sorted(gs.REVIEWER_LAYER.items())]
    agent = [(n, src) for n, src in sorted(gs.REVIEWER_AGENT.items())]
    missed = [n for n, src, path in cases + pure if not flagged(src, path)]
    missed += [f"agent:{n}" for n, src in agent if not guard.scan_agent_source(src, "understudy_agent/voice/x.py")[0]]
    runtime_missed = [n for n, src in agent if not guard.scan_runtime_source(src, "runtime/x.py")]
    false_pos = [i for i, src in enumerate(gs.CLEAN + [gs.ROUND2_CONTROL]) if flagged(src, "calendar/x.py")]
    false_pos += [f"agent:{i}" for i, src in enumerate(gs.AGENT_CLEAN) if guard.scan_agent_source(src, "understudy_agent/tiers/x.py")[0]]
    total = len(cases) + len(pure) + len(agent)
    return {"evasion_cases": total, "flagged": total - len(missed), "missed": missed, "runtime_cases": len(agent),
            "runtime_missed": runtime_missed, "clean_controls": len(gs.CLEAN) + 1 + len(gs.AGENT_CLEAN), "clean_flagged": len(false_pos),
            "sources": {"reviewer_layer": len(gs.REVIEWER_LAYER), "reviewer_agent": len(gs.REVIEWER_AGENT), "reviewer_round2": len(gs.ROUND2),
                        "further": len(gs.EXTRA)},
"limits": ("THIS IS A STATIC NET FOR HONEST MISTAKES, NOT A SANDBOX. A string computed at run time (read from a file or the environment, chr() "
                       "arithmetic, a base64 blob) is not folded, so a fetcher or host hidden that way is not seen; unfoldable arguments of dynamic "
                       "import, exec and eval and unreadable process commands are flagged instead; an alias of a model method made through a "
                       "second variable (y = x.plan) is not followed; a write path built from the environment is not checked. The extension "
                       "layers are held to an import allowlist; the agent package is not (it browses by design). The real defence is "
                       "egress.send, egress.send_image and the ledger, and the canary flows that measure them.")}


def coverage_table(layers: dict[str, dict[str, Any]], rows: list[dict[str, Any]], guard_rep: Any, runtime_rep: Any,
                   image_layer_flows: list[dict[str, Any]] | None = None, agent_rep: Any = None) -> list[dict[str, Any]]:
    """One row per guarded layer for the Evidence map: is the directory there, how many of its files the static guard read and with how
    many violations, and whether a real-code canary flow was run for it. ``registered`` = the layer supplied its own flow; ``adapter`` =
    the privacy layer wraps the layer's real entry point; ``pure_compute`` = no model or network path by rule (the static guard is the
    control); ``none_registered`` is a gap and is never counted as covered; ``not_present`` = the directory does not exist yet."""
    out: list[dict[str, Any]] = []
    image_layer_flows = image_layer_flows or []
    for layer in guard.GUARDED_DIRS:
        info = layers.get(layer, {"status": "not_checked", "flows": []})
        present = (guard.ENGINE_PKG / layer).is_dir()
        files = [f for f in guard_rep.files if f.startswith(layer + "/")]
        viol = [v for v in guard_rep.violations if v.file.startswith(layer + "/")]
        mine = [r for r in rows if r["flow"] in info.get("flows", []) and r["kind"] == "integration"]
        img_mine = [f for f in image_layer_flows if f["flow"] in info.get("image_flows", [])]
        status = info["status"] if present else "not_present"
        out.append({
            "layer": layer, "present": present, "pure_compute": layer in guard.PURE_COMPUTE_DIRS, "files_scanned": len(files),
            "static_guard_violations": len(viol), "canary_flow": status, "flows": [r["flow"] for r in mine],
            "registered_by_layer": status == "registered", "real_code_flow": status in ("registered", "adapter") and bool(mine or img_mine),
            "image_flows": [f["flow"] for f in img_mine], "image_runs": sum(f["runs"] for f in img_mine),
            "image_residue": sum(f["residue"] for f in img_mine),
            "runs": sum(r["seeds"] for r in mine), "requests": sum(r["requests"] for r in mine), "planted": sum(r["planted"] for r in mine),
            "leaked": sum(r["leaked"] for r in mine), "note": info.get("note"),
        })
    rt_files = list(runtime_rep.files)
    out.append({
        "layer": "agent_runtime", "present": bool(rt_files), "pure_compute": False, "files_scanned": len(rt_files),
        "static_guard_violations": len(runtime_rep.violations), "canary_flow": "none_registered" if rt_files else "not_present", "flows": [],
        "registered_by_layer": False, "real_code_flow": False, "image_flows": [], "image_runs": 0, "image_residue": 0, "runs": 0,
        "requests": 0, "planted": 0, "leaked": 0,
        "note": "services/agent runtime: children have no network (the scan allows none), it plans through egress.send and records worker-requested "
                "calls; its own leak tests live in services/agent/tests/runtime and are not run by this evaluation",
    })
    if agent_rep is not None:
        for pref in guard.AGENT_PURE_PREFIXES:
            name = pref.split("/")[1]
            pfiles = [f for f in agent_rep.files if f.startswith(pref)]
            pviol = [v for v in agent_rep.violations if v.file.startswith(pref)]
            out.append({"layer": name, "present": bool(pfiles), "pure_compute": True, "files_scanned": len(pfiles), "static_guard_violations": len(pviol),
                        "canary_flow": "pure_compute" if pfiles else "not_present", "flows": [], "registered_by_layer": False, "real_code_flow": False,
                        "image_flows": [], "image_runs": 0, "image_residue": 0, "runs": 0, "requests": 0, "planted": 0, "leaked": 0,
                        "note": f"services/agent/{pref.rstrip('/')}: pure compute by rule (no model client, no network, no process, no URL, no reviewed exception); "
                                "the static guard is the control"})
        ag_files = list(agent_rep.files)
        pend = guard.pending_exceptions()
        out.append({
            "layer": "agent_service", "present": bool(ag_files), "pure_compute": False, "files_scanned": len(ag_files),
            "static_guard_violations": len(agent_rep.violations), "canary_flow": "static_guard_only" if ag_files else "not_present", "flows": [],
            "registered_by_layer": False, "real_code_flow": False, "image_flows": [], "image_runs": 0, "image_residue": 0, "runs": 0, "requests": 0,
            "planted": 0, "leaked": 0,
            "note": (f"every module of services/agent outside models/ and runtime/ is statically scanned for network use; {len(guard.AGENT_ALLOW)} files "
                     f"have a reviewed entry (loopback clients must carry a literal 127.0.0.1 or localhost); {len(pend)} exception(s) are pending, not "
                     "accepted. Legacy desktop TypeScript still calls providers itself (see image.static_guard.ts_provider_references); those calls are "
                     "on the ledger only if the caller reports them to POST /privacy/ledger/direct, which nothing here can force."),
        })
    return out


def evaluate_privacy(*, seeds: Iterable[int] = tuple(range(8)), record: bool = True, extra_flows: Iterable[CanaryFlow] = (),
                     discover: bool = True) -> dict[str, Any]:
    """Run the full privacy evaluation and return a JSON-ready dict (see the module docstring). ``record=True`` writes the
    aggregate canary result to ``<data dir>/privacy_canary.json`` for ``GET /privacy/summary``."""
    seeds = list(seeds)
    flows = list(reference_flows()) + list(extra_flows)
    layers: dict[str, dict[str, Any]] = {}
    if discover:
        found, layers = discover_flows()
        flows += found

    per_run: list[FlowResult] = []
    with _isolated_data_dir():
        for fl in flows:
            for s in seeds:
                per_run.append(run_flow(fl, seed=s))
        controls = negative_controls()
        ledger_lines_total = len(ledger.read_all())

    rows: list[dict[str, Any]] = []
    for fl in flows:
        rs = [r for r in per_run if r.name == fl.name]
        planted, leaked = sum(r.planted for r in rs), sum(r.leaked for r in rs)
        rows.append({
            "flow": fl.name, "layer": fl.layer, "kind": fl.kind, "status": "ran" if all(r.error is None or r.requests for r in rs) else "error",
            "seeds": len(rs), "requests": sum(r.requests for r in rs), "planted": planted, "leaked": leaked,
            "runs_with_leak": sum(1 for r in rs if r.leaked or r.artifact_leaked),
            "leak_rate_upper_95": round(upper_bound_95(sum(1 for r in rs if r.leaked or r.artifact_leaked), len(rs)), 4) if rs else None,
            "leak_rate_upper_95_token_level": round(upper_bound_95(leaked, planted), 4) if planted else None,
            "ledger_lines": sum(r.ledger_lines for r in rs), "ledger_expected": sum(r.ledger_expected for r in rs),
            "ledger_complete": all(r.ledger_complete for r in rs), "flow_errors": sorted({r.error for r in rs if r.error}),
            "meets_min_requests": all(r.requests >= fl.min_requests for r in rs),
            "artifact_files_scanned": sum(r.artifact_files for r in rs), "artifact_log_records_scanned": sum(r.artifact_log_records for r in rs),
            "artifact_leaked": sum(r.artifact_leaked for r in rs),
            "planted_by_kind": _sum_dicts([r.by_kind for r in rs]), "leaked_kinds": sorted({k for r in rs for k in r.leaked_kinds}),
            "notes": sorted({r.note for r in rs if r.note})[:3],
        })

    def agg(kind: str | None) -> dict[str, Any]:
        sel = [r for r in rows if kind is None or r["kind"] == kind]
        planted, leaked = sum(r["planted"] for r in sel), sum(r["leaked"] for r in sel)
        runs, leaked_runs = sum(r["seeds"] for r in sel), sum(r["runs_with_leak"] for r in sel)
        flows_n, leaked_flows = len(sel), sum(1 for r in sel if r["runs_with_leak"])
        return {"flows": flows_n, "runs": runs, "requests": sum(r["requests"] for r in sel), "planted": planted, "leaked": leaked,
                "runs_with_leak": leaked_runs, "flows_with_leak": leaked_flows,
                # the headline bound is per RUN: a leak is a property of a code path, and tokens planted in one run share that path
                "leak_rate_upper_95": round(upper_bound_95(leaked_runs, runs), 4) if runs else None, "leak_bound_unit": "run",
                "leak_rate_upper_95_per_flow": round(upper_bound_95(leaked_flows, flows_n), 4) if flows_n else None,
                "leak_rate_upper_95_token_level": round(upper_bound_95(leaked, planted), 4) if planted else None,
                "ledger_complete": all(r["ledger_complete"] for r in sel) if sel else None,
                "all_meet_min_requests": all(r["meets_min_requests"] for r in sel) if sel else None,
                "artifact_files_scanned": sum(r["artifact_files_scanned"] for r in sel), "artifact_leaked": sum(r["artifact_leaked"] for r in sel)}

    guard_rep = guard.scan_tree()
    runtime_rep = guard.scan_runtime()
    agent_rep = guard.scan_agent()
    battery = guard_battery()
    image_block = image_evaluation()
    image_layer_flows: list[dict[str, Any]] = []
    if discover:
        with _isolated_data_dir():
            for fl in discover_image_flows():
                res = [image_canary_flow(fl.name, fl.run, seed=sd, strict=False) for sd in seeds]
                image_layer_flows.append({"flow": fl.name, "layer": fl.layer, "runs": len(res), "requests": sum(x["requests"] for x in res),
                                          "residue": sum(len(x["residue"]) for x in res), "residue_details": [d for x in res for d in x["residue"]][:5]})
    image_block["layer_flows"] = image_layer_flows
    image_block["leaks"] += sum(f["residue"] for f in image_layer_flows)
    image_block["runs"] += sum(f["runs"] for f in image_layer_flows)
    image_block["leak_rate_upper_95_per_run"] = round(upper_bound_95(1 if image_block["leaks"] else 0, image_block["runs"]), 4) if image_block["runs"] else None
    image_block["leak_bound_unit"] = "run"
    props = bucketing_properties()
    sensitivity = scan_sensitivity()
    specificity = scan_specificity()
    corpus = backstop_corpus()
    total = agg(None)
    not_covered = [layer for layer, v in layers.items() if v["status"] in ("none_registered", "error")]
    coverage = coverage_table(layers, rows, guard_rep, runtime_rep, image_layer_flows, agent_rep)
    cov_summary = {
        "layers": len([c for c in coverage if c["layer"] != "agent_runtime"]),
        "with_real_code_flow": [c["layer"] for c in coverage if c["real_code_flow"]],
        "pure_compute": [c["layer"] for c in coverage if c["canary_flow"] == "pure_compute"],
        "not_present": [c["layer"] for c in coverage if c["canary_flow"] == "not_present"],
        "gaps": [c["layer"] for c in coverage if c["canary_flow"] in ("none_registered", "error", "not_checked")],
        "static_guard_only": [c["layer"] for c in coverage if c["canary_flow"] == "static_guard_only"],
    }
    data = {
        "meta": {"origin": "synthetic", "n": total["planted"], "n_unit": "tokens", "split": None, "interval_level": 0.95,
                 "note": ("Synthetic fixtures with planted canaries, a capturing fake model port, an isolated data directory. "
                          f"{len(seeds)} seeds per flow. Reference flows test the guard; integration flows test a layer's real code."),
                 "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")},
        "headline": {**total, "leak_bound_note": "per-run bound is the headline; per-flow and token-level bounds are beside it (see limitation prv_leak_bound_unit)",
                     "controls_passed": sum(1 for c in controls if c["passed"]), "controls_total": len(controls),
                     "layers_without_integration_flows": not_covered, "coverage_summary": cov_summary,
                     "artifact_files_scanned": total["artifact_files_scanned"], "artifact_leaked": total["artifact_leaked"],
                     "bucketing_failures": sum(r["failures"] for r in props), "bucketing_cases": sum(r["cases"] for r in props),
                     "static_guard_violations": len(guard_rep.violations) + len(runtime_rep.violations) + len(agent_rep.violations),
                     "static_guard_files": len(guard_rep.files) + len(runtime_rep.files) + len(agent_rep.files),
                     "static_guard_evasions_flagged": f"{battery['flagged']}/{battery['evasion_cases']}",
                     "static_guard_clean_flagged": battery["clean_flagged"],
                     "pending_exceptions": len(guard.pending_exceptions()),
                     "vocabulary_problems": len(vocabulary_problems()),
                     "purposes_registered": len([p for p in all_purposes() if not p.startswith("control.")]),
                     "backstop_must_catch": f"{corpus['must_catch_caught']}/{corpus['must_catch_total']}",
                     "image_runs": image_block["runs"], "image_leaks": image_block["leaks"],
                     "image_blocked_by_reason": image_block["blocked_by_reason"],
                     "image_controls_passed": f"{sum(1 for c in image_block['controls'] if c['passed'])}/{len(image_block['controls'])}",
                     "scan_detects_known_rewrites": f"{sensitivity['detected']}/{sensitivity['cases']}",
                     "scan_false_positives": specificity["false_positives"],
                     "backstop_false_positives": corpus["ordinary_false_positives"] + corpus["hashed_id_false_positives"]},
        "by_kind": {"reference": agg("reference"), "integration": agg("integration")},
        "flows": rows,
        "layers": layers,
        "coverage": coverage,
        "negative_controls": controls,
        "bucketing": props,
        "backstop": corpus,
        "scan_sensitivity": sensitivity, "scan_specificity": specificity,
        "static_guard": {"files": len(guard_rep.files), "violations": [str(v) for v in guard_rep.violations],
                         "allowed_uses": sorted(set(guard_rep.allowed_uses)), "scanned_dirs": list(guard.GUARDED_DIRS),
                         "runtime": {"files": len(runtime_rep.files), "violations": [str(v) for v in runtime_rep.violations],
                                     "rule": "no network of any kind (children are sandboxed) and no reviewed exceptions; every visible direct model call "
                                             "records a metadata-only ledger line"},
                         "agent": {"files": len(agent_rep.files), "violations": [str(v) for v in agent_rep.violations],
                                   "allowed_uses": sorted(set(agent_rep.allowed_uses)),
                                   "reviewed_entries": {k: v.reason for k, v in guard.AGENT_ALLOW.items()},
                                   "rule": "every module outside models/ and runtime/ is scanned; network use needs a reviewed entry with a reason and, for a "
                                           "loopback client, a literal 127.0.0.1 or localhost in the module"},
                         "pending_exceptions": guard.pending_exceptions(), "battery": battery},
        "ledger": {"lines_written_during_evaluation": ledger_lines_total},
        "image": image_block,
        "purposes": [p.public() for p in all_purposes().values() if not p.name.startswith("control.")],
        "vocabulary_problems": vocabulary_problems(),
        "limitations": LIMITATIONS + IMAGE_CAVEATS,
    }
    if record:
        for r in rows:
            canary.record_totals(r["flow"], requests=r["requests"], planted=r["planted"], leaked=r["leaked"], by_kind=r["planted_by_kind"])
    return json.loads(json.dumps(data))


def _sum_dicts(ds: list[dict[str, int]]) -> dict[str, int]:
    out: dict[str, int] = {}
    for d in ds:
        for k, v in d.items():
            out[k] = out.get(k, 0) + v
    return out
