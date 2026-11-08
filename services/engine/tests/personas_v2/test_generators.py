"""Generator tests (no analytic is run here): determinism, schema, privacy rules, structure, speed, round trip through the cog mapper."""
from __future__ import annotations

import json
import re
import time
from functools import lru_cache

import pytest

from understudy_engine.personas_v2 import FAMILY_ORDER, ROLES, generate_cohort
from understudy_engine.personas_v2.cohort import rows_to_events
from understudy_engine.personas_v2.workweeks import generate_workweeks
from understudy_engine.store.paths import repo_root
from understudy_engine.store.validate import validate_row

ROLE_IDS = tuple(ROLES)
ALLOWED_META = {"zone", "depth_bin", "len", "idle_s", "kind", "site"}


@lru_cache(maxsize=None)
def coh(family: str, role: str, n: int = 8, cases: int = 3, seed: int = 5, noise: bool = True):
    return generate_cohort(family, role, n_people=n, cases_per_person=cases, seed=seed, noise=noise)


@lru_cache(maxsize=None)
def ww(family: str, role: str, n: int = 4, days: int = 7, seed: int = 5):
    return generate_workweeks(family, role, n_people=n, n_days=days, seed=seed)


# ------------------------------------------------------------------------------------------ determinism
@pytest.mark.parametrize("family", FAMILY_ORDER)
def test_cohort_is_deterministic(family):
    a = generate_cohort(family, "benefits-processor", n_people=6, cases_per_person=3, seed=21)
    b = generate_cohort(family, "benefits-processor", n_people=6, cases_per_person=3, seed=21)
    assert json.dumps(a.rows, sort_keys=True) == json.dumps(b.rows, sort_keys=True)
    assert json.dumps(a.truth, sort_keys=True) == json.dumps(b.truth, sort_keys=True)
    c = generate_cohort(family, "benefits-processor", n_people=6, cases_per_person=3, seed=22)
    assert json.dumps(a.rows, sort_keys=True) != json.dumps(c.rows, sort_keys=True)


@pytest.mark.parametrize("family", FAMILY_ORDER)
def test_workweeks_is_deterministic(family):
    a = generate_workweeks(family, "programmer", n_people=3, n_days=5, seed=9)
    b = generate_workweeks(family, "programmer", n_people=3, n_days=5, seed=9)
    assert json.dumps(a.rows, sort_keys=True) == json.dumps(b.rows, sort_keys=True)
    assert a.labels == b.labels


def test_families_are_independent_for_the_same_seed():
    a = coh("markov", "benefits-processor")
    b = coh("process_trace", "benefits-processor")
    assert a.hyper != b.hyper
    assert {p.id for p in a.people}.isdisjoint({p.id for p in b.people})


# ------------------------------------------------------------------------------------------ schema and privacy
def _check_rows(rows):
    ids = set()
    last = ""
    for r in rows:
        validate_row(r)                                    # event.schema.json plus the pydantic model
        assert r["origin"] == "synthetic" and r["actor"] == "human"
        assert r["id"] not in ids
        ids.add(r["id"])
        assert r["t"] >= last                              # sorted
        last = r["t"]
        assert set(r.get("meta", {})) <= ALLOWED_META
        for v in r.get("meta", {}).values():
            assert isinstance(v, (int, float, bool)) or re.fullmatch(r"[a-z0-9_:\-.]{0,32}", v)
        tg = r.get("target", {})
        if "label_hash" in tg:
            assert re.fullmatch(r"h:[0-9a-f]{12}", tg["label_hash"])
        if "domain_hash" in tg:
            assert re.fullmatch(r"d:[0-9a-f]{12}", tg["domain_hash"])


@pytest.mark.parametrize("role", ROLE_IDS)
@pytest.mark.parametrize("family", FAMILY_ORDER)
def test_cohort_rows_are_schema_valid_and_private(family, role):
    c = coh(family, role)
    _check_rows(c.rows)
    text = json.dumps(c.rows)
    assert "http" not in text and "://" not in text and "www." not in text
    pats = json.loads((repo_root() / "packages/schema/sensitive_fields.json").read_text())["patterns"]
    for pat in pats:
        assert not re.search(pat, text, re.I), pat


@pytest.mark.parametrize("family", FAMILY_ORDER)
def test_workweek_rows_are_schema_valid_and_private(family):
    w = ww(family, "benefits-processor")
    _check_rows(w.rows)
    assert "http" not in json.dumps(w.rows)


