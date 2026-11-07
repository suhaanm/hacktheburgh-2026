"""Test kit for the extension tracks: a capturing fake ``ModelPort`` and a one-call canary flow.

    from understudy_engine.privacy.testing import CapturingPort, canary_flow

    def test_my_flow_leaks_nothing():
        report = canary_flow(
            "calendar.suggestions",
            make_fixtures=lambda: {"events": [{"title": "Quarterly planning", "attendees": ["Ada"], "start": "2026-11-02T09:00"}]},
            run=lambda fx, port: my_suggestions(fx, port=port),     # must send through egress.send(..., port=port)
            min_requests=1,
        )
        assert report.ok

``canary_flow`` plants canaries in fresh fixtures, runs the flow against a ``CapturingPort``, checks that every captured
request has exactly one matching ledger line (and none extra), that no planted token appears in any request, and records the
run so ``GET /privacy/summary`` can show it. Use inside a test that has isolated ``UNDERSTUDY_DATA_DIR``
(``hermetic(monkeypatch, tmp_path)``).
"""
from __future__ import annotations

import copy
import hashlib
import json
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from . import canary, ledger
from ._stub import stub_from_schema


def _canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)


@dataclass
class CapturedRequest:
    """One request as the model would have received it. ``body`` is JSON-ready; ``text`` is its canonical JSON."""

    index: int
    method: str
    body: Any

    @property
    def text(self) -> str:
        return _canonical(self.body)

    @property
    def bytes(self) -> int:
        return len(self.text.encode())


class CapturingPort:
    """A fake ``ModelPort``: records every request body, returns schema-valid stub output, never touches a network.

    ``name == "capturing"`` and ``offline = True``, so the egress guard accepts it in mock mode and marks the ledger line
    ``mock``. ``script("title_or_method", {...})`` queues specific answers (the last repeats); ``fail_with(exc)`` makes the
    next calls raise (to test fail-closed paths).
    """

    name = "capturing"
    offline = True

    def __init__(self, *, stub_text: str = "stub wording") -> None:
        self.requests: list[CapturedRequest] = []
        self.image_calls: list[dict[str, Any]] = []        # {sha256, bytes} per vision call; never the bytes
        self.last_call: dict[str, Any] | None = None       # per-call usage a provider may expose (see image.ImageUsage)
        self._usage: dict[str, Any] | None = None
        self.stub_text = stub_text
        self._scripted: dict[str, list[Any]] = {}
        self._fail: Exception | None = None
        self._lock = threading.Lock()

    # ---- test helpers
    def script(self, key: str, *outputs: Any) -> "CapturingPort":
        """Queue answers for calls whose schema ``title`` (or method name) is ``key``."""
        self._scripted.setdefault(key, []).extend(outputs)
        return self

    def with_usage(self, *, input_tokens: int | None = None, output_tokens: int | None = None,
                   cost_estimate_usd: float | None = None) -> "CapturingPort":
        """Make each vision call report this usage as ``last_call`` (what the MODELS providers will expose)."""
        self._usage = {"input_tokens": input_tokens, "output_tokens": output_tokens, "cost_estimate_usd": cost_estimate_usd}
        return self

    def fail_with(self, exc: Exception | None) -> "CapturingPort":
        self._fail = exc
        return self

    def reset(self) -> None:
        with self._lock:
            self.requests.clear()

    def __len__(self) -> int:
        return len(self.requests)

    def bodies(self) -> list[Any]:
        return [r.body for r in self.requests]

    def texts(self) -> list[str]:
        return [r.text for r in self.requests]

    # ---- internals
    def _record(self, method: str, body: Any) -> None:
        with self._lock:
            self.requests.append(CapturedRequest(len(self.requests), method, copy.deepcopy(body)))
        if self._fail is not None:
            raise self._fail

    def _answer(self, method: str, schema: dict[str, Any] | None) -> Any:
        for key in ((schema or {}).get("title"), method):
            q = self._scripted.get(key) if key else None
            if q:
                return copy.deepcopy(q.pop(0) if len(q) > 1 else q[0])
        return stub_from_schema(schema, text=self.stub_text)

    # ---- ModelPort
    def plan(self, messages: list[dict[str, Any]], schema: dict[str, Any] | None = None) -> Any:
        self._record("plan", {"messages": messages, "schema": schema})
        return self._answer("plan", schema)

    def read(self, untrusted: str, schema: dict[str, Any]) -> Any:
        self._record("read", {"untrusted": untrusted, "schema": schema})
        return self._answer("read", schema)

    def check(self, prompt: str, schema: dict[str, Any]) -> Any:
        self._record("check", {"prompt": prompt, "schema": schema})
        return self._answer("check", schema)

    def vision(self, image: bytes, prompt: str, schema: dict[str, Any] | None = None) -> Any:
        """Records the prompt, the image's length and a short hash, NEVER the bytes (``image_calls`` keeps the full SHA-256 and the
        length so a test can check the provider received exactly the frame that was sent)."""
        digest = hashlib.sha256(image).hexdigest()
        self.image_calls.append({"sha256": digest, "bytes": len(image)})
        self._record("vision", {"image_sha8": digest[:16], "image_bytes": len(image), "prompt": prompt, "schema": schema})
        if self._usage is not None:
            self.last_call = dict(self._usage)
        return self._answer("vision", schema)

    def computer_step(self, goal: str, screenshot: bytes, history: list[dict[str, Any]]) -> Any:
        self._record("computer_step", {"goal": goal, "screenshot_bytes": len(screenshot), "history": history})
        try:
            from understudy_agent.models.port import Done  # lazy: only when the agent package is installed
        except ImportError:
            raise NotImplementedError("CapturingPort cannot simulate computer use without the agent package") from None
        return Done(summary="stub", claimed_success=False)


