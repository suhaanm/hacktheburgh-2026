"""The fixtures and the evaluation: well-formed, disjoint from the prompts' worked examples, honest in shape."""
from __future__ import annotations

import json
import re


from understudy_engine.localmodel import config, evaluate, fixtures, prompts, rules
from understudy_engine.localmodel.guards import audit_text_for_leaks
from understudy_engine.localmodel.schemas import COMMIT_VOCAB, EVENT_VOCAB, is_test_path, normalise_commit, normalise_event


def test_fixture_sets_are_the_advertised_size_and_split():
    cs, es = fixtures.build_commits(), fixtures.build_events()
    assert (len(cs), len(es)) == (150, 150)
    for fs in (cs, es):
        assert len({f.id for f in fs}) == 150
        dev = sum(1 for f in fs if f.split == "dev")
        assert 45 <= dev <= 60 and len(fs) - dev >= 90


def test_fixtures_are_deterministic():
    a = [json.dumps([f.item, f.label], sort_keys=True) for f in fixtures.build_commits() + fixtures.build_events()]
    b = [json.dumps([f.item, f.label], sort_keys=True) for f in fixtures.build_commits() + fixtures.build_events()]
    assert a == b and len(fixtures.fixtures_fingerprint()) == 12


def test_labels_use_the_fixed_vocabularies_and_match_the_code_computed_facts():
    for f in fixtures.build_commits():
        for k in ("category", "size_bucket", "risk", "message_quality"):
            assert f.label[k] in COMMIT_VOCAB[k], (f.id, k)
        d = rules.digest_commit(f.item)
        assert d["size_bucket"] == f.label["size_bucket"] and d["touches_tests"] == f.label["touches_tests"], f.id
        assert f.label["touches_tests"] == any(is_test_path(x["path"]) for x in f.item["files"])
    for f in fixtures.build_events():
        for k in ("category", "duration_bucket", "attendee_bucket"):
            assert f.label[k] in EVENT_VOCAB[k], (f.id, k)
        d = rules.digest_event(f.item)
        for k in ("recurring", "duration_bucket", "attendee_bucket"):
            assert d[k] == f.label[k], (f.id, k)


def test_every_planted_canary_really_is_in_the_input():
    for f in fixtures.build_commits() + fixtures.build_events():
        blob = json.dumps(f.item)
        for c in f.canaries:
            assert c.lower() in blob.lower() or c.lower() in blob.lower().replace("\\\\", "\\"), (f.id, c)
    assert sum(1 for f in fixtures.build_commits() if f.canaries) >= 50
    assert sum(1 for f in fixtures.build_events() if f.canaries) >= 50


def test_every_category_is_represented_in_both_splits():
    for fs in (fixtures.build_commits(), fixtures.build_events()):
        for split in ("dev", "test"):
            cats = {f.label["category"] for f in fs if f.split == split}
            assert len(cats) >= (8 if fs is None else 8)


def test_worked_examples_are_disjoint_from_the_fixtures():
    norm = lambda s: re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()  # noqa: E731
    shots = {norm(t) for t in prompts.shot_texts()}
    for f in fixtures.build_commits():
        assert norm(normalise_commit(f.item).clean) not in shots, f.id
    for f in fixtures.build_events():
        assert norm(normalise_event(f.item).title) not in shots, f.id


def test_wilson_and_paired_helpers():
    assert evaluate.wilson(0, 10)[0] == 0.0 and evaluate.wilson(10, 10)[1] == 1.0
    lo, hi = evaluate.wilson(50, 100)
    assert 0.40 < lo < 0.41 and 0.59 < hi < 0.60
    p = evaluate.paired([True] * 30 + [False] * 10, [True] * 20 + [False] * 20)
    assert p["model_only_right"] == 10 and p["rules_only_right"] == 0 and p["verdict"] == "model_better" and p["sign_test_p"] < 0.01
    same = evaluate.paired([True, False] * 20, [True, False] * 20)
    assert same["verdict"] == "no_clear_difference" and same["acc_diff"] == 0