def test_truth_files_carry_the_synthetic_badge_and_no_free_text():
    c = coh("latent_skill", "benefits-processor")
    assert c.truth["origin"] == "synthetic"
    assert c.truth["realism"]["label"] == "generated, realism-calibrated"
    assert all(r["origin"] == "synthetic" for r in c.rows)
    w = ww("markov", "data-analyst")
    assert w.truth["realism"]["label"] == "generated, realism-calibrated"


# ------------------------------------------------------------------------------------------ structure
@pytest.mark.parametrize("family", FAMILY_ORDER)
def test_truth_has_the_v1_apprentice_shape(family):
    c = coh(family, "benefits-processor")
    t = c.truth
    for key in ("people", "traces", "deficit_types", "expert_reference", "stuck_episodes", "n_experts", "n_novices"):
        assert key in t
    assert set(t["deficit_types"]) == {"skipped_check_cliff", "repeated_read_result", "search_loop", "copy_error", "idle_before_enter"}
    assert set(p["level"] for p in t["people"]) == {"expert", "novice"}
    for tr in t["traces"]:
        for k in ("task_id", "person", "level", "case", "duration_s", "deficits", "cogs", "expert_median_s"):
            assert k in tr
        for d in tr["deficits"]:
            assert d["instances"] > 0
            assert abs(d["price_s"] - (d["added_s"] - d["saved_s"])) < 0.02
            assert d["material"] == (d["price_s"] >= 5.0)
    assert t["expert_reference"]["sequence_A"][0] == "READ"
    assert len({tr["task_id"] for tr in t["traces"]}) == len(t["traces"])


@pytest.mark.parametrize("role", ROLE_IDS)
def test_mapper_recovers_planted_cogs_without_noise(role):
    """With capture noise off the mapper recovers most of the planted cog sequence: the planted truth is real, not cosmetic."""
    from understudy_engine.cogs.mapper import to_cogs
    c = coh("process_trace", role, 6, 3, 31, False)
    eps = {e.task_id: e for e in c.episodes()}
    good = tot = 0
    for tr in c.truth["traces"]:
        planted = [x[0] for x in tr["cogs"] if x[0] not in ("IDLE",)]
        mapped = [g.id for g in eps[tr["task_id"]].cogs if g.id != "IDLE"]
        pset = set(planted)
        tot += len(set(mapped) | pset)
        good += len(set(mapped) & pset)
    assert good / tot > 0.6


@pytest.mark.parametrize("role", ROLE_IDS)
def test_every_mapped_cog_is_a_known_cog(role):
    from understudy_engine.core import BASE_COGS
    rs = ROLES[role]
    known = set(rs.cogs) | set(BASE_COGS)
    for fam in FAMILY_ORDER:
        for e in coh(fam, role).episodes():
            assert {g.id for g in e.cogs} <= known


def test_levels_are_a_noisy_function_of_tenure():
    c = generate_cohort("markov", "benefits-processor", n_people=60, cases_per_person=2, seed=3)
    ex = [p for p in c.people if p.level == "expert"]
    no = [p for p in c.people if p.level == "novice"]
    assert 0.25 < len(ex) / len(c.people) < 0.55
    # ability overlaps between the groups: the label is not the ability
    assert max(p.g for p in no) > min(p.g for p in ex)
    assert sum(p.g for p in ex) / len(ex) > sum(p.g for p in no) / len(no)


def test_deficit_severity_is_continuous_and_some_people_have_none():
    c = generate_cohort("process_trace", "benefits-processor", n_people=40, cases_per_person=6, seed=8)
    sev = [v for t in c.truth["traces"] for v in t["severity"].values()]
    assert len({round(v, 2) for v in sev}) > 40
    by_person = {}
    for t in c.truth["traces"]:
        by_person.setdefault(t["person"], 0)
        by_person[t["person"]] += sum(1 for d in t["deficits"] if d["material"])
    assert any(v == 0 for v in by_person.values())
    assert any(v > 0 for v in by_person.values())


