"""Every threshold of the insights layer in one frozen record (REQ-9). Thresholds were set from the design (docs/INSIGHTS_DESIGN.md) and tuned,
where tuned at all, on DEV seeds only (evals/insights/PLAN.md); the held-out seeds are run once. Nothing here is a measured property of people.
"""
from __future__ import annotations

from dataclasses import dataclass

DAY = 86400.0


@dataclass(frozen=True)
class Params:
    # ---- statistics
    alpha_worker: float = 0.05            # Bonferroni family-wise level over the person's admissible tests
    q_admin: float = 0.10                 # Benjamini-Hochberg false-discovery rate over the admin's admissible tests
    level: float = 0.95                   # nominal interval level shown
    family_control: bool = True           # False only in the evaluation's diagnostic: what the false-insight rate would be without it
    n_boot: int = 300                     # person-level bootstrap draws (seeded from ids)
    lost_clip: tuple[float, float] = (-120.0, 600.0)     # seconds beyond the expert median are clipped to this range
    # ---- windows (days)
    recent_days: float = 21.0             # the 3-week smoothing window
    earlier_start_days: float = 49.0      # earlier window = (now - 49 d, now - 28 d]
    earlier_end_days: float = 28.0
    admin_window_days: float = 84.0       # per-person summaries in the admin views
    absence_days: float = 10.0            # a gap this long with no occurrence at all is an absence
    absence_grace_n: int = 3              # first occurrences of each skill after an absence are excluded from relapse and time evidence
    # ---- worker gates
    onboard_min: int = 10                 # fewer assist occurrences in total: an onboarding pointer, no comparison
    stale_days: float = 21.0              # newest row older than this: stale marker
    min_n_loss: int = 6
    min_n_improved: int = 5
    floor_loss_s: float = 10.0
    floor_improved_s: float = 8.0
    milestone_levels: tuple[float, ...] = (0.5, 0.65, 0.8)
    milestone_window: int = 20
    milestone_gain_floor: float = 0.10    # the share finished unaided must have risen by this much against the reference window
    retention_min_n: int = 8
    retention_min_days: float = 14.0
    retention_max_days: float = 120.0
    retention_mastered: float = 0.7
    relapse_baseline_n: int = 15
    relapse_baseline_share: float = 0.8
    relapse_recent_max: int = 10
    relapse_recent_min: int = 6
    relapse_drop_floor: float = 0.25
    automation_hours_floor: float = 0.5
    automation_min_support: int = 3
    # ---- admin gates
    k_anon: int = 5                       # comparison tables: groups below this are merged into "Other"
    min_person_n: int = 10                # occurrences before a person counts as having enough data in a comparison
    enough_n: int = 20                    # occurrences in the admin window for the coverage count
    min_n_skill_person: int = 3           # occurrences of a skill before a person contributes a person-level mean
    role_gap_floor_s: float = 8.0
    trend_floor: float = 0.05
    trend_min_n: int = 8                  # occurrences per person in each trend window
    trend_early_start_days: float = 63.0  # early window (now - 63 d, now - 42 d]
    trend_early_end_days: float = 42.0
    bottleneck_floor: float = 0.10
    unit_floor: float = 0.10
    target_share: float = 0.8             # independence line for onboarding (a design target the firm sets)
    target_window: int = 20
    target_occurrences: int = 60          # reach the line within this many occurrences
    target_reached_share: float = 0.6     # share of new juniors expected to get there in time (a design target)
    onboarding_floor: float = 0.10
    coverage_floor: float = 0.6
    automation_min_routines: int = 3
    automation_min_runs: int = 20
    automation_shadow_lower: float = 0.8
    risk_backlog_h: float = 24.0
    risk_window_days: float = 7.0
    feed_stale_days_risk: float = 2.0
    guard_share_tol: float = 0.10         # a quality share must rise by this much (and credibly, see guard_p) to count as worse
    guard_p: float = 0.25                 # one-sided p of the rise (two-proportion z); a rise inside the noise is not a worse guard
    guard_ttp_ratio: float = 1.25
    guard_ttp_abs_s: float = 3.0
    # ---- scoring
    impact_scale_worker: float = 15.0     # person-minutes per week at which impact reaches about 0.63
    impact_scale_admin: float = 120.0
    assist_cost_s: float = 45.0           # a ranking proxy for what one assisted occurrence costs; NOT a measured saving
    actionability_none: float = 0.7
    recency_tau_days: float = 21.0
    novelty_window_days: float = 28.0
    novelty_floor: float = 0.25           # at or below this the same insight is suppressed
    material_change: float = 0.25         # relative change that resets novelty
    # ---- caps
    worker_cap: int = 3
    admin_cap: int = 7
    admin_max_per_group: int = 3
    risk_impact: tuple[tuple[str, float], ...] = (("injection_pauses", 80.0), ("false_claims", 100.0), ("kill_events", 40.0), ("approval_backlog", 60.0))


DEFAULT = Params()
