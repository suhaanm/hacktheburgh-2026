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
from refmap import map_events

PACKS = Path(__file__).resolve().parents[1]
SCHEMA = V.SCHEMA_DIR
PACK_IDS = ["benefits-processor", "data-analyst", "programmer"]


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
    deep = yaml.safe_load((PACKS / "benefits-processor" / "pack.yaml").read_text())
    assert deep["depth"] == "deep" and deep["oracle"] == "understudy_agent.sandbox_sites.oracle:score"
    assert deep["expert_policy"]["coverage"] == "full" and (PACKS / "benefits-processor" / "tasks").is_dir()
    for thin in ("data-analyst", "programmer"):
        d = yaml.safe_load((PACKS / thin / "pack.yaml").read_text())
        assert d["depth"] == "thin"
        assert "oracle" not in d and "tasks" not in d
        assert d["expert_policy"]["coverage"] == "stub"


def test_benefits_pack_has_the_spec_cogs_and_five_questions():
    d = yaml.safe_load((PACKS / "benefits-processor" / "pack.yaml").read_text())
    assert d["cogs"]["extra"] == ["ENTER_HOUSEHOLD", "OPEN_CALCULATOR", "READ_RESULT", "CHECK_CLIFF", "COPY_TO_NOTE", "RECONCILE"]
    assert [q["id"] for q in d["onboarding"]["questions"]] == ["tools", "risky", "tone", "pace", "hours"]


def test_sandbox_sites_use_the_reserved_ports():
    sites = yaml.safe_load((PACKS / "benefits-processor" / "tasks" / "sites.yaml").read_text())
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


def test_extra_cog_must_not_shadow_base_cog(tmp_path):
    dst = clone_pack(tmp_path, "programmer")
    edit_yaml(dst / "pack.yaml", lambda d: d["cogs"]["extra"].append("READ"))
    assert any("duplicates a base cog" in e for e in V.validate_pack(dst))


def test_extra_cog_must_be_produced_by_a_rule(tmp_path):
    dst = clone_pack(tmp_path, "programmer")
    edit_yaml(dst / "pack.yaml", lambda d: d["cogs"]["extra"].append("NEVER_MAPPED"))
    assert any("never produced" in e for e in V.validate_pack(dst))


def test_wrong_mapping_vector_is_caught(tmp_path):
    dst = clone_pack(tmp_path, "benefits-processor")
    edit_yaml(dst / "mapping.yaml", lambda d: d["examples"][0]["expect"].__setitem__(0, "READ"))
    assert any("reference mapper gave" in e for e in V.validate_pack(dst))


def test_undeclared_role_in_rule_is_caught(tmp_path):
    dst = clone_pack(tmp_path, "data-analyst")
    edit_yaml(dst / "mapping.yaml", lambda d: d["role_rules"][0]["when"].update(domain_role="nowhere"))
    assert any("not declared" in e for e in V.validate_pack(dst))


def test_label_vocab_cannot_hit_sensitive_fields(tmp_path):
    dst = clone_pack(tmp_path, "data-analyst")
    edit_yaml(dst / "mapping.yaml", lambda d: d["label_roles"]["editor"]["vocab"].append("password"))
    assert any("sensitive" in e for e in V.validate_pack(dst))


def test_universal_credit_label_would_be_flagged(tmp_path):
    # the global list matches the word credit; a pack must not put it in its label vocabulary
    dst = clone_pack(tmp_path, "benefits-processor")
    edit_yaml(dst / "mapping.yaml", lambda d: d["label_roles"]["result_panel"]["vocab"].append("universal credit"))
    assert any("sensitive" in e for e in V.validate_pack(dst))


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
    errs = V.compare_packs({"a": a, "b": b})
    assert errs == ["a vs b: tone defaults are identical"]


# ---------------------------------------------------------------- reference mapper

