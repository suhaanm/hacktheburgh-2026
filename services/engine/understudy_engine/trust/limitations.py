"""The analytics limitations register (EVL-4): what the numbers from these modules do NOT show.

Each entry is {id, text, severity} as the `limitations` section of /eval/report expects. Written to be read
by a worker or a judge, in plain words. `analytics_limitations()` is the single list the eval harness can merge.
"""
from __future__ import annotations


def analytics_limitations() -> list[dict]:
    return [
        {"id": "ana-synthetic-origin", "severity": "high",
         "text": "Hazard, skills, policy, routing and agent-claim results come from synthetic personas, scripted apprentices "
                 "or simulators we wrote. They show that the methods recover structure we planted, not that real workers behave this way."},
        {"id": "ana-hazard-people", "severity": "high",
         "text": "The stuck hazard is evaluated on four synthetic personas, so 'held-out person' means one of four. Intervals resample "
                 "episodes, not people; the per-person spread is the honest uncertainty."},
        {"id": "ana-hazard-alerts", "severity": "medium",
         "text": "Probabilities are better than the baselines and calibrated, but alert quality is modest: about a third of stuck events "
                 "are flagged, and on held-out people the false-alarm rate (about 1.2 per hour) overshoots the 1 per hour budget "
                 "chosen on training people."},
        {"id": "ana-hazard-label", "severity": "medium",
         "text": "'Stuck' means no progress event in the next 60 seconds, which is not the same as confusion. Fast thinking and slow "
                 "typing both look stuck to this label."},
        {"id": "ana-apprentice-script", "severity": "medium",
         "text": "The apprentice traces follow a fixed task script, so part of the hazard model's large gain on them is learning the script, "
                 "not predicting stuck. The four-persona result is the headline."},
        {"id": "ana-skills-saturate", "severity": "medium",
         "text": "Skill tracing saturates on synthetic personas (about 35 tasks a day): mastery reaches its ceiling on day one and cannot "
                 "follow the planted learning curve. Decay with absence is shown in unit tests only."},
        {"id": "ana-skills-learners-n", "severity": "medium",
         "text": "On the learner trajectories (three learners, thirty cases each, one with a three-day absence) the help level does lighten as "
                 "deficits fade, but a clock alone ranks the true curve as well as mastery does, the ranking of which deficits fade fastest "
                 "is near chance, and the short absence did not move the level. Three learners make every interval wide."},
        {"id": "ana-routing-circular", "severity": "high",
         "text": "Review routing is grounded in sandbox households scored by calculators whose quirks we planted, against a simplified internal "
                 "reference rather than law. The router finding those quirks shows it recovers our planted structure, not that real calculators "
                 "or real agents fail this way; the task is nearly deterministic, and the plain spread of calculator answers does almost as well."},
        {"id": "ana-pooling-people", "severity": "medium",
         "text": "Cold-start priors are built from four synthetic personas (or 24 scripted apprentices with two cases each); with so few and such "
                 "alike people, partial pooling is hard to tell from complete pooling, and learning-curve drift is not modelled."},
        {"id": "ana-study-power", "severity": "high",
         "text": "The study power analysis only shows what the planned design could detect under assumptions we made up (how much people differ, how big "
                 "the training gain is, how carry-over and fatigue behave). It does not show that an effect exists, and with four people no result "
                 "can reach p below 0.05."},
        {"id": "ana-study-n4", "severity": "high",
         "text": "With four teammates the exact two-sided sign-flip p cannot go below 0.125, and the interval excludes zero only when the four differences "
                 "nearly agree and are large. The expected outcome is an interval that includes zero."},
        {"id": "ana-policy-sim", "severity": "medium",
         "text": "Off-policy evaluation is validated in a simulator whose reward structure we invented, with exactly known propensities. "
                 "Real implicit labels (followed, dismissed, repeated, undone) are noisy proxies for 'it helped'."},
        {"id": "ana-routing-shift", "severity": "high",
         "text": "The routing error bound holds for cases like the ones used to calibrate it. A new benefit rule, calculator site or "
                 "household type breaks that assumption silently. Review time per case is an assumption."},
        {"id": "ana-claims-synthetic", "severity": "medium",
         "text": "Agent-claim calibration has not seen a real agent trace. Code still decides success; a low predicted risk never replaces the check."},
        {"id": "ana-trust-ladder", "severity": "low",
         "text": "The autonomy ladder needs 20 clean shadow runs to reach A2 and about 73 clean runs to reach A3; the demo reaches A1 or A2 at most. "
                 "A3 is a target, not a result."},
    ]


# which register entries apply to which evaluate_* section
SECTION_LIMITATIONS = {
    "hazard": ("ana-synthetic-origin", "ana-hazard-people", "ana-hazard-alerts", "ana-hazard-label", "ana-apprentice-script"),
    "skills": ("ana-synthetic-origin", "ana-skills-saturate", "ana-skills-learners-n"),
    "pooling": ("ana-synthetic-origin", "ana-pooling-people"),
    "study_power": ("ana-synthetic-origin", "ana-study-power", "ana-study-n4"),
    "ope": ("ana-synthetic-origin", "ana-policy-sim"),
    "policy_gate": ("ana-synthetic-origin", "ana-hazard-people", "ana-hazard-label"),
    "routing": ("ana-synthetic-origin", "ana-routing-shift", "ana-routing-circular"),
    "agent_claims": ("ana-synthetic-origin", "ana-claims-synthetic", "ana-trust-ladder"),
}


def limitations_for(section: str) -> list[dict]:
    """The register entries that apply to one evaluate_* section (same {id, text, severity} shape)."""
    ids = set(SECTION_LIMITATIONS[section])
    return [x for x in analytics_limitations() if x["id"] in ids]
