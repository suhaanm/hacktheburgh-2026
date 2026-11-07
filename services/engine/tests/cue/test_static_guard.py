"""Nothing in the cue package imports a model client, opens a socket or touches ModelPort (the static guard of the privacy layer)."""
from __future__ import annotations

from pathlib import Path

from understudy_engine.privacy import guard

CUE = Path(__file__).resolve().parents[2] / "understudy_engine" / "cue"


def test_every_cue_module_passes_the_static_egress_guard():
    files = sorted(CUE.glob("*.py"))
    assert len(files) >= 15
    bad = []
    for f in files:
        v, _ = guard.scan_source(f.read_text(), f"cue/{f.name}")
        bad += [str(x) for x in v]
    assert bad == [], "\n".join(bad)


def test_the_guard_covers_the_cue_directory_when_the_privacy_track_has_registered_it():
    # informational: the privacy track adds "cue" to GUARDED_DIRS; this test only fails if it was registered but a file escapes the scan
    if "cue" in guard.GUARDED_DIRS:
        rep = guard.scan_tree()
        assert rep.ok and any(f.startswith("cue/") for f in rep.files)


def test_cue_has_a_canary_flows_module_that_says_why_it_has_no_model_path():
    from understudy_engine.cue import canary_flows

    assert canary_flows.FLOWS == [] and len(canary_flows.NOT_APPLICABLE) > 40 and "no model path" in canary_flows.NOT_APPLICABLE


def test_no_cue_module_mentions_a_model_name():
    import re

    pat = re.compile(r"gpt-\d|gemini-\d|claude-\w|qwen", re.I)
    hits = [f.name for f in CUE.glob("*.py") if pat.search(f.read_text())]
    assert hits == []
