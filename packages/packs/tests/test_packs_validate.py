"""Tests for the pack validator, the schemas and the reference mapper. Run:
    uv run pytest packages/packs/tests -q
"""
from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator

import validate as V
from refmap import map_events, merge

PACKS = Path(__file__).resolve().parents[1]
SCHEMA = V.SCHEMA_DIR
PACK_IDS = ["benefits-processor", "data-analyst", "programmer"]
BEN = PACKS / "benefits-processor"


def validator(name: str) -> Draft202012Validator:
    return Draft202012Validator(json.loads((SCHEMA / name).read_text()))


def clone_pack(tmp_path: Path, pack: str) -> Path:
    dst = tmp_path / pack
    shutil.copytree(PACKS / pack, dst)
    return dst


def edit_yaml(path: Path, fn) -> None:
    data = yaml.safe_load(path.read_text())
    fn(data)
    path.write_text(yaml.safe_dump(data, sort_keys=False))


# ---------------------------------------------------------------- the three real packs

@pytest.mark.parametrize("pack", PACK_IDS)
def test_real_packs_validate(pack):
    assert V.validate_pack(PACKS / pack) == []


@pytest.mark.parametrize("pack", PACK_IDS)
def test_every_yaml_and_json_file_in_a_pack_parses(pack):
    assert V.parse_all_files(PACKS / pack) == []
    files = [p for p in (PACKS / pack).rglob("*") if p.suffix in (".yaml", ".json")]
    assert len(files) >= 8
    for p in files:
        data = json.loads(p.read_text()) if p.suffix == ".json" else yaml.safe_load(p.read_text())
        assert data, p


def test_unparseable_yaml_is_reported_not_swallowed(tmp_path):
    # the bug that bit us: a flow mapping whose plain scalar holds ", " and "?"
    dst = clone_pack(tmp_path, "programmer")
    (dst / "expert_steps.yaml").write_text("checks:\n  - { coach: { question: What is wrong, and have you looked? } }\n")
    errs = V.validate_pack(dst)
    assert errs and "expert_steps.yaml" in errs[0] and "does not parse" in errs[0]


def test_schema_package_and_examples_validate():
    assert V.validate_schema_package() == []


def test_packs_differ_visibly():
    packs = {p: yaml.safe_load((PACKS / p / "pack.yaml").read_text()) for p in PACK_IDS}
    assert V.compare_packs(packs) == []
    tones = {p: (d["tone_defaults"]["length"], d["tone_defaults"]["voice"], d["tone_defaults"]["pace"]) for p, d in packs.items()}
    assert len(set(tones.values())) == 3
    extras = [set(d["cogs"]["extra"]) for d in packs.values()]
    assert not (extras[0] & extras[1]) and not (extras[0] & extras[2]) and not (extras[1] & extras[2])


def test_depth_flags_and_thin_pack_omissions():
    deep = yaml.safe_load((BEN / "pack.yaml").read_text())
    assert deep["depth"] == "deep" and deep["oracle"] == "understudy_agent.sandbox_sites.oracle:score"
    assert "not law" in deep["oracle_note"].lower()
    assert deep["expert_policy"]["coverage"] == "full" and (BEN / "tasks").is_dir()
    for thin in ("data-analyst", "programmer"):
        d = yaml.safe_load((PACKS / thin / "pack.yaml").read_text())
        assert d["depth"] == "thin"
        assert "oracle" not in d and "tasks" not in d
        assert d["expert_policy"]["coverage"] == "stub"


def test_benefits_pack_has_the_spec_cogs_and_five_questions():
    d = yaml.safe_load((BEN / "pack.yaml").read_text())
    assert d["cogs"]["extra"] == ["ENTER_HOUSEHOLD", "OPEN_CALCULATOR", "READ_RESULT", "CHECK_CLIFF", "COPY_TO_NOTE", "RECONCILE"]
    assert [q["id"] for q in d["onboarding"]["questions"]] == ["tools", "risky", "tone", "pace", "hours"]


# ---------------------------------------------------------------- zone mapping (engine format)

def test_mapping_extra_cogs_match_pack_and_vocabulary_covers_base_zones():
    for pack in PACK_IDS:
        pk = yaml.safe_load((PACKS / pack / "pack.yaml").read_text())
        m = yaml.safe_load((PACKS / pack / "mapping.yaml").read_text())
        assert m["extra_cogs"] == pk["cogs"]["extra"]
        assert set(V.BASE_ZONES) <= set(m["zones"])
        assert set(m["params"]) == {"follow_s", "gap_idle_s", "reformulate_within_s", "max_cog_s"}


def _engine_default() -> dict:
    default = V.ROOT / "services" / "engine" / "understudy_engine" / "cogs" / "default_mapping.yaml"
    if not default.is_file():
        pytest.skip("engine default mapping not present")
    return yaml.safe_load(default.read_text())


def test_benefits_params_and_rules_equal_the_engine_default():
    """The deep pack carries a verbatim copy of services/engine/.../cogs/default_mapping.yaml.
    If this fails the default changed: run `uv run python packages/packs/sync_mapping.py`."""
    d = _engine_default()
    m = yaml.safe_load((BEN / "mapping.yaml").read_text())
    assert m["params"] == d["params"] and m["extra_cogs"] == d["extra_cogs"]
    assert m["rules"] == d["rules"]