class LogCapture:
    """Capture every ``logging`` record (all loggers, all levels) in a ``with`` block, for the PRV-4 "logs hold no source text" check.

        with LogCapture() as logs:
            run_my_flow()
        assert_no_canaries(logs.texts, planted)
    """

    def __init__(self) -> None:
        import logging

        self.records: list[Any] = []
        outer = self

        class _H(logging.Handler):
            def emit(self, record: Any) -> None:  # noqa: D401
                outer.records.append(record)

        self._handler = _H(level=logging.DEBUG)
        self._old_level: int | None = None

    def __enter__(self) -> "LogCapture":
        import logging

        root = logging.getLogger()
        self._old_level = root.level
        root.setLevel(logging.DEBUG)
        root.addHandler(self._handler)
        return self

    def __exit__(self, *exc: Any) -> None:
        import logging

        root = logging.getLogger()
        root.removeHandler(self._handler)
        if self._old_level is not None:
            root.setLevel(self._old_level)

    @property
    def texts(self) -> list[str]:
        out = []
        for r in self.records:
            try:
                msg = r.getMessage()
            except Exception:
                msg = str(r.msg)
            out.append(f"{r.name} {msg} {r.exc_text or ''} {' '.join(str(a) for a in (r.args if isinstance(r.args, tuple) else ()))}")
        return out


