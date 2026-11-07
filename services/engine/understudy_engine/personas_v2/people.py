"""People: a hierarchy of random effects with a general ability factor, tenure-based labels, strategy mixtures.

Each person has continuous effects (speed, within-person spread, hesitation, slips, learning rate and form, fatigue,
interruption rate, chronotype, device noise) drawn from the cohort's hyper-parameters, and a latent mastery for each
of the role's skills. The expert or novice *label* is a noisy function of tenure, and tenure is only correlated with
the general ability factor (``tenure_g_corr``), so some "novices" are fast and clean and some "experts" carry deficits.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from .core import choose, dirichlet, expit, logit
from .roles import RoleSpec


@dataclass
class Person:
    id: str
    idx: int
    level: str
    tenure: float                       # prior cases of practice
    g: float                            # general ability (z-score; higher = better)
    log_speed: float                    # log time multiplier (higher = slower)
    within_mult: float
    p_pause: float
    p_slip: float
    learn_alpha: float
    learn_form: str                     # power | exp
    learn_beta: float
    fatigue: float
    chrono_phase_h: float
    interrupt_per_h: float
    theta_inf: dict[str, float]
    theta_gap: float
    strategy: dict[str, list[float]]
    unit_prefs: dict[str, float]
    cap_mult: float
    idle_threshold_s: int
    k_s: float                          # KLM keystroke time for this person
    stuck_report_p: float
    progress_mult: dict[str, float]
    progress_rate_min: float
    mk_rows: dict = field(default_factory=dict)
    habit: list | None = None           # latent_skill: the person's habitual order

    def mean_theta(self) -> float:
        return sum(self.theta_inf.values()) / max(1, len(self.theta_inf))


def _b36(n: int, width: int = 3) -> str:
    chars = "0123456789abcdefghijklmnopqrstuvwxyz"
    s = ""
    for _ in range(width):
        s = chars[n % 36] + s
        n //= 36
    return s


def person_prefix(code: str, seed: int) -> str:
    return f"p_{code}{_b36(seed % 46656)}"


def draw_people(h: dict, role: RoleSpec, n: int, code: str, seed: int, rnd: random.Random) -> list[Person]:
    skills = [d.skill for d in role.deficits]
    offsets = {s: rnd.uniform(-0.4, 0.4) for s in skills}
    pop = {}
    for dim, opts in role.strategy_dims.items():
        if dim in ("verify", "diff", "docs", "plot", "export", "test_first") and len(opts) == 2:
            q = h["verify_reread_pop"] if dim == "verify" else rnd.uniform(0.15, 0.6)
            pop[dim] = [1 - q, q]
        else:
            pop[dim] = dirichlet(rnd, [1.0] * len(opts))
    lam = h["g_loading"]
    resid = math.sqrt(max(1e-9, 1 - lam * lam))
    gs = [rnd.gauss(0.0, 1.0) for _ in range(n)]
    tl = [h["tenure_g_corr"] * g + math.sqrt(1 - h["tenure_g_corr"] ** 2) * rnd.gauss(0.0, 1.0) for g in gs]
    order = sorted(range(n), key=lambda i: -tl[i])
    n_exp = max(1, int(round(h["expert_share"] * n)))
    experts = set(order[:n_exp])
    grp = {True: [tl[i] for i in experts], False: [tl[i] for i in range(n) if i not in experts]}
    stats = {}
    for k, v in grp.items():
        m = sum(v) / max(1, len(v))
        sd = math.sqrt(sum((x - m) ** 2 for x in v) / max(1, len(v))) or 1.0
        stats[k] = (m, sd)
    prefix = person_prefix(code, seed)
    people: list[Person] = []
    for i in range(n):
        g = gs[i]
        is_exp = i in experts
        m, sd = stats[is_exp]
        z_t = (tl[i] - m) / sd
        tenure = math.exp(math.log(h["tenure_expert_median"] if is_exp else h["tenure_novice_median"]) + h["tenure_sd_log"] * z_t)
        log_speed = h["sd_log_speed"] * (-lam * g + resid * rnd.gauss(0.0, 1.0))
        slip_logit = logit(h["slip_med"]) + h["sd_logit_slip"] * (-lam * g + resid * rnd.gauss(0.0, 1.0))
        pause_logit = logit(h["p_pause_med"]) + h["sd_logit_pause"] * (-0.5 * lam * g + math.sqrt(1 - 0.25 * lam * lam) * rnd.gauss(0.0, 1.0))
        alpha = min(1.2, max(0.05, h["learn_alpha_mean"] + h["learn_alpha_sd"] * (0.5 * lam * g + 0.87 * rnd.gauss(0.0, 1.0))))
        theta = {s: 3.3 + 0.9 * g + offsets[s] + h["deficit_difficulty_sd"] * rnd.gauss(0.0, 1.0) for s in skills}
        strat = {}
        for dim, opts in role.strategy_dims.items():
            conc = h["strategy_kappa"] * len(opts)
            strat[dim] = dirichlet(rnd, [max(1e-2, conc * q) for q in pop[dim]])
        prefs = {u.id: math.exp(0.8 * rnd.gauss(0.0, 1.0)) for u in role.units}
        k_s = min(1.2, max(0.12, h["pt_keystroke_s"] * math.exp(log_speed)))   # the published floor (a 90 wpm typist) and ceiling of K
        pmult = {c: math.exp(h["progress_act_noise"] * rnd.gauss(0.0, 1.0)) for c in ("commit", "read", "seek", "revert", "pause")}
        people.append(Person(
            id=f"{prefix}{i:03d}", idx=i, level="expert" if is_exp else "novice", tenure=tenure, g=g, log_speed=log_speed,
            within_mult=math.exp(h["sd_within_person"] * rnd.gauss(0.0, 1.0)),
            p_pause=expit(pause_logit), p_slip=expit(slip_logit), learn_alpha=alpha,
            learn_form="exp" if rnd.random() < h["p_exp_form"] else "power",
            learn_beta=h["learn_beta_novice"] * math.exp(0.25 * rnd.gauss(0.0, 1.0)),
            fatigue=max(0.0, h["fatigue_per_h"] + h["sd_fatigue"] * rnd.gauss(0.0, 1.0)),
            chrono_phase_h=rnd.uniform(11.0, 17.0),
            interrupt_per_h=h["interrupt_per_h"] * math.exp(h["sd_log_interrupt"] * rnd.gauss(0.0, 1.0)),
            theta_inf=theta, theta_gap=h["theta_gap"] * math.exp(0.2 * rnd.gauss(0.0, 1.0)),
            strategy=strat, unit_prefs=prefs, cap_mult=math.exp(0.3 * rnd.gauss(0.0, 1.0)),
            idle_threshold_s=choose(rnd, (60, 120, 300), (0.3, 0.5, 0.2)),
            k_s=k_s, stuck_report_p=min(0.95, max(0.0, h["stuck_report_p"] * math.exp(0.4 * rnd.gauss(0.0, 1.0)))),
            progress_mult=pmult, progress_rate_min=h["progress_rate_per_min"] * math.exp(0.25 * rnd.gauss(0.0, 1.0)),
        ))
    return people