@pytest.mark.parametrize("pack", ["data-analyst", "programmer"])
def test_thin_packs_carry_the_default_base_rules(pack):
    d = _engine_default()
    base_start = next(i for i, r in enumerate(d["rules"]) if r["match"].get("type") == "idle")
    # base rules only: the default also keeps a benefits role rule (nav + calc_result) among them
    base = [r for r in d["rules"][base_start:] if r["cog"] not in d["extra_cogs"]]
    m = yaml.safe_load((PACKS / pack / "mapping.yaml").read_text())
    assert m["rules"][-len(base):] == base


def test_cliff_zones_are_in_the_benefits_vocabulary_and_capture_config():
    m = yaml.safe_load((BEN / "mapping.yaml").read_text())
    assert {"cliff_button", "cliff_panel"} <= set(m["zones"])
    sites = yaml.safe_load((BEN / "tasks" / "sites.yaml").read_text())
    for s in sites["sites"]:
        if s["kind"] != "calculator":
            continue
        zones = {e["zone"]: e["selector"] for e in s["capture"]["elements"]}
        assert zones["cliff_button"] == sites["cliff"]["button"] and zones["cliff_panel"] == sites["cliff"]["panel"]
        # cliff elements must win over the broader result and form zones
        order = [e["zone"] for e in s["capture"]["elements"]]
        assert order.index("cliff_button") < order.index("calc_result" if "calc_result" in order else "household_form")


def test_refmap_hand_made_trace():
    m = yaml.safe_load((BEN / "mapping.yaml").read_text())
    events = [
        {"dt": 0, "type": "nav", "meta": {"zone": "calc_site"}},
        {"dt": 5, "type": "scroll", "meta": {"zone": "household_form"}},
        {"dt": 5, "type": "focus", "role": "textbox", "meta": {"zone": "household_form"}},
        {"dt": 5, "type": "scroll", "meta": {"zone": "calc_result"}},
        {"dt": 5, "type": "scroll", "meta": {"zone": "cliff_panel"}},
        {"dt": 5, "type": "tab", "meta": {"zone": "results_tabs"}},
        {"dt": 5, "type": "paste", "meta": {"zone": "case_note"}},
    ]
    got = map_events(m, events)
    assert got == ["OPEN_CALCULATOR", "ENTER_HOUSEHOLD", "ENTER_HOUSEHOLD", "READ_RESULT", "CHECK_CLIFF", "RECONCILE", "COPY_TO_NOTE"]
    assert merge(got) == ["OPEN_CALCULATOR", "ENTER_HOUSEHOLD", "READ_RESULT", "CHECK_CLIFF", "RECONCILE", "COPY_TO_NOTE"]


def test_refmap_reformulate_respects_the_window():
    m = yaml.safe_load((BEN / "mapping.yaml").read_text())
    quick = [{"dt": 0, "type": "search"}, {"dt": 10, "type": "search"}]
    slow = [{"dt": 0, "type": "search"}, {"dt": 100, "type": "search"}]
    assert map_events(m, quick) == ["SEARCH", "REFORMULATE"]
    assert map_events(m, slow) == ["SEARCH", "SEARCH"]


def test_refmap_unknown_match_key_raises():
    mapping = {"params": {"reformulate_within_s": 45}, "rules": [{"match": {"bogus": 1}, "cog": "READ"}]}
    with pytest.raises(ValueError):
        map_events(mapping, [{"dt": 0, "type": "nav"}])


def test_zone_outside_vocabulary_is_caught(tmp_path):
    dst = clone_pack(tmp_path, "benefits-processor")
    edit_yaml(dst / "mapping.yaml", lambda d: d["rules"].insert(2, {"match": {"type": "nav", "zone": "mystery_zone"}, "cog": "READ"}))
    assert any("mystery_zone" in e for e in V.validate_pack(dst))


def test_wrong_mapping_vector_is_caught(tmp_path):
    dst = clone_pack(tmp_path, "benefits-processor")
    edit_yaml(dst / "mapping.yaml", lambda d: d["examples"][0]["expect"].__setitem__(0, "READ"))
    assert any("reference mapper gave" in e for e in V.validate_pack(dst))


def test_extra_cog_must_match_mapping_and_be_produced(tmp_path):
    dst = clone_pack(tmp_path, "programmer")
    edit_yaml(dst / "pack.yaml", lambda d: d["cogs"]["extra"].append("NEVER_MAPPED"))
    errs = V.validate_pack(dst)
    assert any("must equal pack.yaml cogs.extra" in e for e in errs)


def test_extra_cog_must_not_shadow_base_cog(tmp_path):
    dst = clone_pack(tmp_path, "programmer")
    edit_yaml(dst / "pack.yaml", lambda d: d["cogs"]["extra"].append("READ"))
    assert any("duplicates a base cog" in e for e in V.validate_pack(dst))


def test_capture_config_zone_must_be_in_vocabulary(tmp_path):
    dst = clone_pack(tmp_path, "data-analyst")
    edit_yaml(dst / "mapping.yaml", lambda d: d["capture_sites"][0]["elements"].append({"zone": "ghost", "selector": "div"}))
    assert any("ghost" in e for e in V.validate_pack(dst))


