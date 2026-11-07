from understudy_engine.mlv2.decision import decide


def _h(verdicts):
    rows = {f"A{i}": {"verdict": v, "paired_vs_ref": {"log_loss": {"delta": -0.001 * i, "interval": [-0.002, -0.0001], "level": 0.99}}} for i, v in verdicts.items()}
    return {"family_a": {"rows": rows}, "family_c": {"on_A0": {"rows": {"C1": {"verdict": "null"}, "C2": {"verdict": "null"}}}}}


def _m(passing):
    def role(p):
        return {"pooled_off_diagonal": {"rows": {f"A{i}": {"mismatch_pass": f"A{i}" in p} for i in range(1, 8)},
                                         "family_c": {"C1": {"pooled_pass": True}, "C2": {"pooled_pass": True}}}}
    return {"roles": {r: role(p) for r, p in passing.items()}}


def test_both_conditions_are_needed_and_the_deep_role_decides():
    h = _h({1: "null", 2: "accepted", 3: "accepted", 4: "accepted", 5: "null", 6: "accepted", 7: "accepted"})
    m = _m({"benefits-processor": {"A1", "A3", "A4"}, "data-analyst": {"A1"}, "programmer": {"A3", "A4", "A7"}})
    d = decide(h, m)
    assert d["family_a"]["A7"]["replaces_v1_by_role"]["programmer"] is False        # a thin role cannot rescue a variant that fails the deep role
    assert d["family_a"]["A1"]["replaces_v1_by_role"]["benefits-processor"] is False  # null on the held-out persona replicates
    assert d["family_a"]["A4"]["replaces_v1_by_role"]["benefits-processor"] and d["family_a"]["A4"]["replaces_v1_by_role"]["programmer"]
    assert not d["family_a"]["A4"]["replaces_v1_by_role"]["data-analyst"]
    assert d["default_v2"]["benefits-processor"] == "A4"                              # the lowest held-out difference among the qualifying (A3, A4)
    assert d["default_v2"]["data-analyst"] is None and "data-analyst" in d["v1_stays_for"]
    assert d["family_c"]["C1"]["replaces_v1_rule_by_role"]["benefits-processor"] is False and d["family_c"]["C1"]["note"]


def test_incomplete_inputs_are_reported_not_guessed():
    assert decide(None, None)["status"].startswith("incomplete")
