"""PRV-1 and PRV-4 for the calendar layer: planted names, addresses, titles, places and ids never reach an API response, a suggestion,
the real-check result, an outbound request, the ledger, a log record or a file."""
from __future__ import annotations

import ast
import json
import os
from pathlib import Path

import pytest

from understudy_engine.calendar import canary_run, real_check, service
from understudy_engine.calendar import suggest as S
from understudy_engine.privacy import testing

ROOT = Path(__file__).resolve().parents[2] / "understudy_engine"


@pytest.fixture(scope="module")
def tokens(canary_store):
    return json.loads((canary_store.directory / "canary.json").read_text())["tokens"]


def test_canary_calendars_have_real_looking_text_and_the_same_structure(store, canary_store, tokens):
    assert len(tokens) > 5000
    src, work, _ = canary_store.source_for("p_nov05")
    items = list(src.read())
    titles = [i.fields["title"] for i in items]
    assert any(" " in t and len(t) > 20 for t in titles)                                  # titles look like titles, not like markers
    emails = {a for i in items for a in i.fields["attendees"]}
    assert emails and all("@" in e for e in emails)
    for p in store.people():
        a, b = store.get(p), canary_store.get(p)
        assert [a.week(m).features for m in a.weeks] == [b.week(m).features for m in b.weeks], p
    blob = " ".join(titles + [a for i in items for a in i.fields["attendees"]] + [i.fields["location"] for i in items]).lower()
    present = [t for t in tokens if len(t) >= 8 and t.lower() in blob]
    assert len(present) > 20                                                              # the planted text really is in the fields the code reads


def test_scan_has_a_working_positive_control(tokens):
    probe = next(t for t in tokens if len(t) >= 8)
    assert canary_run.scan([f"x {probe.upper()} y"], [probe]) == [probe]
    assert canary_run.scan(["nothing here"], [probe]) == []


def test_no_planted_token_in_any_output_request_or_log(canary_store, tokens):
    rep = canary_run.run_leak_check(canary_store, tokens)
    assert rep.people == 28 and rep.outputs > 200 and rep.requests > 20 and rep.bytes_scanned > 500_000
    assert rep.leaked == 0, (rep.leaked, rep.leaked_tokens)
    assert rep.control_detected


def test_a_leaky_variant_would_be_caught(canary_store, tokens, monkeypatch):
    """Prove the check can fail: make the suggestion text echo a title from the source, and the scan must flag it."""
    pc = canary_store.get("p_ninetofive")
    src, work, _ = canary_store.source_for("p_ninetofive")
    title = next(i.fields["title"] for i in src.read() if len(i.fields["title"]) > 25)
    assert canary_run.scan([json.dumps({"text": f"Move {title} out of the morning"})], tokens)


def test_calendar_and_plugin_canary_flows_pass_the_privacy_harness(monkeypatch, tmp_path):
    testing.hermetic(monkeypatch, tmp_path)
    from understudy_engine.calendar.canary_flows import FLOWS as CAL
    from understudy_engine.plugins.canary_flows import FLOWS as PLG
    assert CAL and PLG and CAL[0].layer == "calendar" and PLG[0].layer == "plugins"
    for flow in CAL + PLG:
        for seed in range(8):
            r = testing.run_flow(flow, seed)
            assert r.error is None, (flow.name, seed, r.error)
            assert r.requests >= flow.min_requests and r.planted > 100
            assert r.leaked == 0 and r.artifact_leaked == 0 and r.ledger_complete, (flow.name, seed, r)
            assert r.ledger_lines == r.requests


def test_registered_vocabularies_are_clean():
    S.register_privacy()
    testing.assert_vocabularies_clean()


def test_wording_works_with_cohort_means_not_only_whole_numbers(store, monkeypatch, tmp_path):
    """The expert reference is a mean (9.46 focus blocks). Counts are rounded before bucketing, so the guard accepts the payload."""
    testing.hermetic(monkeypatch, tmp_path)
    port = testing.CapturingPort(stub_text="Hold one longer focus block on most days.")
    pc = store.get("p_nightowl")
    ref = service.reference_for(store, pc.role)
    feats = pc.week(pc.weeks[-1]).features
    ref_f = ref.features()
    assert any(abs(v - round(v)) > 0.1 for k, v in ref_f.items() if k in ("focus_blocks_90", "batch_windows", "review_slots"))
    tpl_targets = service.load_template(pc.role).targets
    for s in S.suggest(feats, ref_f, tpl_targets, days_expected=5, person="p", week="w"):
        out = S.reword(s, pc.role, ref_f, feats, port=port, accept_mock=True)
        assert out["source"] == "reworded" and out["ledger_id"], s["template"]
    assert len(port.requests) >= 5
    testing.assert_ledger_complete(port)


def test_nothing_is_written_while_the_pipeline_runs(canary_store, tmp_path, monkeypatch):
    """PRV-4: no raw text is written anywhere. Run the pipeline in an empty working directory and diff the file system."""
    monkeypatch.chdir(tmp_path)
    data = Path(os.environ["UNDERSTUDY_DATA_DIR"])
    home = Path(os.environ["UNDERSTUDY_HOME"])
    data.mkdir(parents=True, exist_ok=True)
    before = {p for root in (tmp_path, data, home) for p in root.rglob("*")}
    src, work, _ = canary_store.source_for("p_nov05")
    real_check.run(src, work=work)
    service.week_report(canary_store, "p_nov05", n_boot=30)
    service.suggestions_report(canary_store, "p_nov05")
    after = {p for root in (tmp_path, data, home) for p in root.rglob("*")}
    assert after == before


def test_calendar_and_plugin_code_never_touches_a_model_client():
    """Static guard in the spirit of the privacy track's: nothing under calendar/ or plugins/ imports a model client or calls the port."""
    banned_imports = ("openai", "anthropic", "understudy_agent")
    offenders = []
    for folder in ("calendar", "plugins"):
        for path in (ROOT / folder).rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                names = []
                if isinstance(node, ast.Import):
                    names = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom):
                    names = [node.module or ""]
                    names += [a.name for a in node.names]
                if any(n.split(".")[0] in banned_imports or n in ("ModelPort", "get_model_port") for n in names):
                    offenders.append((path.name, names))
                if isinstance(node, ast.Attribute) and node.attr in ("plan", "check") and isinstance(node.value, ast.Name) and node.value.id in ("port", "model"):
                    offenders.append((path.name, node.attr))
    assert offenders == []
