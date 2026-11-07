"""Leak check for the calendar layer: run the whole pipeline over canary-seeded calendars and look for any planted token in every
output (API payloads, suggestions, the real-check aggregate) and in every captured outbound request.

The canary calendars (``synth.generate(canary=True)``) carry unique planted names, addresses, titles, locations, descriptions and ids
in the very fields the code reads. A pass means none of them appear anywhere that leaves the layer. It does not mean a paraphrase or an
encoding could not carry one (the scan looks for the exact strings, case-insensitively); that limit is stated in the limitations register.
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Iterable, Iterator

from . import real_check, service
from . import suggest as sug
from .model import week_label
from .store import CalendarStore


@dataclass
class LeakReport:
    people: int = 0
    outputs: int = 0
    bytes_scanned: int = 0
    requests: int = 0
    planted: int = 0
    leaked: int = 0
    leaked_tokens: list[str] = field(default_factory=list)       # only the count and a short prefix are ever shown
    log_records: int = 0
    control_detected: bool = False
    files_written_outside_tmp: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {"people": self.people, "outputs_scanned": self.outputs, "bytes_scanned": self.bytes_scanned, "outbound_requests": self.requests,
                "planted_tokens": self.planted, "leaked": self.leaked, "log_records_scanned": self.log_records,
                "positive_control_detected": self.control_detected}


def scan(texts: Iterable[str], tokens: list[str]) -> list[str]:
    """Tokens (lower-case) found in any text. Substring match, case-insensitive; tokens shorter than 5 characters are not searched."""
    blob = "\n".join(texts).lower()
    return [t for t in tokens if len(t) >= 5 and t.lower() in blob]


@contextmanager
def _scratch_data_dir() -> Iterator[str]:
    """Send ledger lines written by this check to a throw-away folder, so a test run never adds lines to the worker's real ledger."""
    old = os.environ.get("UNDERSTUDY_DATA_DIR")
    with tempfile.TemporaryDirectory(prefix="understudy-canary-") as d:
        os.environ["UNDERSTUDY_DATA_DIR"] = d
        try:
            yield d
        finally:
            if old is None:
                os.environ.pop("UNDERSTUDY_DATA_DIR", None)
            else:
                os.environ["UNDERSTUDY_DATA_DIR"] = old


class _Collect(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=1)
        self.records: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.records.append(record.getMessage() + " " + str(record.args))
        except Exception:                                    # pragma: no cover
            self.records.append(str(record.msg))


def run_leak_check(canary_store: CalendarStore, tokens: list[str], *, people: list[str] | None = None, reword: bool = True) -> LeakReport:
    """Run week reports, suggestions (templated and, if privacy is present, reworded through a capturing port) and the real-check helper for
    each person; scan everything for ``tokens``."""
    rep = LeakReport(planted=len(tokens))
    handler = _Collect()
    root = logging.getLogger()
    old_level = root.level
    root.addHandler(handler)
    root.setLevel(1)
    texts: list[str] = []
    port: Any = None
    if reword:
        try:
            from ..privacy.testing import CapturingPort
            port = CapturingPort(stub_text="Hold one longer focus block on most days.")
        except ImportError:                                  # pragma: no cover
            port = None
    try:
        with _scratch_data_dir():
            for p in people or canary_store.people():
                pc = canary_store.get(p)
                if pc is None:
                    continue
                rep.people += 1
                for m in pc.weeks:
                    wk = week_label(m)
                    out = service.week_report(canary_store, p, wk, n_boot=50)
                    texts.append(json.dumps({"meta": service.week_meta(out), "data": out}, default=str))
                    sr = service.suggestions_report(canary_store, p, wk, reword=False)
                    texts.append(json.dumps({"meta": service.suggestions_meta(sr), "data": sr["suggestions"]}, default=str))
                    if port is not None and sr["suggestions"]:
                        ref = service.reference_for(canary_store, pc.role)
                        feats = pc.week(m).features
                        for s in sr["suggestions"][:3]:
                            r2 = sug.reword(s, pc.role, ref.features(), feats, port=port, accept_mock=True)
                            texts.append(json.dumps(r2, default=str))
                src, work, _info = canary_store.source_for(p, "ics")
                texts.append(json.dumps(real_check.run(src, work=work), default=str))
                src2, work2, _ = canary_store.source_for(p, "json")
                texts.append(json.dumps(real_check.run(src2, work=work2, bucket_small=True), default=str))
            if port is not None:
                rep.requests = len(port.requests)
                texts.extend(json.dumps(r.body, default=str) for r in port.requests)
                texts.extend(r.text for r in port.requests)
    finally:
        root.removeHandler(handler)
        root.setLevel(old_level)
    rep.outputs = len(texts)
    rep.bytes_scanned = sum(len(t) for t in texts)
    rep.log_records = len(handler.records)
    found = scan(texts + handler.records, tokens)
    rep.leaked = len(found)
    rep.leaked_tokens = [t[:3] + "..." for t in found[:5]]
    # positive control: the scan must see a token when one is present, or a pass would mean nothing
    probe = next((t for t in tokens if len(t) >= 8), None)
    rep.control_detected = bool(probe and scan([f"prefix {probe.upper()} suffix"], [probe]))
    return rep
