"""Generator parameter ranges (domain randomisation) for the realistic personas.

Every cohort (and every workweek set) draws one value per row below from its range, with its own seed, so two cohorts
of the same family differ in how strong the person effects are, how bursty the pauses are, how noisy the capture is,
and so on. The ranges are the pre-registered priors (``evals/realism/PLAN.md`` quotes this file's SHA-256 and the
table printed by ``render_table``). They were set from the published regularities in ``cited.py`` where one was
found, and are deliberately wide where none was. They were NOT tuned to make any analytic look good or bad.

``dist`` is ``uniform`` or ``loguniform`` (uniform in the log). ``cite`` points at a ``cited.CITED`` key or is
``assumption``.
"""
from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass(frozen=True)
class P:
    name: str
    lo: float
    hi: float
    dist: str = "uniform"
    cite: str = "assumption"
    doc: str = ""


# ----------------------------------------------------------------------------------------------- the table
PARAMS: tuple[P, ...] = (
    # --- between-person hierarchy
    P("sd_log_speed", 0.12, 0.30, "uniform", "klm_keystroke_s", "SD across people of log speed (KLM tiers 0.12 to 0.28 s span a factor 2.3: SD about 0.2)"),
    P("sd_within", 0.25, 0.55, "uniform", "assumption", "within-person log-SD of a cog's dwell"),
    P("sd_within_person", 0.10, 0.35, "uniform", "assumption", "SD across people of the log multiplier on the within-person log-SD"),
    P("p_pause_med", 0.03, 0.12, "loguniform", "pause_lognormal_mixture", "median per-step probability of a hesitation pause"),
    P("sd_logit_pause", 0.4, 0.9, "uniform", "assumption", "SD across people of the logit of the pause probability"),
    P("pause_mix_lognormal", 0.3, 0.7, "uniform", "burstiness_cv", "share of pauses drawn from a lognormal (rest Lomax)"),
    P("pause_ln_median_s", 4.0, 12.0, "uniform", "pause_lognormal_mixture", "median pause, lognormal component (s)"),
    P("pause_ln_sigma", 0.8, 1.3, "uniform", "pause_lognormal_mixture", "log-SD of the lognormal pause component"),
    P("pause_lomax_alpha", 1.1, 2.2, "uniform", "burstiness_cv", "tail index of the Lomax pause component"),
    P("pause_lomax_scale_s", 3.0, 10.0, "uniform", "assumption", "scale of the Lomax pause component (s)"),
    P("slip_med", 0.008, 0.04, "loguniform", "slip_rate_per_step", "median per-step slip probability"),
    P("sd_logit_slip", 0.3, 0.7, "uniform", "typing_population", "SD across people of the logit of the slip probability"),
    P("g_loading", 0.3, 0.7, "uniform", "typing_population", "loading of the general ability factor on speed, slips, hesitation and learning (faster people slip less, so slowness and slips correlate positively)"),
    P("theta_gap", 3.0, 6.0, "uniform", "assumption", "gap in log-odds mastery between zero practice and the asymptote"),
    # --- practice, warm-up, fatigue, time of day
    P("learn_alpha_mean", 0.2, 0.7, "uniform", "power_law_exponent", "mean learning exponent across people"),
    P("learn_alpha_sd", 0.05, 0.20, "uniform", "power_law_exponent", "SD of the learning exponent across people"),
    P("learn_beta_novice", 0.5, 1.2, "uniform", "assumption", "initial relative slowdown above the asymptote at zero practice"),
    P("p_exp_form", 0.3, 0.7, "uniform", "power_law_exponent", "share of people whose individual curve is exponential, not a power law"),
    P("warmup", 0.0, 0.25, "uniform", "practice_forgetting", "relative slowdown at the start of a session (decays over ten minutes)"),
    P("forget_tau_days", 3.0, 20.0, "uniform", "practice_forgetting", "time constant of forgetting between sessions (days)"),
    P("fatigue_per_h", 0.0, 0.12, "uniform", "fatigue_slowdown_per_hour", "mean slowdown per hour of continuous work"),
    P("sd_fatigue", 0.02, 0.06, "uniform", "assumption", "SD across people of the fatigue slope"),
    P("circadian_amp", 0.0, 0.08, "uniform", "circadian_amplitude", "amplitude of the time-of-day speed multiplier"),
    # --- interruptions
    P("interrupt_per_h", 0.5, 5.0, "loguniform", "interruptions_per_hour", "median interruptions per hour of work"),
    P("sd_log_interrupt", 0.3, 0.8, "uniform", "assumption", "SD across people of the log interruption rate"),
    P("int_len_median_s", 15.0, 120.0, "uniform", "interruption_recovery_min", "median length of an ordinary interruption (s)"),
    P("int_len_sigma", 0.8, 1.4, "uniform", "interruption_recovery_min", "log-SD of interruption length"),
    P("int_long_share", 0.03, 0.15, "uniform", "interruption_recovery_min", "share of interruptions that are long (minutes)"),
    P("int_long_median_s", 300.0, 1500.0, "uniform", "interruption_recovery_min", "median length of a long interruption (s)"),
    P("resume_reread_p", 0.3, 0.8, "uniform", "interruption_recovery_min", "probability of re-reading after an interruption"),
    P("resume_slow", 1.1, 1.6, "uniform", "interruption_recovery_min", "slowdown multiplier on the next two steps after resuming"),
    P("resume_error_mult", 1.0, 1.6, "uniform", "interruption_recovery_min", "multiplier on slip probability right after resuming"),
    # --- strategy mixtures
    P("strategy_kappa", 0.5, 3.0, "uniform", "assumption", "Dirichlet concentration of a person's strategy mixture around the population's"),
    P("verify_reread_pop", 0.05, 0.30, "uniform", "assumption", "population share of the legitimate verification re-read strategy"),
    # --- skill-specific deficits (benefits role; thin roles use their pack's deficits)
    P("deficit_difficulty_sd", 0.3, 0.8, "uniform", "assumption", "SD of the skill-specific component of ability (deficits overlap through the general factor)"),
    P("pmax_skip_cliff", 0.5, 0.95, "uniform", "assumption", "per-check skip probability at zero mastery"),
    P("rework_found_p", 0.3, 0.9, "uniform", "assumption", "probability that a skipped check is found at reconciliation and reworked"),
    P("reread_mean_max", 1.0, 2.5, "uniform", "assumption", "mean extra re-reads after a result at zero mastery"),
    P("search_rounds_max", 1.5, 3.5, "uniform", "assumption", "mean search-read rounds at zero mastery"),
    P("copy_error_pmax", 0.3, 0.7, "uniform", "assumption", "probability of copying the wrong figure at zero mastery"),
    P("idle_pmax", 0.5, 0.9, "uniform", "assumption", "probability of a long hesitation before entering at zero mastery"),
    P("idle_lomax_scale_s", 10.0, 40.0, "uniform", "assumption", "scale of the long hesitation (Lomax, s)"),
    P("idle_lomax_alpha", 1.3, 2.5, "uniform", "burstiness_cv", "tail index of the long hesitation"),
    P("material_s", 5.0, 5.0, "uniform", "assumption", "a deficit occurrence is material when it costs at least this many seconds (fixed)"),
    # --- composition of the cohort
    P("expert_share", 0.3, 0.5, "uniform", "assumption", "share of people labelled experts"),
    P("tenure_expert_median", 100.0, 600.0, "loguniform", "assumption", "median prior cases of a person above the tenure cut"),
    P("tenure_novice_median", 2.0, 30.0, "loguniform", "assumption", "median prior cases of a person below the tenure cut"),
    P("tenure_sd_log", 0.5, 1.0, "uniform", "assumption", "log-SD of tenure within the group"),
    P("tenure_g_corr", 0.5, 0.9, "uniform", "assumption", "correlation of tenure with the general ability factor (the label is only partly the ability)"),
    # --- session timeline of the cohort
    P("session_gap_days_mean", 0.8, 2.5, "uniform", "assumption", "mean days between sessions"),
    P("cases_per_session_mean", 2.0, 4.5, "uniform", "assumption", "mean cases per session"),
    P("between_case_gap_median_s", 60.0, 600.0, "loguniform", "assumption", "median pause between cases within a session (s)"),
    P("start_hour_mean", 8.5, 10.5, "uniform", "assumption", "mean session start hour (UTC)"),
    P("start_hour_sd", 0.5, 1.5, "uniform", "assumption", "SD of the session start hour"),
    # --- capture noise (the instrument)
    P("drop_p", 0.0, 0.12, "uniform", "assumption", "probability an event is dropped"),
    P("drop_burst_p", 0.0, 0.30, "uniform", "assumption", "probability a drop starts an outage that drops the next 1 to 5 events"),
    P("jitter_sd_s", 0.05, 0.60, "uniform", "assumption", "SD of timestamp jitter (s)"),
    P("double_p", 0.0, 0.05, "uniform", "assumption", "probability an event fires twice within 20 to 400 ms"),
    P("zone_err_p", 0.0, 0.04, "uniform", "assumption", "probability an event carries a wrong zone"),
    P("label_missing_p", 0.0, 0.15, "uniform", "assumption", "probability an event has no label hash"),
    P("coarse_ts_p", 0.0, 0.05, "uniform", "assumption", "probability a timestamp is rounded to the whole second"),
    P("task_end_missing_p", 0.0, 0.08, "uniform", "assumption", "probability a task_end marker is missing"),
    P("os_skew_s", 0.0, 2.0, "uniform", "assumption", "clock skew between the OS source and the browser source (s)"),
    P("event_rate_per_s", 0.15, 0.7, "uniform", "burstiness_cv", "mean interaction events per second of an active cog"),
    P("event_gap_sigma", 0.8, 1.4, "uniform", "burstiness_cv", "log-SD of the gap between events inside a cog (burstiness)"),
    # --- the progress label: a point process driven by hidden stuck episodes, not by an emission table
    P("progress_rate_per_min", 0.8, 2.4, "uniform", "assumption", "progress events per minute of ordinary working activity (before hidden-state suppression)"),
    P("progress_act_noise", 0.1, 0.5, "uniform", "assumption", "log-SD across people of the activity-class multipliers of the progress rate"),
    P("progress_lag_s", 0.0, 3.0, "uniform", "assumption", "mean lag of a progress event behind the moment it happened (s)"),
    P("stuck_suppress_full_p", 0.4, 0.8, "uniform", "assumption", "probability a hidden stuck episode suppresses progress completely"),
    P("stuck_suppress_partial", 0.15, 0.6, "uniform", "assumption", "rate multiplier on progress during a stuck episode that does not suppress it completely"),
    P("benign_detour_share", 0.2, 0.6, "uniform", "assumption", "share of detour episodes that are not stuck at all (they look the same and do not suppress progress)"),
    P("silent_stuck_share", 0.1, 0.4, "uniform", "assumption", "share of stuck episodes that show no detour behaviour (a quiet stall)"),
    P("spurious_progress_per_h", 0.2, 2.0, "loguniform", "assumption", "progress events not tied to anything (autosave, redundant saves), per hour"),
    P("stuck_report_p", 0.05, 0.6, "uniform", "assumption", "probability a stuck episode gets a self-reported stuck event"),
    P("stuck_false_per_h", 0.0, 0.5, "uniform", "assumption", "stuck reports outside any stuck episode, per hour"),
    # --- family: markov
    P("mk_detour_base", 0.04, 0.25, "loguniform", "assumption", "markov: per-step probability of starting a detour"),
    P("mk_selfexcite", 0.2, 0.7, "uniform", "burstiness_cv", "markov: probability a detour continues (self-excitation)"),
    P("mk_dirichlet_conc", 2.0, 12.0, "uniform", "assumption", "markov: concentration of people's detour matrices around the role's"),
    P("mk_backtrack_p", 0.0, 0.10, "uniform", "assumption", "markov: probability of going back a step"),
    P("mk_skipahead_p", 0.0, 0.08, "uniform", "assumption", "markov: probability of skipping ahead a step"),
    # --- family: latent_skill
    P("ls_hesitate_a", -2.0, -0.6, "uniform", "assumption", "latent_skill: intercept of the logit of leaving flow for hesitation at log-odds mastery 1 (a mastery of 0.73)"),
    P("ls_hesitate_b", 1.0, 3.0, "uniform", "assumption", "latent_skill: how strongly low mastery pushes towards hesitation"),
    P("ls_hes_to_stuck", 0.25, 0.6, "uniform", "assumption", "latent_skill: probability a hesitation becomes a stuck episode"),
    P("ls_stuck_median_s", 40.0, 150.0, "uniform", "assumption", "latent_skill: median stuck episode length (s)"),
    P("ls_stuck_lomax_alpha", 1.2, 2.2, "uniform", "burstiness_cv", "latent_skill: tail index of stuck episode length"),
    P("ls_theta_gain", 0.5, 2.0, "uniform", "power_law_exponent", "latent_skill: gain in log-odds mastery from practice"),
    # --- family: process_trace
    P("pt_pointing_a_s", 0.15, 0.55, "uniform", "fitts_mouse_throughput_bps", "process_trace: Fitts intercept (s); with the slope below it keeps the mean ISO throughput inside 2.5 to 6 bits/s"),
    P("pt_pointing_b_s", 0.12, 0.20, "uniform", "fitts_mouse_slope_s_per_bit", "process_trace: Fitts slope (s per bit)"),
    P("pt_keystroke_s", 0.12, 0.40, "loguniform", "klm_keystroke_s", "process_trace: median keystroke time K across people (s)"),
    P("pt_mental_s", 0.9, 2.0, "uniform", "klm_mental_s", "process_trace: mental operator M (s)"),
    P("pt_homing_s", 0.3, 0.6, "uniform", "klm_homing_s", "process_trace: homing operator H (s)"),
    P("pt_hick_b_s", 0.05, 0.30, "uniform", "hick_hyman_slope_s_per_bit", "process_trace: Hick-Hyman slope (s per bit)"),
    P("pt_method_switch_p", 0.0, 0.15, "uniform", "assumption", "process_trace: probability of switching method mid-task"),
    P("pt_retry_p", 0.02, 0.15, "uniform", "assumption", "process_trace: probability a step fails and is retried"),
    # --- workweeks (routines and presence)
    P("wk_p_work_weekday", 0.75, 0.97, "uniform", "assumption", "workweeks: probability of working on a weekday"),
    P("wk_p_work_weekend", 0.0, 0.20, "uniform", "assumption", "workweeks: probability of working on a weekend day"),
    P("wk_start_mean_h", 8.0, 10.0, "uniform", "assumption", "workweeks: mean start hour"),
    P("wk_start_day_sd_h", 0.3, 1.5, "uniform", "assumption", "workweeks: SD of the start hour across days"),
    P("wk_start_ar", 0.0, 0.5, "uniform", "assumption", "workweeks: day-to-day autocorrelation of the start hour"),
    P("wk_len_h", 5.0, 8.5, "uniform", "assumption", "workweeks: mean working window length (h)"),
    P("wk_holiday_p", 0.02, 0.08, "uniform", "assumption", "workweeks: probability a weekday is a day off"),
    P("wk_tasks_per_h", 2.0, 6.0, "uniform", "assumption", "workweeks: tasks started per active hour"),
    P("wk_task_gap_sigma", 0.8, 1.3, "uniform", "burstiness_cv", "workweeks: log-SD of the gap between tasks"),
    P("wk_routine_share", 0.25, 0.60, "uniform", "assumption", "workweeks: share of tasks that are instances of a planted routine"),
    P("wk_routine_drift", 0.0, 0.30, "uniform", "assumption", "workweeks: weekly drift of the routine variant probabilities"),
    P("wk_split_p", 0.0, 0.12, "uniform", "assumption", "workweeks: probability a routine instance is split into two episodes by a task-detector error"),
    P("wk_interleave_p", 0.0, 0.15, "uniform", "assumption", "workweeks: probability another task is started in the middle of a routine"),
)