def test_refmap_hand_made_trace():
    mapping = yaml.safe_load((PACKS / "benefits-processor" / "mapping.yaml").read_text())
    roles = {"domain": {"calc_a": ["d:a001"]}, "label": {"threshold_field": ["h:0201"], "calculate": ["h:0301"]}}
    events = [
        {"dt": 0, "type": "nav", "target": {"domain_hash": "d:a001"}},
        {"dt": 5, "type": "scroll", "target": {"domain_hash": "d:a001"}},
        {"dt": 5, "type": "focus", "target": {"role": "spinbutton", "label_hash": "h:0201", "domain_hash": "d:a001"}},
    ]
    # scroll with no ENTER before it is just READ; a threshold field edit without a prior READ_RESULT is ENTER_HOUSEHOLD
    assert map_events(mapping, events, roles) == ["OPEN_CALCULATOR", "READ", "ENTER_HOUSEHOLD"]


def test_refmap_unknown_predicate_raises():
    mapping = {"base_rules": [{"id": "x", "when": {"bogus": 1}, "cog": "READ"}]}
    with pytest.raises(ValueError):
        map_events(mapping, [{"dt": 0, "type": "nav"}], {})


# ---------------------------------------------------------------- steps DSL schema

def good_bundle() -> dict:
    return json.loads((SCHEMA / "examples" / "steps.calc_entry.example.json").read_text())


def test_steps_example_valid():
    assert not list(validator("steps.schema.json").iter_errors(good_bundle()))


@pytest.mark.parametrize("mutate", [
    lambda b: b["steps"][1].pop("postcondition"),
    lambda b: b["steps"][1].pop("precondition"),
    lambda b: b["steps"][1].update(op="eval", code="alert(1)"),
    lambda b: b["steps"][1].update(selector="#x"),                 # selector and role+name together
    lambda b: (b["steps"][1].pop("role"), b["steps"][1].pop("name")),   # neither
    lambda b: b["steps"][1].update(value="123 Real Street"),       # literal value instead of a param slot
    lambda b: b["steps"][0].update(url="javascript:alert(1)"),
    lambda b: b["steps"][4].update(extra="x"),
    lambda b: b["steps"][1].update(precondition={}),
    lambda b: b["steps"][2].pop("param"),
    lambda b: b["steps"][7].pop("literal"),
    lambda b: b["params"].update(**{"Bad Name": {"type": "string"}}),
    lambda b: b["params"]["region"].pop("values"),
    lambda b: b["steps"][5].update(selector="javascript:alert(1)"),
])
def test_steps_invalid_bundles_rejected(mutate):
    b = good_bundle()
    mutate(b)
    assert list(validator("steps.schema.json").iter_errors(b))


@pytest.mark.parametrize("op,step", [
    ("goto", {"url": "http://localhost:7801/"}),
    ("click", {"selector": "button"}),
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
        assert not list((v.iter_errors(json.loads((SCHEMA / "examples" / name).read_text()))))


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
    for name in ("ext_rect.want.example.json", "ext_rect.want_by_role.example.json",
                 "ext_rect.answer.example.json", "ext_rect.answer_not_found.example.json"):
        assert not list(v.iter_errors(json.loads((ex / name).read_text()))), name
    want = json.loads((ex / "ext_rect.want.example.json").read_text())
    assert list(v.iter_errors({**want, "role": "button", "name": "Go"}))        # label_hash and role together
    ans = json.loads((ex / "ext_rect.answer.example.json").read_text())
    no_rect = {k: x for k, x in ans.items() if k != "rect"}
    assert list(v.iter_errors(no_rect))                                         # found defaults to true: rect required


def test_event_schema_example_and_lead_files_untouched():
    v = validator("event.schema.json")
    assert not list(v.iter_errors(json.loads((SCHEMA / "examples" / "event.l0.example.json").read_text())))
    sens = json.loads((SCHEMA / "sensitive_fields.json").read_text())
    assert "autocomplete_tokens" in sens and "input_types" in sens and sens["patterns"]


@pytest.mark.parametrize("pack", PACK_IDS)
def test_pack_sensitive_lists_compile_and_extend_global(pack):
    data = json.loads((PACKS / pack / "sensitive_fields.json").read_text())
    assert data["extends"].endswith("schema/sensitive_fields.json")
    assert (PACKS / pack / data["extends"]).resolve() == (SCHEMA / "sensitive_fields.json").resolve()
