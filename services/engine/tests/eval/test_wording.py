"""The report's wording rule (owner decision D57): the report is emitted in the app's wording whatever the sections' own sources and frozen result files say.

The rule runs when the report is assembled, when it is written and when it is rendered, over every prose string of the whole tree; identifiers, enums, ids,
paths, keys and numbers are untouched; and it is idempotent. These tests build reports from tiny fixtures that carry the old words in every kind of text field.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from understudy_engine.eval.assemble import dumps
from understudy_engine.eval.render_md import render
from understudy_engine.eval.wording import BANNED, reword, reword_tree
from understudy_engine.store.paths import repo_root

OLD = {
    "Synthetic households on local sandbox sites; n = 20.": "Generated households on local sandbox sites; n = 20.",
    "The attacks are synthetic and were written by the same team that wrote the defences.": "The attacks are scripted and were written by the same team that wrote the defences.",
    "Every fixture is synthetic with planted facts.": "Every fixture is generated with planted facts.",
    "Simulated participants (language model), not people. Run 4 (n = 24).": "Language-model participants, not people. Run 4 (n = 24).",
    "against a simulated actuator the model declined": "against a stand-in actuator the model declined",
    "Hazard, benefits-processor, synthetic generators we wrote (120 synthetic people per v2 cell)": "Hazard, benefits-processor, generators we wrote (120 generated people per v2 cell)",
    "fit on one synthetic generator family, test on another; pooled off-diagonal cells; synthetic)": "fit on one generator family, test on another; pooled off-diagonal cells; all generated)",
    "synthetic personas only": "generated personas only",
    "a few dozen synthetic attacks": "a few dozen scripted attacks",
    "Synthetic apprentices with planted deficits": "Scripted apprentices with planted deficits",
    "the simulated study has not been run": "the language-model study has not been run",
    "Planted habit (synthetic developers)": "Planted habit (generated developers)",
}


@pytest.mark.parametrize("old,new", list(OLD.items()))
def test_each_old_sentence_comes_out_in_the_app_wording(old, new):
    assert reword(old) == new
    assert not BANNED.search(reword(old))
    assert reword(reword(old)) == reword(old)               # idempotent


def test_the_old_product_name_and_the_word_simply_do_not_come_back_from_frozen_result_files():
    assert reword("It does not show that real people find Understudy natural.") == "It does not show that real people find Knack natural."
    assert reword("A model that is shown the note can simply do what it says.") == "A model that is shown the note can do what it says."
    assert reword("run `understudy synth --all` first") == "run `understudy synth --all` first"          # a command, not the name
    assert reword("python -m understudy_engine.eval writes it") == "python -m understudy_engine.eval writes it"
    assert reword(reword("Understudy can simply wait")) == reword("Understudy can simply wait") == "Knack can wait"


def test_identifiers_enums_ids_paths_and_quoted_enums_are_not_copy():
    for keep in ("synthetic", "simulated", "simulated_participants", "ana-synthetic-origin", "eval-claims-simulated", "data/synthetic", "synthetic_learner", "Understudy"):
        assert reword(keep) == keep
    assert reword("no personas under data/synthetic; run `understudy synth --all`") == "no personas under data/synthetic; run `understudy synth --all`"
    assert reword("origin must be 'synthetic' or 'real'") == "origin must be 'synthetic' or 'real'"


def _tiny_report() -> dict:
    meta = {"origin": "synthetic", "n": 4, "n_unit": "personas", "split": "four synthetic personas", "interval_level": 0.95,
            "note": "Synthetic personas with planted structure; simulated workers.", "generated_at": "2026-11-08T00:00:00Z"}
    return {
        "generated_at": "2026-11-08T00:00:00Z", "mock": True, "git_rev": "abc1234",
        "findings": [{"id": "f1", "title": "The simulated study cannot show an effect", "origin": "synthetic", "badge": "synthetic (generators we wrote)",
                      "text": "Simulated participants (language model), not people. n = 24.", "sections": ["study_sim"], "status": "ok", "numbers": {"x": 1.0, "y": [0.1, 0.2]}}],
        "evidence_map": [{"section": "hazard", "title": "Stuck hazard", "status": "ok", "origin": "synthetic", "n": 4, "n_unit": "synthetic people", "label": None, "reason": None}],
        "sections": {
            "hazard": {"meta": meta, "caveats": ["Synthetic origin: results show the pipeline recovers planted structure."], "data_source": "engine-data synthetic personas (4 people)",
                       "limitations": [{"id": "ana-synthetic-origin", "severity": "high", "text": "Results come from synthetic personas or simulators we wrote."}],
                       "rows": [{"label": "a", "value": 0.5, "ci": [0.1, 0.9]}], "origin_detail": "simulated_participants"},
            "limitations": [{"id": "eval-synthetic", "severity": "high", "text": "Almost every result comes from synthetic apprentices; each section carries a synthetic badge.", "source": "x"}],
        },
    }


def _strings(o, path="$"):
    if isinstance(o, str):
        yield path, o
    elif isinstance(o, dict):
        for k, v in o.items():
            yield from _strings(v, f"{path}.{k}")
    elif isinstance(o, list):
        for i, v in enumerate(o):
            yield from _strings(v, f"{path}[{i}]")


def _prose(o):
    """Every string value with whitespace: the text a person can read."""
    return [(p, s) for p, s in _strings(o) if re.search(r"\s", s)]


def test_no_banned_word_survives_in_any_text_field_of_the_whole_tree():
    out = reword_tree(_tiny_report())
    assert [(p, s) for p, s in _prose(out) if BANNED.search(s)] == []
    assert reword_tree(out) == out                           # idempotent over the tree


def test_what_is_not_text_is_untouched():
    src, out = _tiny_report(), reword_tree(_tiny_report())
    assert out["sections"]["hazard"]["meta"]["origin"] == "synthetic" and out["findings"][0]["origin"] == "synthetic"
    assert out["sections"]["hazard"]["origin_detail"] == "simulated_participants"
    assert out["sections"]["hazard"]["limitations"][0]["id"] == "ana-synthetic-origin" and out["sections"]["limitations"][0]["id"] == "eval-synthetic"
    assert out["findings"][0]["numbers"] == src["findings"][0]["numbers"] and out["sections"]["hazard"]["rows"] == src["sections"]["hazard"]["rows"]
    assert out["generated_at"] == src["generated_at"] and out["git_rev"] == "abc1234" and out["mock"] is True
    assert set(out) == set(src) and set(out["sections"]["hazard"]) == set(src["sections"]["hazard"])
    assert out["findings"][0]["badge"] == "generators we wrote" and out["evidence_map"][0]["n_unit"] == "generated people"
    assert src["sections"]["hazard"]["meta"]["note"].startswith("Synthetic")       # the input was not changed in place


def test_the_written_json_and_the_markdown_carry_the_app_wording_even_from_an_old_report():
    rep = _tiny_report()
    written = json.loads(dumps(rep))
    assert [(p, s) for p, s in _prose(written) if BANNED.search(s)] == []
    rep["sections"] = {"limitations": rep["sections"]["limitations"]}      # the renderer needs each full section's own shape; the register and the map are enough here
    md = render(rep)
    assert "origin: **synthetic**" not in md and "measured on: **generators we wrote**" in md
    assert not re.search(r"\b(synthetic|simulated)\b", md.replace("eval-synthetic", ""), re.I)      # the limitation id in the register's first column is an identifier


def test_the_committed_report_and_the_dashboard_fixture_have_no_banned_word_in_any_text_field():
    root = repo_root()
    for rel in ("evals/report.json", "apps/dashboard/src/fixtures/eval-report.json"):
        path = Path(root) / rel
        if not path.exists():                                # a checkout without the report
            continue
        bad = [(p, s[:90]) for p, s in _prose(json.loads(path.read_text(encoding="utf-8"))) if BANNED.search(s)]
        assert bad == [], rel
