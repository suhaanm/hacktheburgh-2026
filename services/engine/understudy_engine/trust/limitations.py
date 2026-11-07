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
