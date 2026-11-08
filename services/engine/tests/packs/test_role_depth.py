"""RD (7 Nov 2026): the deeper programmer and data-analyst packs must not move anything the role studies, the sandboxes and the frozen
evaluations depend on, and everything new must be complete and inert where it should be.

Frozen means: the ids, the order and the CONTENT of the first ten cogs, the original skills, expert checks, routine template, mapping rules,
sandbox capture site and the persona, priors-free generator files. The hashes below were computed from the files at git HEAD before the
role-depth track touched them (``json.dumps(..., sort_keys=True)`` of the parsed YAML, sha256, first 16 hex digits).
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest
import yaml

from understudy_engine.coach.steps import StepPolicy
from understudy_engine.cogs import to_cogs
from understudy_engine.core import Event
from understudy_engine.packs import load_pack
from understudy_engine.packs.loader import packs_dir

REPO = Path(__file__).resolve().parents[4]
ROLES = ("programmer", "data-analyst")

FROZEN = {
    "programmer": {
        "n": {"cogs": 10, "skills": 6, "checks": 8, "templates": 1},
        "checks": "3298851562107b33", "skills": "0257b73eb3b11fcf", "templates": "05205d03b93f4b40", "rules": "d448a06020804743",
        "params": "7402c9696edcf86a", "sandbox_site": "49934140fa3d9e1d", "persona_file": "8e29a48ac97400b9", "routine_expert_file": "295c9864e792991d",
        "tools": ["git_host", "ci_dashboard", "issue_tracker", "docs_site", "chat"],
        "risky": ["force_push", "delete_branch", "merge_main", "deploy_publish", "post_comment"],
        "defaults": {"tools": ["git_host", "ci_dashboard"], "risky": ["force_push", "delete_branch", "merge_main", "deploy_publish"], "tone": ["short"], "pace": ["quick"]},
        "zones": ["code_view", "code_editor", "test_runner", "ci_log", "diff_view", "commit_box", "docs_page", "edge_probe", "input_data", "test_editor", "test_report",
                  "doc", "form_field", "search_box", "query_edit", "compare_view", "check_box", "decision_btn", "help"],
        "new_zones": {"repro_console", "history_view", "commit_message", "pr_form", "ci_checks", "review_thread", "review_composer", "prod_logs", "rollback_control",
                      "logging_panel", "profiler_view", "migration_editor"},
        "planted": ["rerun-failed-ci"],
    },
    "data-analyst": {
        "n": {"cogs": 10, "skills": 5, "checks": 7, "templates": 1},
        "checks": "fb9f97bd0bbf87e4", "skills": "1e43808c33dea8cd", "templates": "6c8537156ac9603b", "rules": "516ce8633b74f736",
        "params": "d16b0d249a62d747", "sandbox_site": "128c5ef3af3b2766", "persona_file": "c2f6a9ad4e1e3592", "routine_expert_file": "1759668b353ef5b7",
        "tools": ["sql_console", "notebook", "spreadsheet", "bi_tool", "ticket_queue"],
        "risky": ["destructive_sql", "overwrite_table", "publish_dashboard", "send_extract", "schedule_job"],
        "defaults": {"tools": ["sql_console", "notebook"], "risky": ["destructive_sql", "overwrite_table", "publish_dashboard"], "tone": ["detailed"], "pace": ["gentle"]},
        "zones": ["data_browser", "profile_panel", "sql_editor", "run_control", "query_result", "chart_panel", "export_panel", "clean_panel", "control_panel", "pivot_panel",
                  "doc", "form_field", "search_box", "query_edit", "compare_view", "check_box", "decision_btn", "help"],
        "new_zones": {"lineage_view", "join_panel", "grain_picker", "magnitude_panel", "uncertainty_panel", "finding_editor", "review_request", "repro_panel",
                      "params_panel", "schedule_panel", "metric_docs"},
        "planted": ["weekly-metric-refresh"],
    },
}
NEW_COGS = {
    "programmer": ["REPRODUCE_LOCALLY", "BISECT_CHANGE", "WRITE_COMMIT_MSG", "OPEN_PR", "READ_CI", "ANSWER_REVIEW", "REVIEW_PEER", "WATCH_PROD", "ROLL_BACK",
                   "ADD_LOGGING", "PROFILE_HOTPATH", "WRITE_MIGRATION"],
    "data-analyst": ["TRACE_SOURCE", "JOIN_TABLES", "SET_GRAIN", "CHECK_MAGNITUDE", "QUANTIFY_UNCERTAINTY", "WRITE_FINDING", "PEER_CHECK", "MAKE_REPRODUCIBLE",
                     "PARAMETERISE_REPORT", "SCHEDULE_REFRESH", "DOCUMENT_METRIC"],
}
# the cog each new zone stands for (a click or focus in it), as the mapping must turn it
ZONE_COG = {
    "programmer": {"repro_console": "REPRODUCE_LOCALLY", "history_view": "BISECT_CHANGE", "commit_message": "WRITE_COMMIT_MSG", "pr_form": "OPEN_PR", "ci_checks": "READ_CI",
                   "review_thread": "ANSWER_REVIEW", "review_composer": "REVIEW_PEER", "prod_logs": "WATCH_PROD", "rollback_control": "ROLL_BACK",
                   "logging_panel": "ADD_LOGGING", "profiler_view": "PROFILE_HOTPATH", "migration_editor": "WRITE_MIGRATION"},
    "data-analyst": {"lineage_view": "TRACE_SOURCE", "join_panel": "JOIN_TABLES", "grain_picker": "SET_GRAIN", "magnitude_panel": "CHECK_MAGNITUDE",
                     "uncertainty_panel": "QUANTIFY_UNCERTAINTY", "finding_editor": "WRITE_FINDING", "review_request": "PEER_CHECK", "repro_panel": "MAKE_REPRODUCIBLE",
                     "params_panel": "PARAMETERISE_REPORT", "schedule_panel": "SCHEDULE_REFRESH", "metric_docs": "DOCUMENT_METRIC"},
}


def h(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True).encode()).hexdigest()[:16]


def docs(role: str) -> dict:
    d = packs_dir() / role
    pack = yaml.safe_load((d / "pack.yaml").read_text())
    out = {"pack": pack, "dir": d}
    for key, rel in (("steps", pack["expert_policy"]["steps"]), ("curriculum", pack["curriculum"]), ("routines", pack["routines"]), ("mapping", pack["cogs"]["mapping"]),
                     ("habits", pack["habits"]), ("priors", pack["priors"])):
        out[key] = yaml.safe_load((d / rel).read_text())
    return out


@pytest.fixture(scope="module", params=ROLES)
def role(request) -> str:
    return request.param


# ------------------------------------------------------------------------------------------------ nothing frozen moved
def test_the_frozen_part_of_the_pack_is_byte_identical_in_meaning(role):
    f, d = FROZEN[role], docs(role)
    n = f["n"]
    assert d["pack"]["cogs"]["extra"][: n["cogs"]] == NEW_COGS_ORIGINAL[role]
    assert h(d["steps"]["checks"][: n["checks"]]) == f["checks"]
    assert h(d["curriculum"]["skills"][: n["skills"]]) == f["skills"]
    assert h(d["routines"]["templates"][: n["templates"]]) == f["templates"]
    old_rules = [r for r in d["mapping"]["rules"] if not (set([r["match"].get("zone")] if isinstance(r["match"].get("zone"), str) else r["match"].get("zone") or []) & f["new_zones"])]
    assert h(old_rules) == f["rules"]
    assert h(d["mapping"]["params"]) == f["params"]
    assert h([s for s in d["mapping"]["capture_sites"] if s["id"] == "roles_sandbox"]) == f["sandbox_site"]
    for name, key in (("persona.yaml", "persona_file"), ("routine_expert.yaml", "routine_expert_file")):
        assert hashlib.sha256((d["dir"] / name).read_bytes()).hexdigest()[:16] == f[key], f"{name} is a generator or calendar input and must not change"


NEW_COGS_ORIGINAL = {
    "programmer": ["READ_CODE", "EDIT_CODE", "RUN_TESTS", "READ_TRACE", "REVIEW_DIFF", "COMMIT", "SEARCH_DOCS", "PROBE_EDGE", "INSPECT_INPUT", "WRITE_TEST"],
    "data-analyst": ["LOAD_DATA", "PROFILE_DATA", "WRITE_QUERY", "RUN_QUERY", "INSPECT_RESULT", "PLOT", "EXPORT_RESULT", "CLEAN_DATA", "RECONCILE_CONTROL", "GROUP_AGG"],
}


def test_the_frozen_zones_tools_and_defaults_are_still_there(role):
    f, d = FROZEN[role], docs(role)
    zones = d["mapping"]["zones"]
    assert [z for z in zones if z in f["zones"]] == f["zones"]                         # same zones, same order
    assert set(zones) == set(f["zones"]) | f["new_zones"]
    qs = {q["id"]: q for q in d["pack"]["onboarding"]["questions"]}
    assert [o["value"] for o in qs["tools"]["options"]][: len(f["tools"])] == f["tools"]
    assert [o["value"] for o in qs["risky"]["options"]][: len(f["risky"])] == f["risky"]
    for qid, defaults in f["defaults"].items():
        got = [o["value"] for o in qs[qid]["options"] if o.get("default")]
        assert got[: len(defaults)] == defaults or set(defaults) <= set(got), (qid, got)     # a default may be ADDED, never dropped
    persona = yaml.safe_load((d["dir"] / d["pack"]["persona"]).read_text())
    assert [r["id"] for r in persona["planted_routines"]] == f["planted"]


def test_new_cogs_are_appended_in_order_and_every_one_is_produced_by_a_rule(role):
    d = docs(role)
    extra = d["pack"]["cogs"]["extra"]
    assert extra == NEW_COGS_ORIGINAL[role] + NEW_COGS[role] and d["mapping"]["extra_cogs"] == extra
    assert 18 <= len(extra) <= 22
    produced = {r["cog"] for r in d["mapping"]["rules"]}
    assert set(NEW_COGS[role]) <= produced


# ------------------------------------------------------------------------------------------------ the mapping turns each new zone into its cog
def test_the_engine_mapping_turns_each_new_zone_into_its_cog(role):
    mp = load_pack(role).cog_mapping()
    for zone, cog in ZONE_COG[role].items():
        ev = Event.model_validate({"schema": 1, "id": "e1", "t": "2026-11-07T10:00:00Z", "origin": "real", "actor": "human", "person": "p_x1", "role": role,
                                   "source": "browser", "type": "click", "meta": {"zone": zone}})
        assert [c.id for c in to_cogs([ev], mp)] == [cog], (zone, cog)


def test_every_new_cog_has_a_mapping_test_vector_and_a_capture_element_or_a_documented_gap(role):
    d = docs(role)
    in_examples = {c for ex in d["mapping"]["examples"] for c in ex["expect"] if c}
    assert set(NEW_COGS[role]) <= in_examples
    captured = {e["zone"] for s in d["mapping"]["capture_sites"] for e in s["elements"]} | {r["zone"] for s in d["mapping"]["capture_sites"] for r in s.get("nav", [])}
    gaps = set(ZONE_COG[role]) - captured
    # a zone no capture config can emit is only reachable through an element that carries data-understudy-zone: say so in the docs
    assert gaps <= {"logging_panel"}, gaps          # the one zone that no real tool exposes as a distinct control: documented as a limit
    doc = (REPO / "docs" / "roles" / f"{role}.md").read_text()
    for z in gaps:
        assert z in doc, f"zone {z} has no capture element and is not mentioned in docs/roles/{role}.md"


# ------------------------------------------------------------------------------------------------ the new checks cannot touch a frozen task
def sandbox_zones(role: str) -> set[str]:
    base = REPO / "services" / "agent" / "understudy_agent" / "sandbox_roles" / ("programmer" if role == "programmer" else "analyst") / "static"
    src = "".join(p.read_text() for p in base.glob("*") if p.suffix in (".js", ".html"))
    return set(re.findall(r'data-understudy-zone="([a-z_]+)"', src)) | set(re.findall(r"zone: '([a-z_]+)'", src))


def test_no_sandbox_page_emits_a_new_zone(role):
    assert not sandbox_zones(role) & FROZEN[role]["new_zones"]


def expert_runs(role: str) -> list[dict]:
    return [json.loads(p.read_text()) for p in sorted((REPO / "evals" / "study_roles" / "experts" / role).glob("run_*.json"))]


def test_the_scripted_expert_recordings_still_map_to_the_cogs_they_were_recorded_with(role):
    runs = expert_runs(role)
    if not runs:
        pytest.skip("no expert recordings in this checkout")
    mp = load_pack(role).cog_mapping()
    for run in runs:
        evs = [Event.model_validate(e) for e in run["events"]]
        assert [c.id for c in to_cogs(evs, mp)] == [c["cog"] for c in run["cogs"]], run["task"]
        zones = {(e.meta or {}).get("zone") for e in evs}
        assert not zones & FROZEN[role]["new_zones"]


def family_ids(d: dict) -> set[str]:
    return {c["id"] for c in d["steps"]["checks"] if "family" in c}


def test_new_checks_are_never_started_scored_or_violated_by_a_frozen_task(role):
    """Every recorded expert run, tracked with the whole policy and with the frozen checks alone, gives the same answer for everything the frozen
    checks can see: done, occurrences, violations, the step in progress, and the outcomes the end-of-task skill tracing scores."""
    runs = expert_runs(role)
    if not runs:
        pytest.skip("no expert recordings in this checkout")
    d = docs(role)
    whole = StepPolicy.from_pack(load_pack(role))
    frozen_doc = {**d["steps"], "checks": [c for c in d["steps"]["checks"] if "family" not in c]}
    frozen = StepPolicy.from_doc(frozen_doc)
    new_ids = family_ids(d)
    assert new_ids and set(whole.steps) == set(frozen.steps) | new_ids
    mp = load_pack(role).cog_mapping()
    for run in runs:
        cogs = to_cogs([Event.model_validate(e) for e in run["events"]], mp)
        a, b = whole.track(cogs), frozen.track(cogs)
        assert a.done == b.done and not (set(a.occurrences) & new_ids), run["task"]
        assert {k: (o.start, o.end, o.complete) for k, o in a.occurrences.items()} == {k: (o.start, o.end, o.complete) for k, o in b.occurrences.items()}
        assert [(v.step, v.missing) for v in a.violations] == [(v.step, v.missing) for v in b.violations]
        assert a.current == b.current
        assert {k: v for k, v in whole.episode_outcomes(a).items()} == frozen.episode_outcomes(b)
        assert not set(whole.episode_outcomes(a)) & new_ids                          # no new check is scored at the end of a task


def test_new_checks_are_optional_and_start_with_a_cog_no_frozen_check_uses(role):
    d = docs(role)
    base_cogs = {g for c in d["steps"]["checks"] if "family" not in c for g in c["cogs"]}
    for c in d["steps"]["checks"]:
        if "family" in c:
            assert c["required"] is False and c["cogs"][0] not in base_cogs and c["cogs"][0] in NEW_COGS[role], c["id"]
    assert len({c["family"] for c in d["steps"]["checks"] if "family" in c}) >= 4


def test_every_new_cog_is_checked_taught_and_named_by_a_habit(role):
    d = docs(role)
    checked = {g for c in d["steps"]["checks"] for g in c["cogs"]}
    taught = {g for s in d["curriculum"]["skills"] for g in s["cogs"]}
    habit_cogs = {g for h_ in d["habits"]["habits"] for g in h_["cogs"]}
    for cog in NEW_COGS[role]:
        assert cog in checked and cog in taught and cog in habit_cogs, cog
    skills = {s["id"] for s in d["curriculum"]["skills"]}
    taught_by_a_check = {c["skill"] for c in d["steps"]["checks"] if "skill" in c}
    new_skills = [s for s in d["curriculum"]["skills"] if "name" in s]
    assert len(new_skills) >= len(NEW_COGS[role]) - 1
    for s in new_skills:
        assert s["id"] in taught_by_a_check, f"skill {s['id']} is taught by no expert check"
        assert any(h_["skill"] == s["id"] for h_ in d["habits"]["habits"]), f"skill {s['id']} has no habit definition"
    assert {h_["skill"] for h_ in d["habits"]["habits"]} <= skills


# ------------------------------------------------------------------------------------------------ the coach's critical gates
def test_a_critical_gate_is_spoken_for_only_when_a_later_check_is_started_without_it():
    cases = {
        "programmer": (["READ_TRACE", "BISECT_CHANGE"], "reproduce_locally"),
        "data-analyst": (["PROFILE_DATA", "WRITE_FINDING"], "trace_source"),
    }
    for role, (cog_ids, expect) in cases.items():
        pol = StepPolicy.from_pack(load_pack(role))
        t = 0.0
        from understudy_engine.core import Cog

        cogs = []
        for cid in cog_ids:
            cogs.append(Cog(id=cid, t0=t, t1=t + 10))
            t += 20
        prog = pol.track(cogs)
        assert prog.unresolved(), role
        v = prog.unresolved()[-1]
        assert pol.pick_missed(v.missing, prog) == expect, (role, v)


def test_nothing_is_said_about_a_new_step_when_no_new_cog_occurs(role):
    pol = StepPolicy.from_pack(load_pack(role))
    first = next(iter(pol.steps.values()))
    from understudy_engine.core import Cog

    prog = pol.track([Cog(id=first.cogs[0], t0=0.0, t1=5.0)])
    assert all(v.step not in family_ids(docs(role)) for v in prog.violations)


# ------------------------------------------------------------------------------------------------ content that must be complete
def test_every_new_skill_has_three_hints_in_a_question_or_command_form_and_a_name(role):
    d = docs(role)
    for s in d["curriculum"]["skills"]:
        if "name" not in s:
            continue
        p = s["prompts"]
        assert set(p) == {"L1", "L2", "L3"} and len(p["L1"]) <= 200 and len(p["L2"]) <= 140 and len(p["L3"]) <= 80
        assert p["L1"].rstrip().endswith("?"), s["id"]                                  # L1 is a question, never the answer (COA-4)
        assert not any(w in p["L1"].lower() for w in ("you should", "you must", "always ", "never ")), s["id"]


def test_every_routine_template_is_complete_and_consistent(role):
    d = docs(role)
    tpl = d["routines"]["templates"]
    new = [t for t in tpl if "steps" in t]
    assert len(new) >= 8
    judgement = set(d["routines"]["defaults"]["judgement_cogs"])
    classes = {t["irreversibility"] for t in new}
    assert {"none", "outward"} <= classes and len(classes) >= 3
    assert any(not t["automatable"] for t in new) and any(t["automatable"] for t in new)
    for t in new:
        assert t["tools"] is not None and all(re.fullmatch(r"[a-z][a-z0-9_-]{1,40}", x) for x in t["tools"])
        share = sum(1 for c in t["cogs"] if c in judgement) / len(t["cogs"])
        assert abs(share - t["judgement_share"]) < 0.011, t["id"]
        if t["irreversibility"] == "irreversible":
            assert not t["automatable"]
        assert 2 <= len(t["steps"]) <= 8 and len(t["proposal"]["what"]) <= 240
    assert {"github", "slack", "postgres", "sheets"} & {x for t in new for x in t["tools"]}


def test_every_template_is_long_enough_for_the_routine_finder_to_ever_report_it(role):
    """The finder never reports a skeleton shorter than its min_len (repeats merged, IDLE, REVERT and REFORMULATE left out): a shorter template would be
    dead data. The validator's copy of those numbers is kept equal to the finder's here."""
    import importlib.util

    from understudy_engine.routines.finder import DROP_COGS, FinderConfig

    spec = importlib.util.spec_from_file_location("pack_validate_for_rd", REPO / "packages" / "packs" / "validate.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.FINDER_MIN_LEN == FinderConfig().min_len and mod.FINDER_DROP == DROP_COGS
    for t in docs(role)["routines"]["templates"]:
        kept = [c for c in t["cogs"] if c not in DROP_COGS]
        merged = [c for i, c in enumerate(kept) if i == 0 or c != kept[i - 1]]
        assert len(merged) >= FinderConfig().min_len, t["id"]


def test_every_cog_of_the_pack_is_used_somewhere(role):
    d = docs(role)
    used = {g for c in d["steps"]["checks"] for g in c["cogs"]} | {g for s in d["curriculum"]["skills"] for g in s["cogs"]} | {g for t in d["routines"]["templates"] for g in t["cogs"]}
    assert set(d["pack"]["cogs"]["extra"]) <= used


def test_priors_carry_a_dwell_for_every_new_cog_and_it_matches_the_expert_median(role):
    d = docs(role)
    dwell = d["priors"]["cog_dwell_s"]
    medians = {c["cogs"][0]: c["expert_median_s"] for c in d["steps"]["checks"] if "family" in c}
    for cog in NEW_COGS[role]:
        assert dwell[cog] == medians[cog], cog


def test_every_new_check_carries_a_coach_target_in_the_zone_of_its_cog_and_cue_reads_it(role):
    from understudy_engine.cue import vocab as CV

    d = docs(role)
    zone_of_cog = {cog: zone for zone, cog in ZONE_COG[role].items()}
    v = CV.get_vocab(role)
    for c in d["steps"]["checks"]:
        if "family" not in c:
            continue
        t = c["coach"]["target"]
        assert t["zone"] == zone_of_cog[c["cogs"][0]], c["id"]
        assert 0 < len(t["label_hint"]) <= 80 and t["role_hint"] in {"button", "textbox", "region", "combobox"}
        assert v.target(c["id"]) == {"zone": t["zone"], "label_hint": t["label_hint"], "role_hint": t["role_hint"]}, c["id"]


# ------------------------------------------------------------------------------------------------ the pitch docs say what the pack has
WORDS = {4: "four", 6: "six", 10: "ten", 11: "eleven", 12: "twelve", 13: "thirteen", 16: "sixteen", 18: "eighteen", 21: "twenty-one", 22: "twenty-two"}


def test_the_role_docs_state_the_counts_the_pack_has(role):
    d = docs(role)
    text = (REPO / "docs" / "roles" / f"{role}.md").read_text().lower()
    n_cogs, n_new = len(d["pack"]["cogs"]["extra"]), len(NEW_COGS[role])
    assert f"{WORDS[n_cogs]} for this role: ten from the first release, {WORDS[n_new]} added" in text
    assert f"{WORDS[len(d['curriculum']['skills'])]} skills" in text
    assert f"{WORDS[n_new]} checks are new" in text
    assert f"{WORDS[len(d['routines']['templates'])]} routine templates" in text
    gates = sum(1 for c in d["steps"]["checks"] if c.get("critical") and "family" in c)
    assert f"{WORDS[gates]} are **critical gates**" in text
