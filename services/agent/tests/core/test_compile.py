"""HND-3: compile an L1 recording into a bundle, dry-run it, replay it on a new household."""
from __future__ import annotations

import json

import pytest

from understudy_agent.compile import (
    compile_and_check, compile_draft, load_bundles, save_bundle, validate_platform_bundle, validate_recording,
)
from understudy_agent.models.mock_provider import MockProvider
from understudy_agent.sandbox_sites.households import generate_households
from understudy_agent.sandbox_sites.oracle import site_expected
from understudy_agent.sandbox_sites.recordings import synthetic_recording
from understudy_agent.tiers.browser import BrowserHost
from understudy_agent.tiers.dsl import DslRuntime, run_bundle, to_internal, validate_bundle
from understudy_agent.tiers.heuristic import HeuristicModelPort
from understudy_agent.tiers.safety import Guard
from understudy_agent.queue import ApprovalQueue
from understudy_agent.audit import AuditLog
from understudy_agent.security.denylist import Denylist


@pytest.fixture
async def host():
    async with BrowserHost() as h:
        yield h


@pytest.fixture
def model():
    return HeuristicModelPort(MockProvider("benefits_clean"))


@pytest.fixture
def sinks(tmp_path):
    a = AuditLog(tmp_path / "audit.jsonl")
    return ApprovalQueue(tmp_path / "queue", audit=a), a


def hh(i):
    return generate_households(20)[i]


@pytest.mark.parametrize("site,layout", [("a", "v1"), ("b", "v1"), ("c", "v1"), ("a", "v2"), ("b", "v2"), ("c", "v2")])
async def test_recording_compiles_dry_runs_and_replays_on_a_new_household(cluster, host, model, sinks, site, layout):
    q, a = sinks
    rec = synthetic_recording(site, layout, base_urls=cluster.urls)
    assert validate_recording(rec) == [] and rec["skipped_sensitive"] == 1
    assert not any("limited" in (s.get("param") or "") or "health" in (s.get("param") or "") for s in rec["steps"])
    # compile + dry run on household 3
    bundle, rep = await compile_and_check(rec, model=model, host=host, household=hh(3), base_urls=cluster.urls,
                                          audit=a, queue=q)
    assert bundle is not None and rep.ok, rep.errors
    assert rep.site == site and rep.layout == layout and rep.dry_run["matches_expected"] is True
    assert rep.inserted_from_household == ["limited_capability"]  # never from the recording
    assert validate_platform_bundle(bundle) == [] and validate_bundle(bundle) == []
    assert bundle["params"]["limited_capability"]["source"] == "household.params.limited_capability"
    # replay on NEW households, including a limited-capability one where the answer depends on that field
    ctx = await host.new_context()
    for i in (10, 1, 6):  # hh_0011 is the carer with limited capability
        page = await ctx.new_page()
        guard = Guard(model, run_id="r_replay", mode="compiled", audit=a, queue=q, denylist=Denylist(),
                      recorded_hosts=frozenset({f"127.0.0.1:{cluster.ports[site]}"}))
        q_str = "?layout=v2" if layout == "v2" else ""
        rt = DslRuntime(page=page, params=hh(i).params(), base_url=cluster.urls[site], query=q_str, guard=guard,
                        navigator="replay")
        out = (await run_bundle(bundle, rt)).outputs
        from understudy_agent.completion import validate_result_fields

        f, problems = validate_result_fields(site, out)
        assert f and abs(f.amount - site_expected(site, hh(i))["uc_monthly"]) <= 0.06, (i, problems)
    # the LCW household really exercises the household-only field
    assert site_expected(site, hh(10))["uc_monthly"] != site_expected(site, hh(10).__class__.from_dict(
        {**hh(10).to_dict(), "limited_capability": False}))["uc_monthly"]


