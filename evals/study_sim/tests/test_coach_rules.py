"""The pure rules of the coach path: following, false prompts, study-mode violations, counts."""
from __future__ import annotations

from evals.study_sim.checks import contamination
from evals.study_sim.coach import (Mode, NudgeCounts, Shown, false_nudge, first_note_interaction, followed_by, skill_of_step, target_step,
                                   violation_of)
from evals.study_sim.observe import Executed


def ex(t, kind, dom="", site=None, path="/", ok=True):
    return Executed(t=t, kind=kind, ok=ok, dom_id=dom, site=site, path=path)


def test_skill_of_step_and_target():
    assert skill_of_step("cliff_a") == "cliff" and skill_of_step("cliff_b") == "cliff" and skill_of_step("reconcile") == "reconcile"
    assert skill_of_step("write_note") is None and skill_of_step(None) is None
    assert target_step({"missed": ["cliff_a", "cliff_b"]}) == "cliff_a"
    assert target_step({"missed": [], "candidate": {"step": "reconcile"}}) == "reconcile"
    assert target_step({"step": "cliff_b"}) == "cliff_b"


def test_followed_by():
    assert followed_by("cliff", ex(1, "click", "cliff-btn", "a"))
    assert not followed_by("cliff", ex(1, "click", "continue", "a"))
    assert not followed_by("cliff", ex(1, "click", "cliff-btn", "a", ok=False))
    assert followed_by("reconcile", ex(1, "select", "reconciliation"))
    assert followed_by("reconcile", ex(1, "select", "cn-recon"))
    assert followed_by("reconcile", ex(1, "switch_tab"))
    assert not followed_by("reconcile", ex(1, "click", "cliff-btn", "a"))
    assert not followed_by(None, ex(1, "click", "cliff-btn", "a"))


def test_false_nudge_cliff():
    done_a = [ex(10, "click", "cliff-btn", "a")]
    assert false_nudge("cliff", "cliff_a", [], 50) == ""
    assert false_nudge("cliff", "cliff_a", done_a, 50) == "false"                  # the first cliff was opened 40 s before the prompt
    assert false_nudge("cliff", "cliff_a", done_a, 13) == "lag"                    # 3 s before: the event pipeline lagging
    assert false_nudge("cliff", "cliff_b", done_a, 50) == ""                       # only one of two done: a prompt for the second is right
    both = done_a + [ex(20, "click", "cliff-btn", "b")]
    assert false_nudge("cliff", "cliff_b", both, 50) == "false"
    assert false_nudge("cliff", "cliff_a", [ex(10, "click", "cliff-btn", "a"), ex(11, "click", "cliff-btn", "a")], 50) == "false"
    assert false_nudge("cliff", "cliff_b", [ex(10, "click", "cliff-btn", "a"), ex(11, "click", "cliff-btn", "a")], 50) == ""   # same site twice is one check


def test_false_nudge_reconcile():
    assert false_nudge("reconcile", "reconcile", [], 50) == ""
    assert false_nudge("reconcile", "reconcile", [ex(5, "switch_tab")], 50) == "false"
    assert false_nudge("reconcile", "reconcile", [ex(48, "select", "reconciliation")], 50) == "lag"
    assert false_nudge("reconcile", "reconcile", [ex(60, "switch_tab")], 50) == ""   # done after the prompt arrived: not before it


def test_first_note_interaction():
    seq = [ex(1, "fill", path="/step/1"), ex(5, "goto", path="/casenote"), ex(9, "fill", path="/casenote")]
    assert first_note_interaction(seq) == 5
    assert first_note_interaction(seq[:1]) is None


def test_violation_of_study_mode():
    act = {"action": "annotate", "missed": ["cliff_a"]}
    silent = {"action": "silent"}
    assert violation_of(Mode("post_test"), silent) == "" and violation_of(Mode("off"), silent) == ""
    assert violation_of(Mode("post_test"), act) and violation_of(Mode("off"), act)
    assert violation_of(Mode("train", "cliff"), act) == ""
    assert violation_of(Mode("train", "reconcile"), act)                              # a cliff prompt while only reconcile is on
    assert violation_of(Mode("train", "cliff"), {"action": "nudge", "missed": ["reconcile"]})
    assert violation_of(Mode("train", "cliff"), {"action": "nudge", "missed": ["write_note"]})   # an unrelated step is also a violation