def test_report_without_a_model_is_honest_and_complete():
    rep = evaluate.evaluate_localmodel(fast=True)                      # mock mode (autouse fixture), empty data dir: no cache
    assert rep["status"] == "model_not_run" and rep["model"]["source"] == "not_run"
    assert rep["meta"]["origin"] == "synthetic" and rep["meta"]["n"] == 300 and rep["limitations"]
    assert {"loc_no_finetune", "loc_synthetic", "loc_small_n"} <= {x["id"] for x in rep["limitations"]}
    for task in ("commit_digest", "event_digest"):
        t = rep["tasks"][task]
        cat = t["fields"]["category"]
        assert cat["rules"]["test"]["n"] >= 90 and cat["rules"]["test"]["ci"][0] < cat["rules"]["test"]["acc"] < cat["rules"]["test"]["ci"][1]
        assert cat["model"]["dev"] is None if "model" in cat and cat["model"] is None else True
    lk = rep["leak_canary"]
    assert lk["planted_strings"] > 100 and lk["per_arm"]["rules"]["canaries_found_in_outputs"] == 0
    assert lk["per_arm"]["rules"]["values_outside_vocabulary"] == 0
    gs = rep["guard_stress"]
    assert set(gs) == {"echo_input_in_field", "email_in_field", "extra_key_with_input", "out_of_vocabulary", "non_json"}
    for kind, r in gs.items():
        assert r["items"] == 300 and r["canaries_in_outputs"] == 0
        assert r["rejected_and_replaced_by_rules"] + r["accepted_because_the_value_was_a_vocabulary_word"] == 300
        assert r["rejected_and_replaced_by_rules"] >= 290                # only a bare "docs" or "chore" message echoes a valid value


def test_headline_rows_cover_the_model_or_rules_fields_only():
    rep = evaluate.evaluate_localmodel(fast=True)
    got = {(r["task"], r["field"]) for r in rep["headline"]}
    assert got == {("commit_digest", "category"), ("commit_digest", "risk"), ("commit_digest", "message_quality"),
                   ("event_digest", "category"), ("event_digest", "needs_prep")}
    assert all(r["verdict"] == "model_not_run" and r["rules_ci"][0] <= r["rules_acc"] <= r["rules_ci"][1] for r in rep["headline"])


def test_live_run_against_the_stub_then_report_from_the_cache(stub):
    rep = evaluate.evaluate_localmodel(fast=False)
    assert rep["status"] == "ok" and rep["model"]["source"] == "live"
    assert config.eval_cache_path().exists() and not config.pid_path().exists()           # server stopped again
    cache_text = config.eval_cache_path().read_text()
    planted = {c for f in fixtures.build_commits() + fixtures.build_events() for c in f.canaries}
    assert not audit_text_for_leaks(cache_text, sorted(planted))                       # enums only, no input text
    assert rep["leak_canary"]["per_arm"]["model"]["canaries_found_in_outputs"] == 0
    assert rep["leak_canary"]["server_log"]["checked"] is True and rep["leak_canary"]["server_log"]["canaries_found_in_log"] == 0
    assert rep["parse_failures"]["commit_digest"]["fell_back_to_rules"] == 0
    assert rep["injection"]["commit_digest"]["items"] == 20 and rep["latency"]["event_digest"]["items"] == 150
    cat = rep["tasks"]["commit_digest"]["fields"]["category"]
    assert cat["model"]["test"]["n"] == cat["rules"]["test"]["n"] and cat["paired_model_vs_rules"]["test"]["verdict"] == "no_clear_difference"
    # now offline, the way make eval runs it: mock on, numbers from the cache
    import os

    os.environ["UNDERSTUDY_MOCK"] = "1"
    try:
        again = evaluate.evaluate_localmodel(fast=True)
    finally:
        del os.environ["UNDERSTUDY_MOCK"]
    assert again["model"]["source"] == "cache" and again["tasks"] == rep["tasks"]


def test_a_stale_cache_is_not_used(stub, monkeypatch):
    evaluate.evaluate_localmodel(fast=False)
    monkeypatch.setattr(prompts, "prompt_version", lambda: "changed")
    monkeypatch.setenv("UNDERSTUDY_MOCK", "1")
    rep = evaluate.evaluate_localmodel(fast=True)
    assert rep["status"] == "model_not_run" and "stale" in rep["model"]["reason"]


def test_no_canary_in_the_rules_outputs():
    for f in fixtures.build_commits():
        assert not audit_text_for_leaks(json.dumps(rules.digest_commit(f.item)), f.canaries)
    for f in fixtures.build_events():
        assert not audit_text_for_leaks(json.dumps(rules.digest_event(f.item)), f.canaries)