def test_capture_selector_with_unbalanced_brackets_is_caught(tmp_path):
    dst = clone_pack(tmp_path, "benefits-processor")
    edit_yaml(dst / "tasks" / "sites.yaml", lambda d: d["sites"][0]["capture"]["elements"].append({"zone": "doc", "selector": 'a[href="x"'}))
    assert any("unbalanced" in e for e in V.validate_pack(dst))


def test_onboarding_tools_option_must_name_a_capture_site(tmp_path):
    dst = clone_pack(tmp_path, "benefits-processor")
    edit_yaml(dst / "pack.yaml", lambda d: d["onboarding"]["questions"][0]["options"][0].update(site="zzz"))
    assert any("not a capture site" in e for e in V.validate_pack(dst))


# ---------------------------------------------------------------- as-built sandbox alignment

def test_sites_yaml_matches_the_built_sandbox_specs():
    specs = pytest.importorskip("understudy_agent.sandbox_sites.specs")
    sites = yaml.safe_load((BEN / "tasks" / "sites.yaml").read_text())
    by_id = {s["id"]: s for s in sites["sites"]}
    assert sites["host"] == specs.HOST
    for sid in specs.SITE_IDS:
        spec, mine = specs.SITES[sid], by_id[sid]
        assert mine["port"] == specs.DEFAULT_PORTS[sid]
        assert mine["label"] == spec.name
        assert mine["start_path"] == spec.start_path
        assert mine["result"]["v1"] == spec.result_v1
        assert mine["result"]["v2"] == spec.result_v2
    cn = by_id["case_note"]
    assert cn["path"] == specs.CASENOTE_PATH and cn["served_by"] == specs.CASENOTE_SITE and cn["port"] == specs.DEFAULT_PORTS["a"]
    note = sites["case_note"]
    assert note["draft"] == {"v1": specs.CASENOTE_SAVE["v1"], "v2": specs.CASENOTE_SAVE["v2"]}
    assert note["submit"] == {"v1": specs.CASENOTE_SUBMIT["v1"], "v2": specs.CASENOTE_SUBMIT["v2"]}
    assert note["result"] == specs.CASENOTE_RESULT


def test_household_generator_yaml_matches_the_built_generator_and_oracle():
    households = pytest.importorskip("understudy_agent.sandbox_sites.households")
    oracle = pytest.importorskip("understudy_agent.sandbox_sites.oracle")
    gen = yaml.safe_load((BEN / "tasks" / "household_generator.yaml").read_text())
    assert [a["id"] for a in gen["archetypes"]] == list(households.ARCHETYPES)
    assert set(gen["fields"]) == set(households.generate_households(1)[0].to_dict()) - {"notes"}
    seen_flags: set[str] = set()
    for h in households.generate_households(60):
        seen_flags |= set(oracle.score(h)["cliff_flags"])
    assert {c["id"] for c in gen["cliffs"]} == seen_flags
    assert gen["seed"] == 2026 and gen["default_count"] == 20


def test_task_yaml_matches_the_oracle_and_result_fields():
    oracle = pytest.importorskip("understudy_agent.sandbox_sites.oracle")
    task = yaml.safe_load((BEN / "tasks" / "task.yaml").read_text())
    households = pytest.importorskip("understudy_agent.sandbox_sites.households")
    keys = set(oracle.score(households.generate_households(1)[0]))
    assert set(task["oracle"]["returns"]) <= keys
    assert task["result_fields"] == ["amount", "status", "ref"]
    assert "not law" in task["oracle"]["label"].lower()
    for forbidden in ("child_benefit", "housing_support", "council_tax"):
        assert forbidden not in (BEN / "tasks" / "task.yaml").read_text()


def test_the_irreversible_submit_button_matches_the_risk_patterns():
    import re
    pack = yaml.safe_load((BEN / "pack.yaml").read_text())
    label = "Submit to claimant record"
    assert any(re.search(p, label, re.I) for p in pack["risk_classes"]["irreversible"])
    # and the draft button is not irreversible
    assert not any(re.search(p, "Save draft", re.I) for p in pack["risk_classes"]["irreversible"])


def test_capture_hosts_are_derivable_from_sites_yaml():
    sites = yaml.safe_load((BEN / "tasks" / "sites.yaml").read_text())
    hosts = {f"{sites['host']}:{s['port']}" for s in sites["sites"] if s["kind"] == "calculator"}
    assert hosts == {"127.0.0.1:7801", "127.0.0.1:7802", "127.0.0.1:7803"}


def test_sandbox_sites_use_the_reserved_ports():
    sites = yaml.safe_load((BEN / "tasks" / "sites.yaml").read_text())
    assert sorted({s["port"] for s in sites["sites"]}) == [7801, 7802, 7803]


# ---------------------------------------------------------------- plugin_refs (ROL-5)

def test_plugin_refs_sample_is_accepted_and_ignored(tmp_path):
    sample = yaml.safe_load((Path(__file__).parent / "fixtures" / "plugin_refs.sample.yaml").read_text())
    dst = clone_pack(tmp_path, "data-analyst")
    edit_yaml(dst / "pack.yaml", lambda d: d.update(plugin_refs=sample["plugin_refs"]))
    assert V.validate_pack(dst) == []