def test_learning_and_interruptions_leave_a_mark():
    c = generate_cohort("latent_skill", "benefits-processor", n_people=30, cases_per_person=8, seed=14)
    nov = [t for t in c.truth["traces"] if t["level"] == "novice"]
    first = [t["duration_s"] for t in nov if t["case"] <= 2]
    last = [t["duration_s"] for t in nov if t["case"] >= 7]
    assert sorted(last)[len(last) // 2] < sorted(first)[len(first) // 2]
    assert sum(t["interruptions"] for t in c.truth["traces"]) > 0


def test_families_are_structurally_different():
    """Bigram distributions of the planted cog sequences differ between families by more than within a family across seeds."""
    from collections import Counter

    def big(c):
        cnt = Counter()
        for t in c.truth["traces"]:
            cg = [x[0] for x in t["cogs"]]
            cnt.update(zip(cg, cg[1:]))
        n = sum(cnt.values())
        return {k: v / n for k, v in cnt.items()}

    def tv(a, b):
        return 0.5 * sum(abs(a.get(k, 0) - b.get(k, 0)) for k in set(a) | set(b))

    ds = {f: big(generate_cohort(f, "benefits-processor", n_people=30, cases_per_person=4, seed=40)) for f in FAMILY_ORDER}
    ds2 = {f: big(generate_cohort(f, "benefits-processor", n_people=30, cases_per_person=4, seed=41)) for f in FAMILY_ORDER}
    across = min(tv(ds[a], ds[b]) for a in FAMILY_ORDER for b in FAMILY_ORDER if a < b)
    within = max(tv(ds[f], ds2[f]) for f in FAMILY_ORDER)
    assert across > 0.5 * within          # the families are at least as far apart as two draws of one family are from each other
    assert across > 0.08


def test_cohort_40_by_8_is_fast():
    t = time.time()
    c = generate_cohort("process_trace", "benefits-processor", n_people=40, cases_per_person=8, seed=1)
    assert time.time() - t < 30.0
    assert len(c.truth["traces"]) == 320


def test_round_trip_through_files(tmp_path):
    c = coh("markov", "programmer")
    out = c.write(tmp_path, "x")
    rows = [json.loads(l) for l in (out / "events.jsonl").read_text().splitlines()]
    assert len(rows) == len(c.rows)
    assert json.loads((out / "truth.json").read_text())["family"] == "markov"
    assert len(rows_to_events(rows)) == len(rows)


# ------------------------------------------------------------------------------------------ workweeks
@pytest.mark.parametrize("family", FAMILY_ORDER)
def test_workweeks_structure(family):
    w = generate_workweeks(family, "benefits-processor", n_people=6, n_days=14, seed=2)
    t = w.truth
    assert t["n_days"] == 14 and len(t["people"]) == 6
    assert any(d["windows"] == [] for p in t["people"] for d in p["daily"])               # days off exist
    assert any(r["n_instances"] >= 3 for p in t["people"] for r in p["routines"])         # routines recur
    assert any(r == "adhoc" for r in w.labels.values()) and any(r != "adhoc" for r in w.labels.values())
    types = {r["type"] for r in w.rows}
    assert {"lock", "unlock", "sleep", "resume", "idle", "progress", "task_start"} <= types
    assert all(w.labels.get(e.task_id) for e in w.episodes() if e.task_id in w.labels)


def test_no_schedule_change_is_planted():
    w = ww("markov", "benefits-processor", 6, 14)
    assert "change_day" not in w.truth


# ------------------------------------------------------------------------------------------ marginal checks run and are honest
def test_marginal_checks_report_ids_status_and_decoupled_label():
    from understudy_engine.personas_v2.marginals import cohort_checks, label_checks, structure_checks, summarise
    c = generate_cohort("process_trace", "benefits-processor", n_people=30, cases_per_person=6, seed=77)
    checks = cohort_checks(c) + structure_checks(c) + label_checks(c)
    ids = {x["id"] for x in checks}
    assert {"M1", "M3", "M4", "M6", "M7", "M9", "M13b", "M13d", "S1", "S4"} <= ids
    assert all(x["constant_status"] in {"secondary", "assumption", "qualitative"} for x in checks)
    by = {x["id"]: x for x in checks}
    assert 0.0 < by["M13b"]["value"] < 1.0 and 0.0 < by["M13d"]["value"] < 1.0           # the label is not the hidden state
    assert by["M2d"]["constant_status"] == "assumption"                                    # the unverified Hick slope is never called published
    s = summarise({"a": checks})
    assert s["M7"]["inside"] + s["M7"]["outside"] + s["M7"]["not_applicable"] == 1


def test_params_hash_and_table_are_stable_and_complete():
    from understudy_engine.personas_v2 import params
    assert len(params.params_sha256()) == 64
    table = params.render_table()
    assert table.count("\n") == len(params.PARAMS) + 1
    assert all(p.name in table for p in params.PARAMS)
    for p in params.PARAMS:
        assert p.lo <= p.hi
