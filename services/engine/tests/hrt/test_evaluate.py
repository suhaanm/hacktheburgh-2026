"""The report sections: shaped from recorded results, valid against the report schema, pending (never a dev result) when the held-out run has not been made."""
from __future__ import annotations

import json
import shutil

import pytest

from understudy_engine.eval import render_md
from understudy_engine.eval.adapters import SECTION_NAMES, Ctx, hrt_decisions, hrt_ledger
from understudy_engine.eval.assemble import run_section
from understudy_engine.eval.adapters import SECTIONS
from understudy_engine.eval.schema import load_schema
from understudy_engine.hrt import evaluate as ev
from understudy_engine.store.paths import repo_root

RESULTS = repo_root() / "evals" / "hrt" / "results"


def _dev(part: str) -> dict:
    p = RESULTS / f"dev_{part}.json"
    if not p.exists():
        pytest.skip(f"{p.name} has not been written (run `python -m understudy_engine.hrt.run dev`)")
    return json.loads(p.read_text(encoding="utf-8"))


def _valid(name: str, section: dict) -> list[str]:
    from jsonschema import Draft202012Validator

    schema = load_schema()
    v = Draft202012Validator({"$ref": f"#/$defs/{name}", "$defs": schema["$defs"]})
    return [e.message for e in v.iter_errors(section)]


def test_the_two_sections_are_registered_in_the_harness_the_schema_and_the_markdown():
    assert "hrt_ledger" in SECTION_NAMES and "hrt_decisions" in SECTION_NAMES
    assert "hrt_ledger" in render_md.TITLES and "hrt_decisions" in render_md.TITLES and "hrt_ledger" in render_md.RENDER
    props = load_schema()["properties"]["sections"]["properties"]
    assert "hrt_ledger" in props and "hrt_decisions" in props


def test_shape_ledger_is_schema_valid_and_carries_origin_n_split_and_every_registered_claim():
    s = ev.shape_ledger(_dev("ledger"))
    assert _valid("hrt_ledger", s) == []
    m = s["meta"]
    assert m["origin"] == "synthetic" and m["n"] > 0 and m["n_unit"] and m["split"] and m["interval_level"] == 0.95
    ids = [c["id"] for c in s["rows"]]
    assert ids[:4] == ["P1", "P2", "P3", "P4a"] and "P4b" in ids and "P6b" in ids
    assert all(c["result"] in ("passed", "not passed", "not applicable") for c in s["rows"])
    worlds = {w["world"] for w in s["worlds"]}
    assert any("v1" in w for w in worlds) and any("markov" in w for w in worlds) and any("rule change" in w for w in worlds)
    assert s["reliability_v1"] and all(0 <= b["p_mean"] <= 1 and 0 <= b["freq"] <= 1 for b in s["reliability_v1"])
    assert any(l["severity"] == "high" for l in s["limitations"]) and "no live predictions" in " ".join(l["text"] for l in s["limitations"])
    assert "generated" in s["label"]


def test_shape_decisions_is_schema_valid_with_the_primary_family_and_the_unscored_rows_named():
    s = ev.shape_decisions(_dev("decisions"))
    assert _valid("hrt_decisions", s) == []
    assert [r["id"] for r in s["rows"]] == ["D1", "D2", "D3", "D4"]
    assert s["primary_family"]["size"] == 4 and abs(s["primary_family"]["adjusted_level"] - 0.9875) < 1e-9
    for r in s["rows"]:
        assert r["verdict"] in ("win", "loss", "no clear difference") and len(r["ci95"]) == 2 and len(r["ci_adjusted_98_75"]) == 2
    assert s["not_scored"][0]["id"] == "D6" and s["recorded"][0]["id"] == "D5"
    assert "generated" in s["label"] and s["meta"]["origin"] == "synthetic"


def _strings(o, skip=("origin",)):
    if isinstance(o, str):
        yield o
    elif isinstance(o, dict):
        for k, v in o.items():
            if k not in skip:
                yield from _strings(v, skip)
    elif isinstance(o, list):
        for v in o:
            yield from _strings(v, skip)


def test_no_text_the_app_can_show_says_synthetic_or_simulated_and_none_is_a_banned_phrase():
    """Owner decision D57: the app says 'generators we wrote', 'generated worlds'. The data's origin enum keeps its value; every other string is in plain words
    and passes the banned-phrase list of docs/knack-ux/banned-phrases.json."""
    import re

    cfg = json.loads((repo_root() / "docs" / "knack-ux" / "banned-phrases.json").read_text(encoding="utf-8"))
    for name, section in (("ledger", ev.shape_ledger(_dev("ledger"))), ("decisions", ev.shape_decisions(_dev("decisions")))):
        assert section["meta"]["origin"] == "synthetic"
        for text in _strings(section):
            assert not re.search(r"\b(synthetic|simulat\w*)\b", text, re.I), f"{name}: {text[:120]}"
            for p in cfg["phrases"] + cfg["visible_words"]:
                pat = r"(?:^|[.!?]\s+)" + re.escape(p) if p.endswith(":") else r"\b" + re.escape(p) + r"\b"
                assert not re.search(pat, text, re.I), f"{name}: banned phrase {p!r} in {text[:120]}"
    assert ev.app_words("a simulated worker, the simulator's reward, Synthetic data") == "a generated worker, the generator reward, Generated data"


def test_the_markdown_renders_both_sections_with_their_claims_and_limits():
    a = ev.shape_ledger(_dev("ledger"))
    b = ev.shape_decisions(_dev("decisions"))
    txt = render_md._hrt_ledger(a)
    assert "P1" in txt and "The guard" in txt and "Calibration slope" in txt
    txt2 = render_md._hrt_decisions(b)
    assert "when to build an automation" in txt2 and "not scored" in txt2 and "98.75%" in txt2


def test_a_part_that_has_not_been_run_is_pending_and_a_dev_result_is_never_shown(tmp_path, monkeypatch):
    monkeypatch.setenv("UNDERSTUDY_EVALS_DIR", str(tmp_path))
    (tmp_path / "hrt" / "results").mkdir(parents=True)
    for part in ("ledger", "decisions"):
        src = RESULTS / f"dev_{part}.json"
        if src.exists():
            shutil.copy(src, tmp_path / "hrt" / "results" / f"dev_{part}.json")
    spec = {s.name: s for s in SECTIONS}
    for name in ("hrt_ledger", "hrt_decisions"):
        sec, _ = run_section(spec[name], Ctx(fast=True), lambda m: None)
        assert sec["status"] == "pending" and "held-out run" in sec["reason"] and "dev result is never shown" in sec["reason"]


def test_a_recorded_held_out_result_becomes_a_section(tmp_path, monkeypatch):
    monkeypatch.setenv("UNDERSTUDY_EVALS_DIR", str(tmp_path))
    d = tmp_path / "hrt" / "results"
    d.mkdir(parents=True)
    for part in ("ledger", "decisions"):
        src = RESULTS / f"dev_{part}.json"
        if not src.exists():
            pytest.skip("no dev result to stand in for a held-out file")
        shutil.copy(src, d / f"heldout_{part}.json")
    a, b = hrt_ledger(Ctx()), hrt_decisions(Ctx())
    assert a["meta"]["origin"] == "synthetic" and a["rows"] and b["rows"] and b["meta"]["n_unit"] == "generated worlds"