def test_plugin_refs_bad_kind_is_rejected(tmp_path):
    dst = clone_pack(tmp_path, "data-analyst")
    edit_yaml(dst / "pack.yaml", lambda d: d.update(plugin_refs=[{"id": "x/y", "kind": "bogus"}]))
    assert any("plugin_refs" in e for e in V.validate_pack(dst))


# ---------------------------------------------------------------- the validator catches mistakes

def test_unknown_top_level_key_rejected(tmp_path):
    dst = clone_pack(tmp_path, "programmer")
    edit_yaml(dst / "pack.yaml", lambda d: d.update(surprise=1))
    assert V.validate_pack(dst)


def test_deep_pack_requires_oracle_tasks_and_full_policy(tmp_path):
    dst = clone_pack(tmp_path, "benefits-processor")
    edit_yaml(dst / "pack.yaml", lambda d: d.pop("oracle"))
    assert any("oracle" in e for e in V.validate_pack(dst))


def test_oracle_must_be_labelled_not_law(tmp_path):
    dst = clone_pack(tmp_path, "benefits-processor")
    edit_yaml(dst / "pack.yaml", lambda d: d.update(oracle_note="Authoritative entitlement engine."))
    assert any("not law" in e for e in V.validate_pack(dst))


def test_thin_pack_cannot_claim_full_policy(tmp_path):
    dst = clone_pack(tmp_path, "data-analyst")
    edit_yaml(dst / "pack.yaml", lambda d: d["expert_policy"].update(coverage="full"))
    assert V.validate_pack(dst)


def test_question_order_enforced(tmp_path):
    dst = clone_pack(tmp_path, "programmer")
    edit_yaml(dst / "pack.yaml", lambda d: d["onboarding"]["questions"].reverse())
    assert any("question ids" in e for e in V.validate_pack(dst))


def test_path_traversal_rejected(tmp_path):
    dst = clone_pack(tmp_path, "programmer")
    edit_yaml(dst / "pack.yaml", lambda d: d.update(routines="../data-analyst/routines.yaml"))
    assert V.validate_pack(dst)


def test_missing_file_reported(tmp_path):
    dst = clone_pack(tmp_path, "programmer")
    (dst / "priors.yaml").unlink()
    assert any("priors" in e for e in V.validate_pack(dst))


def test_expert_steps_cycle_and_unknown_after(tmp_path):
    dst = clone_pack(tmp_path, "programmer")
    edit_yaml(dst / "expert_steps.yaml", lambda d: d["checks"][0].update(after=["rerun_and_confirm"]))
    assert any("cycle" in e for e in V.validate_pack(dst))
    dst2 = clone_pack(tmp_path / "b", "programmer")
    edit_yaml(dst2 / "expert_steps.yaml", lambda d: d["checks"][1].update(after=["ghost"]))
    assert any("unknown 'after'" in e for e in V.validate_pack(dst2))


def test_persona_unknown_skill_and_template(tmp_path):
    dst = clone_pack(tmp_path, "benefits-processor")
    edit_yaml(dst / "persona.yaml", lambda d: d["apprentice"]["deficits"][0].update(skill="ghost-skill"))
    assert any("unknown skill" in e for e in V.validate_pack(dst))
    dst2 = clone_pack(tmp_path / "b", "benefits-processor")
    edit_yaml(dst2 / "persona.yaml", lambda d: d["planted_routines"][0].update(template="ghost-template"))
    assert any("unknown template" in e for e in V.validate_pack(dst2))


def test_site_ports_outside_range_rejected(tmp_path):
    dst = clone_pack(tmp_path, "benefits-processor")
    edit_yaml(dst / "tasks" / "sites.yaml", lambda d: d["sites"][0].update(port=8000))
    assert V.validate_pack(dst)


def test_compare_packs_flags_identical_tone():
    a = yaml.safe_load((PACKS / "data-analyst" / "pack.yaml").read_text())
    b = copy.deepcopy(a)
    b["cogs"]["extra"] = ["OTHER_COG"]
    b["risk_classes"]["irreversible"] = ["zzz"]
    for q in b["onboarding"]["questions"]:
        q["prompt"] = "different " + q["prompt"]
        for o in q.get("options", []):
            o["value"] = "x_" + o["value"]
    b["onboarding"]["questions"][4]["default_hours"] = {"start": "01:00", "end": "02:00", "days": ["sat"]}
    assert V.compare_packs({"a": a, "b": b}) == ["a vs b: tone defaults are identical"]


# ---------------------------------------------------------------- steps DSL schema

def good_bundle() -> dict:
    return json.loads((SCHEMA / "examples" / "steps.calc_entry.example.json").read_text())


def test_steps_example_valid_and_uses_site_a_selectors():
    b = good_bundle()
    assert not list(validator("steps.schema.json").iter_errors(b))
    assert b["steps"][0]["op"] == "goto"
    assert [s["op"] for s in b["steps"][-3:]] == ["click", "wait_for", "extract"]     # the cliff check ends the bundle
    assert b["steps"][-3]["selector"] == "#cliff-btn" and b["steps"][-2]["selector"].startswith("#cliff-panel")
    assert {s["op"] for s in b["steps"]} == {"goto", "fill", "select", "click", "wait_for", "extract", "checkpoint"}
    assert not any(s["selector"] == "#submit-note" for s in b["steps"] if "selector" in s)