async def test_role_and_name_targets_and_param_transform_for_site_c(cluster, host, model, sinks):
    q, a = sinks
    rec = synthetic_recording("a", "v1", base_urls=cluster.urls, by_role=("adult1_age", "savings"))
    bundle, rep = await compile_and_check(rec, model=model, host=host, household=hh(1), base_urls=cluster.urls,
                                          audit=a, queue=q)
    assert rep.ok, rep.errors
    roled = [s for s in bundle["steps"] if "role" in s]
    assert len(roled) == 2 and all("selector" not in s for s in roled)
    recc = synthetic_recording("c", "v1", base_urls=cluster.urls)
    bc, repc = compile_draft(recc, base_urls=cluster.urls, model=model)
    assert repc.site == "c" and bc["params"]["adult1_earnings_monthly"]["transform"] == {"mul": 12.0, "round": 2}
    assert bc["params"]["rent_monthly"]["transform"]["round"] == 2


async def test_cliff_click_is_recorded_and_postcondition_waits_for_the_panel(cluster, model):
    rec = synthetic_recording("b", base_urls=cluster.urls, with_cliff=True)
    bundle, rep = compile_draft(rec, base_urls=cluster.urls, model=model)
    cliff = [s for s in bundle["steps"] if s.get("selector") == "#cliff-btn"][0]
    assert cliff["postcondition"] == {"selector_visible": "#cliff-panel"}


async def test_irreversible_click_is_marked_and_the_dry_run_stops_in_front_of_it(cluster, host, model, sinks):
    q, a = sinks
    rec = synthetic_recording("a", base_urls=cluster.urls, with_cliff=False)
    rec["steps"].append({"op": "click", "t_ms": 99999, "role": "button", "name": "Submit to claimant record"})
    bundle, rep = compile_draft(rec, base_urls=cluster.urls, model=model)
    sub = [s for s in bundle["steps"] if s.get("name") == "Submit to claimant record"][0]
    assert sub["irreversible"] is True
    # the dry run never presses it (and never submits anything)
    bundle2, rep2 = await compile_and_check(rec, model=model, host=host, household=hh(1), base_urls=cluster.urls,
                                            audit=a, queue=q)
    assert cluster.state.submissions == []
    assert rep2.dry_run["stopped_before"] == sub["id"]
    assert bundle2 is None  # the dry run never reached the result, so it is not accepted as a compiled routine


def test_validator_rejects_a_bad_recording_and_unknown_slots(cluster, model):
    rec = synthetic_recording("a", base_urls=cluster.urls)
    bad = json.loads(json.dumps(rec))
    bad["steps"][1]["selector"] = "javascript:alert(1)"
    bundle, rep = compile_draft(bad, base_urls=cluster.urls, model=model)
    assert bundle is None and rep.errors and "recording" in rep.errors[0]
    weird = json.loads(json.dumps(rec))
    weird["steps"][1]["param"] = "mystery_field"
    bundle, rep = compile_draft(weird, base_urls=cluster.urls, model=None)
    assert bundle is None and "cannot place field slot" in rep.errors[0]


def test_a_model_may_draft_the_slot_mapping_but_code_validates_it(cluster):
    rec = synthetic_recording("a", base_urls=cluster.urls)
    rec["steps"][1]["param"] = "mystery_field"
    mock = MockProvider("benefits_clean")
    mock.script_plan("param_mapping", {"mappings": [{"slot": "mystery_field", "canonical": "adults"}]})
    bundle, rep = compile_draft(rec, base_urls=cluster.urls, model=mock)
    assert bundle is not None and rep.model_drafted == ["mystery_field"]
    mock2 = MockProvider("benefits_clean")
    mock2.script_plan("param_mapping", {"mappings": [{"slot": "mystery_field", "canonical": "social_security_number"}]})
    bundle, rep = compile_draft(rec, base_urls=cluster.urls, model=mock2)
    assert bundle is None and "cannot place" in rep.errors[0]  # an invented parameter is refused