# --------------------------------------------------------------------------------------------------------- environment
def hermetic(monkeypatch: Any, tmp_path: Path) -> Path:
    """Point the data dir and home at ``tmp_path`` and turn mock mode off, so a test never touches the shared ``data/``.
    Returns the data dir. (Pass the pytest ``monkeypatch`` and ``tmp_path`` fixtures.)"""
    data = tmp_path / "data"
    data.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("UNDERSTUDY_DATA_DIR", str(data))
    monkeypatch.setenv("UNDERSTUDY_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("UNDERSTUDY_MOCK", raising=False)
    return data


# --------------------------------------------------------------------------------------------------------- ledger checks
def _wire_from_request(req: CapturedRequest) -> dict[str, Any] | None:
    """The ``{purpose, schema, payload}`` object egress put in the request, or None for requests not made through it."""
    body = req.body
    try:
        if req.method == "plan":
            text = body["messages"][-1]["content"]
        elif req.method == "check":
            text = body["prompt"].rsplit("\n\n", 1)[-1]
        else:
            return None
        obj = json.loads(text)
    except (KeyError, IndexError, TypeError, ValueError):
        return None
    return obj if isinstance(obj, dict) and {"purpose", "payload"} <= set(obj) else None


def ledger_extension_rows() -> list[dict[str, Any]]:
    return [r for r in ledger.read_all() if r.get("kind", "extension") == "extension"]


def assert_ledger_complete(port: CapturingPort, rows: list[dict[str, Any]] | None = None) -> None:
    """Exactly one ledger line per captured guarded request, in order, and each line's payload is exactly what the request
    carried. Raises AssertionError otherwise."""
    rows = ledger_extension_rows() if rows is None else rows
    wires = [(r, _wire_from_request(r)) for r in port.requests]
    guarded = [(r, w) for r, w in wires if w is not None]
    unguarded = [r for r, w in wires if w is None]
    assert not unguarded, f"{len(unguarded)} request(s) reached the port without going through egress.send (methods: " \
                          f"{sorted({r.method for r in unguarded})})"
    assert len(rows) == len(guarded), f"{len(guarded)} guarded request(s) but {len(rows)} ledger line(s)"
    for i, ((req, wire), row) in enumerate(zip(guarded, rows)):
        assert row["purpose"] == wire["purpose"], f"ledger line {i}: purpose differs from the request"
        assert row["payload"] == wire["payload"], f"ledger line {i}: the payload in the ledger is not what was sent"
        assert row["bytes"] == req.bytes, f"ledger line {i}: byte count differs ({row['bytes']} vs {req.bytes})"


# --------------------------------------------------------------------------------------------------------- one-call flow
def canary_flow(
    name: str, make_fixtures: Callable[[], Any], run: Callable[[Any, CapturingPort], Any], *, seed: int = 0,
    mode: str = "replace", min_requests: int = 1, record: bool = True, strict: bool = True,
) -> canary.CanaryReport:
    """Plant canaries in fresh fixtures, run ``run(fixtures, port)`` against a ``CapturingPort``, check the ledger and scan.

    ``strict=True`` raises AssertionError on a leak, a missing or extra ledger line, a request that bypassed the guard, or
    fewer than ``min_requests`` requests. ``strict=False`` returns the report without raising on leaks (the eval harness).
    """
    fixtures = make_fixtures()
    planted = canary.plant(fixtures, seed=seed, mode=mode)
    port = CapturingPort()
    before = len(ledger_extension_rows())
    with LogCapture() as logs:
        run(fixtures, port)
    report = canary.scan(port, planted)
    art = canary.scan_artifacts(planted)
    log_report = canary.scan(logs.texts, planted)
    if record:
        canary.record_run(name, report)
    if strict:
        assert report.requests >= min_requests, f"{name}: expected at least {min_requests} captured request(s), saw {report.requests}"
        assert_ledger_complete(port, ledger_extension_rows()[before:])
        if report.leaks:
            raise AssertionError(f"{name}: planted canary token(s) reached the model port: {report.summary()}")
        if art.leaks:
            raise AssertionError(f"{name}: planted token(s) found in the ledger, audit log, queue or log files (PRV-4): {art.summary()}")
        if log_report.leaks:
            raise AssertionError(f"{name}: planted token(s) found in log records (PRV-4): {log_report.summary()}")
    return report


# --------------------------------------------------------------------------------------------------------- flow registry
@dataclass(frozen=True)
class CanaryFlow:
    """One flow to measure. A layer owner exposes ``FLOWS = [CanaryFlow(...), ...]`` in ``<layer>/canary_flows.py`` and
    ``privacy.evaluate.evaluate_privacy()`` runs them all (several seeds each) against a ``CapturingPort``.

    ``make_fixtures()`` builds FRESH fixtures (nested dicts and lists with names, emails, titles, paths, messages, customers);
    ``run(fixtures, port)`` runs the real flow, sending only through ``egress.send(..., port=port)``; ``min_requests`` is how
    many model calls it must make (0 for a flow that may legitimately send nothing). ``mode="append"`` keeps the original text
    (use it when the code reads keywords from titles or messages).
    """

    name: str
    make_fixtures: Callable[[], Any]
    run: Callable[[Any, CapturingPort], Any]
    layer: str = ""
    kind: str = "integration"          # "integration" = the layer's real code; "reference" = the privacy layer's own upstream stand-in
    min_requests: int = 1
    mode: str = "replace"


@dataclass(frozen=True)
class ImageCanaryFlow:
    """An image flow a layer supplies as ``IMAGE_FLOWS = [ImageCanaryFlow(...)]`` in ``<layer>/canary_flows.py``. ``run(planted, port)``
    runs the layer's real code with ``planted.safe_image(kind, source)`` through ``egress.send_image(..., port=port)``; the evaluation runs it
    over several seeds with ``image_canary_flow`` and reports any residue of the planted frame."""

    name: str
    run: Callable[[Any, CapturingPort], Any]
    layer: str = ""


@dataclass
class FlowResult:
    name: str
    layer: str
    kind: str
    seed: int
    requests: int
    planted: int
    leaked: int
    ledger_expected: int
    ledger_lines: int
    ledger_complete: bool
    by_kind: dict[str, int]
    leaked_kinds: list[str]
    error: str | None = None
    note: str | None = None
    artifact_files: int = 0          # PRV-4: files of the audit log, queue, logs and ledgers that were read
    artifact_log_records: int = 0    # PRV-4: logging records captured while the flow ran
    artifact_leaked: int = 0         # planted tokens found in any of them


def run_flow(flow: CanaryFlow, seed: int = 0) -> FlowResult:
    """Run one flow once with canaries planted; never raises (an exception in the flow is recorded as ``error``)."""
    fixtures = flow.make_fixtures()
    try:
        planted = canary.plant(fixtures, seed=seed, mode=flow.mode)
    except AssertionError as exc:
        return FlowResult(flow.name, flow.layer, flow.kind, seed, 0, 0, 0, 0, 0, False, {}, [], error=str(exc)[:160])
    port = CapturingPort()
    before = len(ledger_extension_rows())
    error = None
    with LogCapture() as logs:
        try:
            flow.run(fixtures, port)
        except Exception as exc:  # a flow that fails closed (EgressError) is fine; record what happened, not the message text
            error = type(exc).__name__
    report = canary.scan(port, planted)
    art = canary.scan_artifacts(planted)
    log_report = canary.scan(logs.texts, planted)
    art_leaked = len({(lk.kind, lk.token) for lk in art.leaks} | {(lk.kind, lk.token) for lk in log_report.leaks})
    rows = ledger_extension_rows()[before:]
    guarded = [r for r in port.requests if _wire_from_request(r) is not None]
    try:
        assert_ledger_complete(port, rows)
        complete, note = True, None
    except AssertionError as exc:
        complete, note = False, str(exc)[:200]
    if report.requests < flow.min_requests:
        note = ((note + "; ") if note else "") + f"made {report.requests} request(s), expected at least {flow.min_requests}"
    return FlowResult(flow.name, flow.layer, flow.kind, seed, report.requests, report.planted, report.leaked, len(guarded), len(rows),
                      complete, report.by_kind, sorted({lk.kind for lk in report.leaks}), error, note,
                      artifact_files=art.requests, artifact_log_records=log_report.requests, artifact_leaked=art_leaked)


def vocabulary_problems() -> list[str]:
    """Every registered vocabulary value, purpose instruction and payload field name that the backstop would refuse at send time
    (empty list when all are clean)."""
    from . import patterns
    from .image import image_purposes
    from .payload import purposes, vocabularies

    bad: list[str] = []
    for name, v in vocabularies().items():
        for val in v["values"] or []:
            rules = patterns.scan_text(val)
            if rules:
                bad.append(f"vocabulary {name!r}: value trips {sorted(set(rules))}")
    for pname, p in purposes().items():
        rules = patterns.scan_text(p.instructions)
        if rules:
            bad.append(f"purpose {pname!r}: instructions trip {sorted(set(rules))}")
        for fname in p.model.field_names():
            rules = patterns.scan_text(fname, pii=False)
            if rules:
                bad.append(f"purpose {pname!r}: field name {fname!r} trips the sensitive-field patterns {sorted(set(rules))}")
    for pname, ip in image_purposes().items():
        rules = patterns.scan_text(ip.instructions)
        if rules:
            bad.append(f"image purpose {pname!r}: instructions trip {sorted(set(rules))}")
        for fname in ip.model.field_names():
            rules = patterns.scan_text(fname, pii=False)
            if rules:
                bad.append(f"image purpose {pname!r}: field name {fname!r} trips the sensitive-field patterns {sorted(set(rules))}")
    return bad


def assert_vocabularies_clean() -> None:
    """Fail if any registered id, instruction or field name would be refused by the backstop at send time, so no id can be refused
    in production for a reason a unit test could have caught. A track calls this at the end of its own suite."""
    bad = vocabulary_problems()
    assert not bad, "the privacy backstop would refuse these at send time:\n" + "\n".join(bad)


# --------------------------------------------------------------------------------------------------------- images (REQ-5)
def image_canary_flow(name: str, run: Callable[[Any, CapturingPort], Any], *, seed: int = 0, strict: bool = True, kind: str = "customer_name") -> dict[str, Any]:
    """One call for a track's image tests: plant a PNG (a planted token in its pixels and metadata), run ``run(planted, port)`` against
    a ``CapturingPort`` and check that the frame left no residue anywhere:

    * no file under the data dir (audit, queue, logs, ledger, anything), no temporary file, no log record, no exception text, no ledger
      row and no captured request contains the frame's bytes, token, full hash, or a base64 or hex rendering;
    * every ledger row holds only the allowed fields (sha8, size, dimensions, kind, source, provider, model, latency, tokens, cost, ok).

    ``planted.safe_image(kind, source)`` builds the frame. ``run`` should send through ``egress.send_image``; refusals and failures it
    lets propagate are recorded (their text is scanned), not raised. Returns ``{requests, ledger_rows, residue, ok}``; ``strict`` raises
    AssertionError when ``residue`` is not empty or a row has a disallowed field."""
    import tempfile as _tf

    from ._paths import data_dir

    pi = canary.plant_image(seed, kind=kind)
    port = CapturingPort()
    root = data_dir()
    tmpmon = root / "_tmpmon_image_flow"
    tmpmon.mkdir(parents=True, exist_ok=True)
    old = _tf.tempdir
    _tf.tempdir = str(tmpmon)
    errors: list[str] = []
    try:
        with LogCapture() as logs:
            try:
                run(pi, port)
            except Exception as exc:        # a refusal or failure is a normal outcome; keep its text for the scan
                errors.append(f"{type(exc).__name__}: {exc}")
    finally:
        _tf.tempdir = old
    rows = ledger.read_all()
    residue = canary.scan_image_residue(pi, paths=[root], texts=logs.texts + errors + port.texts() + [json.dumps(rows)])
    residue = [r for r in residue if "_tmpmon_image_flow" not in r]
    left = [p.name for p in tmpmon.iterdir()]
    if left:
        residue.append(f"{len(left)} temporary file(s) left behind")
    allowed_row = {"id", "t", "kind", "status", "purpose", "schema", "method", "fields", "payload", "image", "source", "provider", "model", "bytes",
                   "mock", "ok", "latency_ms", "input_tokens", "output_tokens", "cost_estimate_usd", "error", "reason"}
    allowed_img = {"sha8", "bytes", "width", "height", "kind", "mime", "source"}
    for r in rows:
        if r.get("kind") == "image" and (set(r) - allowed_row or (r.get("image") and set(r["image"]) - allowed_img)):
            residue.append("a ledger row has a field outside the allowed set")
    try:
        tmpmon.rmdir()
    except OSError:
        pass
    out = {"name": name, "requests": len(port), "ledger_rows": len(rows), "residue": residue, "ok": not residue}
    if strict and residue:
        raise AssertionError(f"{name}: the planted frame left residue: {residue[:5]}")
    return out