@pytest.mark.parametrize("mutate", [
    lambda b: b["steps"][2].pop("postcondition"),
    lambda b: b["steps"][2].pop("precondition"),
    lambda b: b["steps"][2].update(op="eval", code="alert(1)"),
    lambda b: b["steps"][2].update(role="textbox", name="Your age"),         # selector and role+name together
    lambda b: b["steps"][2].pop("selector"),                                 # neither
    lambda b: b["steps"][2].update(value="123 Real Street"),                 # literal value instead of a param slot
    lambda b: b["steps"][0].update(url="javascript:alert(1)"),
    lambda b: b["steps"][3].update(extra="x"),
    lambda b: b["steps"][2].update(precondition={}),
    lambda b: b["steps"][2].pop("param"),
    lambda b: b["params"].update(**{"Bad Name": {"type": "string"}}),
    lambda b: b["params"]["tenure"].pop("values"),
    lambda b: b["steps"][2].update(selector="javascript:alert(1)"),
])
def test_steps_invalid_bundles_rejected(mutate):
    b = good_bundle()
    mutate(b)
    assert list(validator("steps.schema.json").iter_errors(b))


@pytest.mark.parametrize("op,step", [
    ("goto", {"url": "http://127.0.0.1:7801/step/1"}),
    ("click", {"selector": "button"}),
    ("click", {"role": "button", "name": "Calculate"}),
    ("fill", {"role": "textbox", "name": "Notes", "param": "adults"}),
    ("select", {"selector": "select", "option": "England"}),
    ("wait_for", {"text": {"literal": "Result"}}),
    ("assert_text", {"param": "adults"}),
    ("extract", {"name": "total", "selector": ".t"}),
    ("checkpoint", {"name": "mid"}),
])
def test_every_dsl_op_has_a_valid_form(op, step):
    b = good_bundle()
    b["steps"] = [{"id": "s1", "op": op, "precondition": {"always": True}, "postcondition": {"always": True}, **step}]
    assert not list(validator("steps.schema.json").iter_errors(b))


# ---------------------------------------------------------------- other schemas

def test_routine_schema_accepts_api_example_and_bare_proposal():
    v = validator("routine.schema.json")
    for name in ("routine.calc_entry.example.json", "routine.bare_proposal.example.json"):
        assert not list(v.iter_errors(json.loads((SCHEMA / "examples" / name).read_text())))


def test_routine_schema_rejects_bad_rung_and_unknown_key():
    v = validator("routine.schema.json")
    r = json.loads((SCHEMA / "examples" / "routine.calc_entry.example.json").read_text())
    assert list(v.iter_errors({**r, "rung": "A9"}))
    assert list(v.iter_errors({**r, "surprise": 1}))


def test_queue_item_schema():
    v = validator("queue_item.schema.json")
    q = json.loads((SCHEMA / "examples" / "queue_item.example.json").read_text())
    assert not list(v.iter_errors(q))
    assert list(v.iter_errors({**q, "kind": "other"}))
    assert list(v.iter_errors({**q, "status": "maybe"}))
    assert list(v.iter_errors({**q, "id": "01"}))


def test_memory_frontmatter_schema():
    v = validator("memory.frontmatter.schema.json")
    fm = json.loads((SCHEMA / "examples" / "memory.frontmatter.example.json").read_text())
    assert not list(v.iter_errors(fm))
    assert list(v.iter_errors({"role": "benefits-processor"}))             # revision required
    assert list(v.iter_errors({"role": "Benefits", "revision": 1}))
    assert not list(v.iter_errors({"role": "programmer", "revision": 0}))  # extra keys are kept, minimal is fine


def test_ext_rect_protocol():
    v = validator("ext_rect.schema.json")
    ex = SCHEMA / "examples"
    for name in ("ext_rect.want.example.json", "ext_rect.want_by_role.example.json", "ext_rect.want_by_zone.example.json",
                 "ext_rect.answer.example.json", "ext_rect.answer_full.example.json", "ext_rect.answer_not_found.example.json"):
        assert not list(v.iter_errors(json.loads((ex / name).read_text()))), name
    want = json.loads((ex / "ext_rect.want.example.json").read_text())
    assert list(v.iter_errors({**want, "role": "button", "name": "Go"}))        # label_hash and role together
    assert list(v.iter_errors({**want, "zone": "cliff_button"}))                # label_hash and zone together
    zone = json.loads((ex / "ext_rect.want_by_zone.example.json").read_text())
    assert list(v.iter_errors({**zone, "role": "button", "name": "Go"}))        # zone and role+name together
    assert list(v.iter_errors({**zone, "zone": "Cliff Button"}))
    full = json.loads((ex / "ext_rect.answer_full.example.json").read_text())
    assert list(v.iter_errors({**full, "viewport": {"w": 1280}}))               # w and h both required
    assert list(v.iter_errors({**full, "screen": {"x": 0, "y": 0, "z": 1}}))
    ans = json.loads((ex / "ext_rect.answer.example.json").read_text())
    no_rect = {k: x for k, x in ans.items() if k != "rect"}
    assert list(v.iter_errors(no_rect))                                         # found defaults to true: rect required


def test_event_schema_example_and_lead_files_untouched():
    v = validator("event.schema.json")
    assert not list(v.iter_errors(json.loads((SCHEMA / "examples" / "event.l0.example.json").read_text())))
    sens = json.loads((SCHEMA / "sensitive_fields.json").read_text())
    assert "autocomplete_tokens" in sens and "input_types" in sens and sens["patterns"]