def test_save_and_load_bundles(cluster, model, tmp_path):
    rec = synthetic_recording("a", base_urls=cluster.urls)
    bundle, _ = compile_draft(rec, base_urls=cluster.urls, model=model)
    p = save_bundle(bundle, root=tmp_path)
    save_bundle(bundle, name="b", root=tmp_path)
    assert p == tmp_path / "routines" / "calc-entry-3x" / "steps.json"
    got = load_bundles("calc-entry-3x", tmp_path)
    assert set(got) == {"primary", "b"} and got["primary"]["id"] == "calc-entry-3x"


async def test_the_platforms_example_bundles_run_on_the_sandbox(cluster, host, model, sinks):
    """Cross-track check: packages/schema/examples/steps.calc_entry*.json execute with our interpreter."""
    from understudy_agent.supervisor import repo_root

    q, a = sinks
    ex = repo_root() / "packages" / "schema" / "examples"
    for name, site, start in (("steps.calc_entry.example.json", "a", "a"), ("steps.calc_entry_c.example.json", "c", "c")):
        p = ex / name
        if not p.exists():
            pytest.skip(f"{name} not published yet")
        bundle = json.loads(p.read_text())
        assert validate_platform_bundle(bundle) == [], name
        page = await (await host.new_context()).new_page()
        params = hh(1).params()
        for k, v in bundle["params"].items():
            if k.startswith("site_") and k.endswith("_start"):
                params[k] = cluster.urls[start] + ("/step/1" if site == "a" else "/")
        guard = Guard(model, run_id="r_x", mode="compiled", audit=a, queue=q, denylist=Denylist(),
                      recorded_hosts=frozenset({f"127.0.0.1:{cluster.ports[site]}"}))
        res = await run_bundle(bundle, DslRuntime(page=page, params=params, base_url="", guard=guard, navigator="ex",
                                                   stop_before_irreversible=True))
        assert res.steps_run >= 15


def test_demo_bundle_installs_idempotently_with_private_sites_and_targets_the_real_ports(cluster, tmp_path):
    from understudy_agent import demo_bundle
    from understudy_agent.compile import bundles_by_site, validate_platform_bundle
    from understudy_agent.sandbox_sites import lock as sandbox_lock_mod

    root = tmp_path / "demo-data"
    # another agent holds the shared sandbox lock: seeding must neither wait for it nor touch the shared sites
    with sandbox_lock_mod.sandbox_lock("someone-else"):
        first = demo_bundle.install_report(data_dir=root, log=lambda *_: None)
    assert first["actions"] == {"a": "written", "b": "written", "c": "written"}
    names = sorted(p.name for p in first["paths"])
    assert names == ["steps.b.json", "steps.c.json", "steps.json"]
    got = bundles_by_site("calc-entry-3x", root)
    assert sorted(got) == ["a", "b", "c"] and all(validate_platform_bundle(b) == [] for b in got.values())
    assert all(r["dry_run"]["matches_expected"] for r in first["reports"].values())
    gotos = {s: [st["url"] for st in b["steps"] if st["op"] == "goto"][0] for s, b in got.items()}
    from understudy_agent.sandbox_sites.specs import site_base_urls

    target = site_base_urls()                 # 7801-7803 in production; the test environment points them at port 9
    assert gotos == {"a": target["a"] + "/step/1", "b": target["b"] + "/", "c": target["c"] + "/"}
    assert not any(str(port) in u for u in gotos.values() for port in cluster.ports.values())  # not the private dry-run ports
    assert cluster.state.calculations == []        # the session's sandbox (another agent's, as far as this test knows) untouched
    second = demo_bundle.install_report(data_dir=root, log=lambda *_: None)
    assert second["actions"] == {"a": "unchanged", "b": "unchanged", "c": "unchanged"}
    assert demo_bundle.status(data_dir=root)["bundles"] == {"a": True, "b": True, "c": True}