def test_nudge_counts():
    def sh(outcome, zone="cliff_button", skill="cliff", false="", ring=True, delay=8.0, action="annotate"):
        return Shown("d", action, "m", zone, "cliff_a", skill, [], "expert_policy", 0.0, 0.0, ring_found=ring, outcome=outcome, false=false, delay_s=delay)
    c = NudgeCounts.of([sh("followed"), sh("dismissed"), sh("ignored", ring=False), sh("ignored", false="false"), sh("followed", false="lag", zone="results_tabs", skill="reconcile")])
    assert (c.shown, c.followed, c.explicit_dismissed, c.ignored, c.dismissed) == (5, 2, 1, 2, 3)
    assert (c.false_nudges, c.lag_prompts, c.rings_drawn, c.banners_only) == (1, 1, 4, 1)
    assert ("cliff_button", "cliff_button") in c.zones and ("results_tabs", "results_tabs") in c.zones
    c2 = NudgeCounts.of([sh("followed", zone="reconcile_control", skill="reconcile"), sh("followed", zone="cliff_button", skill="reconcile")])
    assert ("reconcile_control", "reconcile_control") in c2.zones and ("cliff_button", None) in c2.zones      # the wrong zone for the skill is not "expected"


def test_contamination():
    own = [ex(1, "click", "calculate", "a"), ex(2, "click", "cliff-btn", "a"), ex(3, "click", "save-draft", "a")]
    clean = {"calculations": [{"site": "a"}], "cliff_opens": [{"site": "a"}], "notes": {"CN-1": {}}, "submissions": [], "exfil_hits": []}
    assert contamination(clean, own) == ""
    assert contamination({**clean, "cliff_opens": [{"site": "a"}, {"site": "b"}]}, own)          # more cliff panels than the participant opened
    assert contamination({**clean, "calculations": [{"site": "a"}, {"site": "c"}]}, own)
    assert contamination({**clean, "notes": {"CN-1": {}, "CN-2": {}}}, own)
    assert contamination({**clean, "submissions": [{"note_id": "x"}]}, own)
    assert contamination({**clean, "exfil_hits": [{"site": "a"}]}, own)
    assert contamination({"calculations": [{"site": "c"}], "cliff_opens": [], "notes": {}}, [ex(1, "click", "calculate", "a")])   # site c never visited
    assert contamination({"calculations": [], "cliff_opens": [], "notes": {}}, []) == ""


def test_contamination_detects_a_reset_during_the_case():
    from evals.study_sim.checks import contamination, counts_of
    own = [ex(1, "click", "calculate", "a"), ex(2, "click", "cliff-btn", "a"), ex(3, "click", "calculate", "b"), ex(4, "click", "cliff-btn", "b")]
    full = {"calculations": [{"site": "a"}, {"site": "b"}], "cliff_opens": [{"site": "a"}, {"site": "b"}], "notes": {}, "submissions": [], "exfil_hits": []}
    assert contamination(full, own, counts_of(full)) == ""
    wiped = {**full, "cliff_opens": [{"site": "b"}]}                                # site a's panel opened, then someone reset, then b's was logged
    assert "reset" in contamination(wiped, own)
    assert "shrank" in contamination({**full, "calculations": [{"site": "a"}], "cliff_opens": [{"site": "a"}]}, [ex(1, "click", "calculate", "a"), ex(2, "click", "cliff-btn", "a"), ex(3, "click", "calculate", "b")], counts_of(full))
    assert "no note" in contamination({**full}, own, None, saved=True)
    assert contamination({**full, "notes": {"CN-1": {}}}, own + [ex(5, "click", "save-draft", "a")], None, saved=True) == ""