def test_event_schema_accepts_zone_meta_and_rejects_urls_in_meta():
    v = validator("event.schema.json")
    ev = json.loads((SCHEMA / "examples" / "event.l0.example.json").read_text())
    ev["meta"] = {"zone": "household_form", "depth_bin": 2}
    assert not list(v.iter_errors(ev))
    ev["meta"] = {"zone": "https://evil.example/x"}
    assert list(v.iter_errors(ev))


@pytest.mark.parametrize("pack", PACK_IDS)
def test_pack_sensitive_lists_compile_and_extend_global(pack):
    data = json.loads((PACKS / pack / "sensitive_fields.json").read_text())
    assert data["extends"].endswith("schema/sensitive_fields.json")
    assert (PACKS / pack / data["extends"]).resolve() == (SCHEMA / "sensitive_fields.json").resolve()


# ---------------------------------------------------------------- the engine's real mapper agrees

@pytest.mark.parametrize("pack", PACK_IDS)
def test_engine_mapper_agrees_with_every_mapping_example(pack):
    """Run each pack's test vectors through the engine's own rule matcher, not just the reference mapper."""
    mapper = pytest.importorskip("understudy_engine.cogs.mapper")
    from datetime import datetime, timedelta, timezone

    from understudy_engine.core import Event

    doc = yaml.safe_load((PACKS / pack / "mapping.yaml").read_text())
    mp = mapper.compile_mapping(doc)
    assert mp.extra_cogs == tuple(doc["extra_cogs"])
    for ex in doc["examples"]:
        t = datetime(2026, 11, 7, 9, 0, tzinfo=timezone.utc)
        prev_cog, prev_t, got = None, None, []
        for i, e in enumerate(ex["events"]):
            t = t + timedelta(seconds=e["dt"])
            ev = Event(**{"schema": 1, "id": f"ev_{i:06d}", "t": t, "origin": "synthetic", "actor": "human",
                          "person": "p_test", "role": pack, "source": e.get("source", "browser"), "type": e["type"],
                          "target": {"role": e["role"]} if e.get("role") else None, "meta": e.get("meta", {})})
            rule = mp.classify(ev)
            cog = rule.cog if rule else None
            if cog and rule.reformulate_as and prev_cog in ("SEARCH", "REFORMULATE") \
                    and (t - prev_t).total_seconds() <= mp.params["reformulate_within_s"]:
                cog = rule.reformulate_as
            got.append(cog)
            if cog:
                prev_cog, prev_t = cog, t
        assert got == ex["expect"], (pack, ex["name"])


# ---------------------------------------------------------------- the built sites really serve the cliff panel

def test_built_sites_serve_the_cliff_button_and_panel():
    """Render a result page and the /cliff panel in-process and compare with sites.yaml `cliff` and `capture`."""
    pytest.importorskip("starlette.testclient")
    sites_mod = pytest.importorskip("understudy_agent.sandbox_sites.sites")
    specs = pytest.importorskip("understudy_agent.sandbox_sites.specs")
    from starlette.testclient import TestClient

    cfg = yaml.safe_load((BEN / "tasks" / "sites.yaml").read_text())
    cliff = cfg["cliff"]
    apps = sites_mod.make_apps(sites_mod.SandboxState(), {"a": 7801, "b": 7802, "c": 7803})
    spec = specs.SITES["b"]
    for layout in ("v1", "v2"):
        keys = spec.fields(layout)
        form = {keys["adults"]: "1", keys["adult1_age"]: "34", keys["adult2_age"]: "", keys["children_ages"]: "",
                keys["adult1_earnings_monthly"]: "900", keys["adult2_earnings_monthly"]: "0",
                keys["limited_capability"]: "no", keys["tenure"]: "rent", keys["rent_monthly"]: "500",
                keys["bedrooms"]: "1", keys["savings"]: "15900", keys["childcare_monthly"]: "0"}
        client = TestClient(apps["b"])
        suffix = "" if layout == "v1" else "?layout=v2"
        r = client.post(f"/calculate{suffix}", data=form)
        assert r.status_code == 200, r.text[:200]
        html = r.text
        assert f'id="{cliff["button"].lstrip("#")}"' in html and f'id="{cliff["panel"].lstrip("#")}"' in html
        assert 'data-understudy-zone="cliff_button"' in html and 'data-understudy-zone="cliff_panel"' in html
        assert cliff["button_label"] in html
        import re
        ref = re.search(r'data-url="/cliff\?([^"]+)"', html)
        assert ref, "the button must carry the /cliff url"
        panel = client.get("/cliff?" + ref.group(1).replace("&amp;", "&"))
        assert panel.status_code == 200
        ids = re.findall(r'data-cliff="([a-z_]+)" data-near="(yes|no)"', panel.text)
        assert [i for i, _ in ids] == cliff["ids"]
        # savings 15900 is near the capital limit and must be flagged
        assert dict(ids)["capital_limit"] == "yes"


# ---------------------------------------------------------------- templates match what the engine plants

def _lev(a: list[str], b: list[str]) -> int:
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        cur = [i]
        for j, y in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (x != y)))
        prev = cur
    return prev[-1]


