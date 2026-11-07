"""Honest evaluation of the privacy layer (NFR-11): ``evaluate_privacy() -> dict`` for the eval harness.

What it measures, and what it does not claim
--------------------------------------------
* **Canary leaks.** Each registered flow is run several times, each with fresh fixtures seeded with unique planted tokens
  (person names, emails, meeting titles, file paths, commit messages, customer names), against a ``CapturingPort`` that records
  every request body. The measurement is: how many planted tokens appear in any captured request. A one-sided exact
  (Clopper-Pearson) 95% upper bound on the leak rate is reported with the count.
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
* **Backstop corpus.** Shapes it must catch (by rule) and ordinary vocabulary it must not flag.
* **Static guard.** Modules scanned and violations, from ``guard.scan_tree``.

Everything runs offline on synthetic fixtures in a temporary data directory (the real ledger is not touched); the aggregate is
recorded for ``GET /privacy/summary`` only when ``record=True``. Nothing here validates behaviour on real data, and
the real provider is never called.
"""
from __future__ import annotations

import contextlib
import importlib
import json
import os
import random
import tempfile
import threading
from datetime import datetime, timezone
from typing import Any, Iterable

from . import bucket as B
from . import canary, egress, guard, ledger, patterns
from .egress import EgressError
from .payload import PurposeError, UnsafeFieldError, get_purpose
from .purposes import BriefingCardWording, CalendarSuggestionWording, DigestMeta, GitHabitWording
from .testing import CanaryFlow, CapturingPort, FlowResult, run_flow

_env_lock = threading.RLock()
LAYERS = ("calendar", "gitanalysis", "proactive", "localmodel", "plugins")


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
            layers[layer] = {"status": "registered" if got else "none_registered", "flows": [f.name for f in got]}
        except ModuleNotFoundError as exc:
            layers[layer] = {"status": "none_registered", "flows": [], "note": "no canary_flows module"} if exc.name == name else \
                {"status": "error", "flows": [], "note": f"import failed: {exc.name}"}
        except Exception as exc:  # a broken layer must not break the evaluation
            layers[layer] = {"status": "error", "flows": [], "note": f"{type(exc).__name__} while importing"}
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
            "leak_rate_upper_95": round(upper_bound_95(leaked, planted), 4) if planted else None,
            "ledger_lines": sum(r.ledger_lines for r in rs), "ledger_expected": sum(r.ledger_expected for r in rs),
            "ledger_complete": all(r.ledger_complete for r in rs), "flow_errors": sorted({r.error for r in rs if r.error}),
            "meets_min_requests": all(r.requests >= fl.min_requests for r in rs),
            "planted_by_kind": _sum_dicts([r.by_kind for r in rs]), "leaked_kinds": sorted({k for r in rs for k in r.leaked_kinds}),
            "notes": sorted({r.note for r in rs if r.note})[:3],
        })

    def agg(kind: str | None) -> dict[str, Any]:
        sel = [r for r in rows if kind is None or r["kind"] == kind]
        planted, leaked = sum(r["planted"] for r in sel), sum(r["leaked"] for r in sel)
        return {"flows": len(sel), "runs": sum(r["seeds"] for r in sel), "requests": sum(r["requests"] for r in sel), "planted": planted,
                "leaked": leaked, "leak_rate_upper_95": round(upper_bound_95(leaked, planted), 4) if planted else None,
                "ledger_complete": all(r["ledger_complete"] for r in sel) if sel else None,
                "all_meet_min_requests": all(r["meets_min_requests"] for r in sel) if sel else None}

    guard_rep = guard.scan_tree()
    props = bucketing_properties()
    corpus = backstop_corpus()
    total = agg(None)
    not_covered = [layer for layer, v in layers.items() if v["status"] in ("none_registered", "error")]
    data = {
        "meta": {"origin": "synthetic", "n": total["planted"], "n_unit": "tokens", "split": None, "interval_level": 0.95,
                 "note": ("Synthetic fixtures with planted canaries, a capturing fake model port, an isolated data directory. "
                          f"{len(seeds)} seeds per flow. Reference flows test the guard; integration flows test a layer's real code."),
                 "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")},
        "headline": {**total, "controls_passed": sum(1 for c in controls if c["passed"]), "controls_total": len(controls),
                     "layers_without_integration_flows": not_covered,
                     "bucketing_failures": sum(r["failures"] for r in props), "bucketing_cases": sum(r["cases"] for r in props),
                     "static_guard_violations": len(guard_rep.violations), "static_guard_files": len(guard_rep.files),
                     "backstop_must_catch": f"{corpus['must_catch_caught']}/{corpus['must_catch_total']}",
                     "backstop_false_positives": corpus["ordinary_false_positives"] + corpus["hashed_id_false_positives"]},
        "by_kind": {"reference": agg("reference"), "integration": agg("integration")},
        "flows": rows,
        "layers": layers,
        "negative_controls": controls,
        "bucketing": props,
        "backstop": corpus,
        "static_guard": {"files": len(guard_rep.files), "violations": [str(v) for v in guard_rep.violations],
                         "allowed_uses": sorted(set(guard_rep.allowed_uses)), "scanned_dirs": list(guard.GUARDED_DIRS)},
        "ledger": {"lines_written_during_evaluation": ledger_lines_total},
        "purposes": [get_purpose(p).public() for p in ("calendar.suggestion_wording", "git.habit_wording", "briefing.card_wording", "digest.meta")],
        "limitations": LIMITATIONS,
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