PARAM_BY_NAME = {p.name: p for p in PARAMS}


def draw_hyper(rng: np.random.Generator, overrides: dict[str, float] | None = None) -> dict[str, float]:
    """One value per row, drawn in table order (so the stream is stable when a row is appended at the end)."""
    out: dict[str, float] = {}
    for p in PARAMS:
        u = float(rng.random())
        if p.dist == "loguniform":
            out[p.name] = float(math.exp(math.log(p.lo) + u * (math.log(p.hi) - math.log(p.lo))))
        else:
            out[p.name] = float(p.lo + u * (p.hi - p.lo))
    if overrides:
        for k, v in overrides.items():
            if k not in PARAM_BY_NAME:
                raise KeyError(f"unknown generator parameter {k!r}")
            out[k] = float(v)
    return out


def params_sha256() -> str:
    """SHA-256 of this file: PLAN.md quotes it, the report prints it, a mismatch is flagged."""
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def render_table() -> str:
    """Markdown table of every range, for PLAN.md and REPORT.md (machine output, never typed by hand)."""
    lines = ["| Parameter | Low | High | Scale | Cited regularity (status) | Meaning |", "|---|---|---|---|---|---|"]
    from .cited import CITED

    for p in PARAMS:
        c = CITED.get(p.cite)
        tag = "assumption" if p.cite == "assumption" else f"{p.cite} ({c['status'] if c else '?'})"
        lines.append(f"| `{p.name}` | {p.lo:g} | {p.hi:g} | {p.dist} | {tag} | {p.doc} |")
    return "\n".join(lines)