def test_every_routine_the_engine_plants_has_a_template_that_matches_its_nominal_sequence():
    """The finder names a routine after the template it matches; a mismatch gives auto-xxxx ids."""
    profiles = pytest.importorskip("understudy_engine.personas.profiles")
    tasks = pytest.importorskip("understudy_engine.personas.tasks")
    templates = {t["id"]: t for t in yaml.safe_load((BEN / "routines.yaml").read_text())["templates"]}
    specs = {r.name: r for persona in profiles.PERSONAS for r in persona.routines}
    assert specs, "the engine plants no routines?"
    for name, spec in specs.items():
        assert name in templates, f"pack has no template for planted routine {name}"
        nominal = tasks.nominal_template(spec)
        t = templates[name]
        dist = _lev(nominal, t["cogs"]) / max(len(nominal), len(t["cogs"]))
        assert dist <= t["match_distance"], (name, dist, nominal, t["cogs"])


def test_persona_planted_routines_name_pack_templates():
    persona = yaml.safe_load((BEN / "persona.yaml").read_text())
    templates = {t["id"] for t in yaml.safe_load((BEN / "routines.yaml").read_text())["templates"]}
    assert {r["id"] for r in persona["planted_routines"]} <= templates
    assert {"calc-entry-3x", "case-note-copy", "cliff-recheck", "queue-sweep", "weekly-report"} <= templates


# ---------------------------------------------------------------- param transform (unit conversion)

def site_c_bundle() -> dict:
    return json.loads((SCHEMA / "examples" / "steps.calc_entry_c.example.json").read_text())


def test_site_c_example_validates_and_carries_the_unit_transforms():
    b = site_c_bundle()
    assert not list(validator("steps.schema.json").iter_errors(b))
    t = {k: v["transform"] for k, v in b["params"].items() if "transform" in v}
    assert t["adult1_earnings_monthly"] == {"mul": 12.0, "round": 2}
    assert t["adult2_earnings_monthly"] == {"mul": 12.0, "round": 2}
    assert t["rent_monthly"]["mul"] == pytest.approx(12 / 52) and t["childcare_monthly"]["round"] == 2
    assert set(t) == {"adult1_earnings_monthly", "adult2_earnings_monthly", "rent_monthly", "childcare_monthly"}


def test_site_c_example_transforms_equal_the_sandbox_spec():
    specs = pytest.importorskip("understudy_agent.sandbox_sites.specs")
    b = site_c_bundle()
    got = {k: (v["transform"]["mul"], v["transform"]["round"]) for k, v in b["params"].items() if "transform" in v}
    assert got == specs.SITES["c"].transforms
    # the bundle's selectors are the spec's testid selectors; the two panels are separated by the next-tab click
    sels = {s["selector"] for s in b["steps"] if "selector" in s}
    assert specs.SITES["c"].selector("adult1_earnings_monthly") in sels
    assert specs.SITES["c"].buttons()[0] in sels and specs.SITES["c"].buttons()[1] in sels


def test_site_c_transform_applied_gives_the_values_the_site_expects():
    """Typing the household's monthly figure through the declared transform gives the annual or weekly number."""
    specs = pytest.importorskip("understudy_agent.sandbox_sites.specs")
    households = pytest.importorskip("understudy_agent.sandbox_sites.households")
    b = site_c_bundle()
    h = next(x for x in households.generate_households(20, 2026) if x.archetype == "lone_parent_childcare")
    params = h.params()
    for name in ("adult1_earnings_monthly", "rent_monthly", "childcare_monthly"):
        tr = b["params"][name]["transform"]
        typed = f"{round(float(params[name]) * tr['mul'], tr['round']):.{tr['round']}f}"
        assert typed == specs.bound_value(specs.SITES["c"], name, params)


@pytest.mark.parametrize("transform,ok", [
    ({"mul": 12.0, "round": 2}, True),
    ({"mul": 12}, True),                          # round is optional: leave unrounded
    ({"mul": 0.5, "round": 0}, True),
    ({"round": 2}, False),                        # mul is required
    ({"mul": "12", "round": 2}, False),
    ({"mul": 0, "round": 2}, False),
    ({"mul": -1, "round": 2}, False),
    ({"mul": 12, "round": -1}, False),
    ({"mul": 12, "round": 2.5}, False),
    ({"mul": 12, "round": 9}, False),
    ({"mul": 12, "round": 2, "add": 5}, False),   # no other operations
    ("x12", False),
])
def test_param_transform_forms(transform, ok):
    b = good_bundle()
    b["params"]["earnings"] = {"type": "number", "source": "household.params.adult1_earnings_monthly", "transform": transform}
    assert (not list(validator("steps.schema.json").iter_errors(b))) is ok


# ---------------------------------------------------------------- task markers (task_start, progress, task_end)

