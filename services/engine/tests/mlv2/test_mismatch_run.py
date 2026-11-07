import json

import numpy as np
import pytest

from understudy_engine.mlv2 import freeze, mismatch as MM, run as RUN, splits
from understudy_engine.mlv2.splits import HeldOutLocked


class _StubCohort:
    """Stands in for personas_v2.generate_cohort: episodes from the hazard simulator, a different seed and mix per family."""

    def __init__(self, family, role, n_people, cases, seed):
        from understudy_engine.hazard.sim import simulate_people

        fi = MM.FAMILIES.index(family)
        self.eps, _ = simulate_people(8, 20, seed=seed + 100 * fi, p_stuck=(0.03 + 0.03 * fi, 0.12 + 0.03 * fi))
        self.truth = {"realism": {"params_sha256": "stub", "generator_sha256": "stub-gen"}}

    def episodes(self):
        return self.eps


def _stub(family, role, n_people, cases, seed):
    return _StubCohort(family, role, n_people, cases, seed)


def test_seeds_follow_the_registered_scheme():
    assert MM.seed_for("MIS-DEV", "markov", "train") == 7100 and MM.seed_for("MIS-DEV", "markov", "test") == 7101
    assert MM.seed_for("MIS-HELD", "process_trace", "test") == 8100 + 20 + 1
    assert MM.seed_for("MIS-RESERVE", "latent_skill", "train") == 9110


def test_held_out_mismatch_pools_are_locked(monkeypatch):
    monkeypatch.delenv("UNDERSTUDY_MLV2_HELDOUT", raising=False)
    with pytest.raises(HeldOutLocked):
        MM.load_bundles("MIS-HELD", "benefits-processor", cohort_fn=_stub)


def test_mismatch_part_runs_on_a_stub_generator_and_reports_the_registered_structure(tmp_path, monkeypatch):
    monkeypatch.setenv("UNDERSTUDY_MLV2_CACHE", str(tmp_path))
    from understudy_engine.mlv2.models import A7_CANDIDATES, FAMILY_A

    variants = {k: FAMILY_A[k] for k in ("A0", "A1", "A3", "A6")} | {"A7": A7_CANDIDATES["A7_A1"]}
    out = MM.run_mismatch_part("MIS-DEV", roles=("benefits-processor",), n_boot=120, fast=True, cohort_fn=_stub, inner_folds=3, variants=variants)
    role = out["roles"]["benefits-processor"]
    assert set(role["cells"]) == {f"{x}->{y}" for x in MM.FAMILIES for y in MM.FAMILIES}
    assert sum(1 for c in role["cells"].values() if c["kind"] == "mismatch") == 6
    pooled = role["pooled_off_diagonal"]
    assert pooled["n_cells"] == 6 and "A0" in pooled["rows"] and pooled["rows"]["A0"]["paired_vs_ref"]["log_loss"]["delta"] == 0.0
    for vid in ("A1", "A3", "A6", "A7"):
        r = pooled["rows"][vid]
        assert set(r["guards"]) == {"brier", "ece", "auc", "detection"} and isinstance(r["mismatch_pass"], bool)
        assert r["mean_diagonal_log_loss_delta"] is not None and r["transfer_loss"] is not None
    assert set(pooled["family_c"]) == {"C1", "C2"}
    assert "stub-gen" in out["generator_sha256"] and "not to real work" in out["note"]


def test_heldout_command_refuses_without_token_frozen_file_and_second_run(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("UNDERSTUDY_EVALS_DIR", str(tmp_path))
    monkeypatch.delenv("UNDERSTUDY_MLV2_HELDOUT", raising=False)
    assert RUN.main(["heldout", "--part", "hazard"]) == 3                       # no token
    monkeypatch.setenv("UNDERSTUDY_MLV2_HELDOUT", "1")
    assert RUN.main(["heldout", "--part", "hazard"]) == 3                       # no frozen.json
    freeze.write_json(freeze.frozen_path(), {"a7_base": "A7_A4", "primary_a": "A7"})
    freeze.append_log({"event": "start", "part": "hazard", "t": freeze.now()})
    assert RUN.main(["heldout", "--part", "hazard"]) == 3                       # already started: refused
    assert RUN.main(["heldout", "--part", "nonsense"]) == 2
    lines = freeze.log_lines()
    assert [x["event"] for x in lines] == ["start"]                              # a refused run writes nothing


def test_code_hashes_are_per_part_and_stable(monkeypatch):
    h1 = freeze.code_hashes("hazard")
    h2 = freeze.code_hashes("hazard")
    assert h1 == h2 and "hazard_part.py" in h1 and "mismatch.py" not in h1
    assert "mismatch.py" in freeze.code_hashes("mismatch")
    assert freeze.code_fingerprint(h1) == freeze.code_fingerprint(h2)


def test_each_heldout_part_asks_its_own_registered_pool(tmp_path, monkeypatch):
    """Regression for a bug found on the first genome invocation: the CLI passed the hazard pool name ('HELD') to every part."""
    import understudy_engine.mlv2.genome_part as GP
    import understudy_engine.mlv2.hazard_part as HP
    import understudy_engine.mlv2.mismatch as MMOD
    from understudy_engine.mlv2 import apprentice_pool as AP

    monkeypatch.setenv("UNDERSTUDY_EVALS_DIR", str(tmp_path))
    monkeypatch.setenv("UNDERSTUDY_MLV2_HELDOUT", "1")
    freeze.write_json(freeze.frozen_path(), {"a7_base": "A7_A4", "primary_a": "A7", "hazard_frozen": True, "primary_e": "E4", "primary_q": "Q1"})
    seen = {}
    for part, mod, fn in (("hazard", HP, "run_hazard_part"), ("genome", GP, "run_genome_part"), ("mismatch", MMOD, "run_mismatch_part")):
        monkeypatch.setattr(mod, fn, lambda pool, _p=part, **kw: (seen.__setitem__(_p, pool), {"seconds": 0})[1])
        assert RUN.main(["heldout", "--part", part]) == 0
    assert seen == {"hazard": "HELD", "genome": "APP-HELD", "mismatch": "MIS-HELD"}
    assert seen["genome"] in AP.POOLS and seen["mismatch"] in MM.POOLS and seen["hazard"] in splits.POOL_NAMES