def test_calculator_sites_declare_task_markers_that_match_the_sandbox_selectors():
    specs = pytest.importorskip("understudy_agent.sandbox_sites.specs")
    cfg = yaml.safe_load((BEN / "tasks" / "sites.yaml").read_text())
    for s in cfg["sites"]:
        if s["kind"] != "calculator":
            continue
        mk = s["capture"]["markers"]
        assert mk["task_start"] == {"zone": "calc_site", "idle_s": 120}
        result_read = next(p for p in mk["progress"] if p["kind"] == "result_read")["when"]
        spec = specs.SITES[s["id"]]
        for selector in (spec.result_v1["amount"], spec.result_v2["amount"]):
            assert selector in result_read, (s["id"], selector)
    a = next(s for s in cfg["sites"] if s["id"] == "a")["capture"]["markers"]
    status = [specs.CASENOTE_RESULT["v1"]["status"], specs.CASENOTE_RESULT["v2"]["status"]]
    note = next(p for p in a["progress"] if p["kind"] == "note_field")["when"]
    assert all(sel in note for sel in status) and all(sel in a["task_end"]["when"] for sel in status)
    assert a["task_end"]["reason"] == "note_saved"
    # the case note page is only on site a's port, so only site a carries the note markers
    for s in cfg["sites"]:
        if s["id"] in ("b", "c"):
            assert "task_end" not in s["capture"]["markers"]


def test_marker_zone_must_be_in_the_vocabulary(tmp_path):
    dst = clone_pack(tmp_path, "benefits-processor")
    edit_yaml(dst / "tasks" / "sites.yaml", lambda d: d["sites"][0]["capture"]["markers"]["task_start"].update(zone="mystery_zone"))
    assert any("mystery_zone" in e for e in V.validate_pack(dst))


def test_progress_markers_need_a_task_start(tmp_path):
    dst = clone_pack(tmp_path, "benefits-processor")
    edit_yaml(dst / "tasks" / "sites.yaml", lambda d: d["sites"][1]["capture"]["markers"].pop("task_start"))
    assert any("without a task_start" in e for e in V.validate_pack(dst))


def test_marker_selector_with_unbalanced_brackets_is_caught(tmp_path):
    dst = clone_pack(tmp_path, "benefits-processor")
    edit_yaml(dst / "tasks" / "sites.yaml", lambda d: d["sites"][0]["capture"]["markers"]["progress"][0].update(when='a[href="x"'))
    assert any("unbalanced" in e for e in V.validate_pack(dst))


@pytest.mark.parametrize("markers,ok", [
    ({"task_start": {"zone": "calc_site", "idle_s": 120}}, True),
    ({"task_start": {"zone": "calc_site", "idle_s": 5}}, False),                       # too short to mean a new case
    ({"task_start": {"zone": "calc_site"}}, False),
    ({"progress": [{"kind": "Result Read", "when": "#x"}]}, False),                    # kind is an enum token
    ({"task_end": {"when": "#x"}}, False),                                             # reason is required
    ({"surprise": 1}, False),
])
def test_markers_schema_forms(markers, ok):
    v = def_validator_for("zoneMarkers")
    assert (not list(v.iter_errors(markers))) is ok


def def_validator_for(name: str):
    return V.def_validator(name)


# ---------------------------------------------------------------- the reconciliation select (zone reconcile_control)

def test_reconcile_control_zone_is_in_the_vocabulary_the_capture_config_and_the_engine_rule():
    m = yaml.safe_load((BEN / "mapping.yaml").read_text())
    assert "reconcile_control" in m["zones"]
    assert {"match": {"type": ["click", "focus"], "zone": "reconcile_control"}, "cog": "RECONCILE", "starts": True} in m["rules"]
    cfg = yaml.safe_load((BEN / "tasks" / "sites.yaml").read_text())
    site_a = next(s for s in cfg["sites"] if s["id"] == "a")["capture"]["elements"]
    order = [e["zone"] for e in site_a]
    assert order.index("reconcile_control") < order.index("case_note")        # it must win over the broader note zone
    sel = next(e["selector"] for e in site_a if e["zone"] == "reconcile_control")
    assert 'data-understudy-zone="reconcile_control"' in sel
    for s in cfg["sites"]:
        if s["id"] in ("b", "c"):
            assert "reconcile_control" not in [e["zone"] for e in s["capture"]["elements"]]     # the note page is only on site a's port


def test_reconcile_control_selectors_match_the_built_sandbox_markup():
    specs = pytest.importorskip("understudy_agent.sandbox_sites.specs")
    pytest.importorskip("starlette.testclient")
    sites_mod = pytest.importorskip("understudy_agent.sandbox_sites.sites")
    from starlette.testclient import TestClient
    import re

    cfg = yaml.safe_load((BEN / "tasks" / "sites.yaml").read_text())
    sel = next(e["selector"] for e in next(s for s in cfg["sites"] if s["id"] == "a")["capture"]["elements"] if e["zone"] == "reconcile_control")
    assert specs.CASENOTE_FIELDS_V1["reconciliation"] in sel and specs.CASENOTE_FIELDS_V2["reconciliation"] in sel
    app = sites_mod.make_apps(sites_mod.SandboxState(), {"a": 7801, "b": 7802, "c": 7803})["a"]
    for q, field in (("", specs.CASENOTE_FIELDS_V1["reconciliation"]), ("&layout=v2", specs.CASENOTE_FIELDS_V2["reconciliation"])):
        html = TestClient(app).get(f"/casenote?case=CASE-1005{q}").text
        tag = re.search(r'<select[^>]*data-understudy-zone="reconcile_control"[^>]*>', html)
        assert tag, f"the reconciliation select must carry the zone attribute ({q or 'v1'})"
        assert f'id="{field.lstrip("#")}"' in tag.group(0)
        assert html.count('data-understudy-zone="reconcile_control"') == 1
