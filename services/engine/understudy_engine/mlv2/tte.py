"""M2b: time-to-event head, expected minutes until the next progress event (PLAN.md section 6.3).

Discrete-time survival: for each origin bin b (v1's 30 s bins) and step s = 1..K (30 s each, K = 10 so five minutes), the event is "the next
`progress` event falls in (b + 30 (s - 1), b + 30 s]". An origin is at risk at step s while no progress has happened and the episode still
covers the step; an episode that ends first censors the origin from then on. A logistic regression (l2 = 3, v1's code) on v1's features
plus a one-hot step is fitted on the person-period rows, so the hazard is h_s(x) = sigmoid(f(x) + a_s) (proportional-odds, a piecewise
baseline).

Why this form: it handles right censoring exactly, reuses v1's bins and logistic code, and its two-step survival S(60 s) = (1 - h_1)(1 - h_2)
is precisely the probability v1's label asks for (no progress in the next 60 s), so it is scored on the same log loss and compared pairwise
with the v1 classifier. A parametric AFT model (lifelines) would impose one hazard shape and would not give the same-label comparison.
Expected minutes until progress is the restricted mean survival time to 5 minutes, using the origin's features held fixed over the steps
(the model sees the situation at the origin, not the future).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from understudy_engine.core import Episode
from understudy_engine.hazard.features import BIN_S, HORIZON_S, N_HASH, TSP_COLS, BinTable
from understudy_engine.hazard.logreg import LogisticModel
from understudy_engine.trust.calibration import logit, sigmoid

K_STEPS = 10
STEP_S = BIN_S


@dataclass
class TTEData:
    """Per-origin survival outcome aligned with the rows of a BinTable."""

    time_s: np.ndarray        # observed time from the origin to the next progress, or to the end of the episode when censored
    event: np.ndarray         # 1 if a progress event followed within the episode, 0 if censored
    steps_obs: np.ndarray     # fully observed 30 s steps from the origin (capped at K)

    @property
    def n(self) -> int:
        return int(self.time_s.size)


def build_tte(episodes: list[Episode], tab: BinTable) -> TTEData:
    """Outcomes for exactly the bins of ``tab`` (episodes in the order ``build_bins`` consumed them)."""
    t_all, e_all, s_all = [], [], []
    for ep in episodes:
        k_max = int(np.floor((ep.t1 - HORIZON_S - ep.t0) / BIN_S)) + 1 if ep.t1 - ep.t0 >= HORIZON_S else 0
        if k_max <= 0:
            continue
        b = ep.t0 + BIN_S * np.arange(k_max)
        pt = np.sort(np.asarray(ep.progress_t, dtype=float))
        j = np.searchsorted(pt, b, side="right")            # first progress strictly after b
        has = j < pt.size
        nxt = np.where(has, pt[np.minimum(j, max(pt.size - 1, 0))] if pt.size else np.inf, np.inf)
        t_ev = nxt - b
        t_cen = ep.t1 - b
        time_s = np.where(has, t_ev, t_cen)
        t_all.append(time_s)
        e_all.append(has.astype(np.int8))
        s_all.append(np.minimum(np.floor(t_cen / STEP_S + 1e-9), K_STEPS).astype(int))
    if not t_all:
        z = np.zeros(0)
        return TTEData(z, z.astype(np.int8), z.astype(int))
    out = TTEData(np.concatenate(t_all), np.concatenate(e_all), np.concatenate(s_all))
    if out.n != tab.n:
        raise ValueError(f"tte rows {out.n} do not match the bin table {tab.n}: pass the same episodes that built the table")
    return out


def person_period(tte: TTEData, rows: np.ndarray, k_steps: int = K_STEPS) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Expand the given origin rows to person-period rows: (origin row index, step 1..K, event indicator)."""
    t = tte.time_s[rows]
    ev = tte.event[rows].astype(bool)
    step_event = np.where(ev, np.ceil(t / STEP_S - 1e-9).astype(int), 10**6)         # step in which the event happens
    step_event = np.maximum(step_event, 1)
    obs = np.minimum(tte.steps_obs[rows], k_steps)
    last = np.where(ev & (step_event <= k_steps), step_event, np.minimum(obs, k_steps))  # last step at risk
    # an event beyond K steps contributes K non-event rows; a censored origin contributes its observed steps
    last = np.where(ev & (step_event > k_steps), k_steps, last)
    last = np.maximum(last, 0)
    reps = last.astype(int)
    origin = np.repeat(np.arange(rows.size), reps)
    step = np.concatenate([np.arange(1, r + 1) for r in reps]) if reps.sum() else np.zeros(0, int)
    is_ev = (ev & (step_event <= k_steps))[origin] & (step == step_event[origin])
    return origin, step, is_ev.astype(float)


class DiscreteTimeModel:
    """The head: logistic hazard on origin features + one-hot step. ``features='full'`` is v1's design, ``'tsp'`` the baseline."""

    def __init__(self, features: str = "full", l2: float = 3.0, k_steps: int = K_STEPS) -> None:
        if features not in ("full", "tsp"):
            raise ValueError(features)
        self.features, self.l2, self.k = features, l2, k_steps
        self._lr: LogisticModel | None = None
        self._base = 0.5
        self._roles: dict[str, float] = {}

    def _x(self, tab: BinTable, rows: np.ndarray) -> np.ndarray:
        if self.features == "tsp":
            return tab.dense[rows][:, list(TSP_COLS)]
        role = np.array([self._roles.get(str(r), logit(self._base)) for r in tab.role[rows]])
        return np.hstack([tab.hashed[rows].astype(float), tab.dense[rows], role[:, None]])

    def _mask(self, d: int) -> np.ndarray:
        m = np.zeros(d, dtype=bool)
        m[(N_HASH if self.features == "full" else 0):] = True
        return m

    def fit(self, tab: BinTable, tte: TTEData, rows: np.ndarray) -> "DiscreteTimeModel":
        y0 = tab.y[rows].astype(float)
        self._base = float(np.clip(y0.mean(), 1e-4, 1 - 1e-4)) if y0.size else 0.5
        self._roles = {str(r): float(logit(np.clip(y0[tab.role[rows] == r].mean(), 1e-4, 1 - 1e-4))) for r in np.unique(tab.role[rows])}
        origin, step, ev = person_period(tte, rows, self.k)
        X0 = self._x(tab, rows)
        onehot = np.zeros((step.size, self.k))
        onehot[np.arange(step.size), step - 1] = 1.0
        X = np.hstack([X0[origin], onehot])
        mask = np.concatenate([self._mask(X0.shape[1]), np.zeros(self.k, dtype=bool)])
        self._lr = LogisticModel(l2=self.l2).fit(X, ev, standardize=mask)
        return self

    def hazards(self, tab: BinTable, rows: np.ndarray) -> np.ndarray:
        """(len(rows), K) discrete hazards h_s."""
        assert self._lr is not None, "fit first"
        X0 = self._x(tab, rows)
        out = np.zeros((rows.size, self.k))
        for s in range(self.k):
            oh = np.zeros((rows.size, self.k))
            oh[:, s] = 1.0
            out[:, s] = self._lr.predict_proba(np.hstack([X0, oh]))
        return out

    def survival(self, tab: BinTable, rows: np.ndarray) -> np.ndarray:
        """(len(rows), K + 1) with S(0) = 1 and S(s) = prod_{j<=s} (1 - h_j)."""
        h = self.hazards(tab, rows)
        return np.hstack([np.ones((rows.size, 1)), np.cumprod(1.0 - h, axis=1)])

    def prob_no_progress_60s(self, tab: BinTable, rows: np.ndarray) -> np.ndarray:
        return np.clip(self.survival(tab, rows)[:, 2], 1e-6, 1 - 1e-6)

    def expected_minutes(self, tab: BinTable, rows: np.ndarray) -> np.ndarray:
        """Restricted mean time to progress, minutes, capped at K steps (five minutes)."""
        S = self.survival(tab, rows)
        return (S[:, :-1].sum(axis=1) * STEP_S) / 60.0


class KMConstant:
    """Population Kaplan-Meier restricted mean (the constant baseline for the expected-minutes head)."""

    def __init__(self, k_steps: int = K_STEPS) -> None:
        self.k = k_steps
        self.s_ = np.ones(k_steps + 1)

    def fit(self, tte: TTEData, rows: np.ndarray) -> "KMConstant":
        origin, step, ev = person_period(tte, rows, self.k)
        s = np.ones(self.k + 1)
        for j in range(1, self.k + 1):
            at = step == j
            n = int(at.sum())
            d = float(ev[at].sum())
            s[j] = s[j - 1] * (1.0 - d / n if n > 0 else 1.0)
        self.s_ = s
        return self

    def survival_row(self) -> np.ndarray:
        return self.s_

    def expected_minutes(self) -> float:
        return float(self.s_[:-1].sum() * STEP_S / 60.0)


def km_restricted_mean(time_s: np.ndarray, event: np.ndarray, cap_s: float = K_STEPS * STEP_S) -> float:
    """Kaplan-Meier restricted mean survival time (minutes) up to ``cap_s`` from continuous durations and an event indicator."""
    t = np.asarray(time_s, float)
    e = np.asarray(event, int)
    if t.size == 0:
        return float("nan")
    order = np.argsort(t, kind="mergesort")
    t, e = t[order], e[order]
    uniq, first = np.unique(t, return_index=True)
    at_risk = (t.size - first).astype(float)
    d = np.add.reduceat(e, first).astype(float)
    surv = np.cumprod(1.0 - d / at_risk)
    times = np.concatenate([[0.0], uniq, [np.inf]])
    vals = np.concatenate([[1.0], surv])
    seg = np.minimum(times[1:], cap_s) - np.minimum(times[:-1], cap_s)
    return float((vals * seg).sum() / 60.0)


def concordance(time_s: np.ndarray, event: np.ndarray, pred_minutes: np.ndarray) -> float | None:
    """Harrell's concordance of predicted expected minutes with observed time to progress, censoring handled (lifelines)."""
    from lifelines.utils import concordance_index

    t = np.asarray(time_s, float)
    e = np.asarray(event, int)
    if (e == 1).sum() < 2 or t.size < 3:
        return None
    return float(concordance_index(t, np.asarray(pred_minutes, float), e))


@dataclass
class TTEOof:
    s60: np.ndarray            # (n,) P(no progress in 60 s) from the head, leave one person out
    minutes: np.ndarray        # (n,) expected minutes to progress
    s60_tsp: np.ndarray        # baseline discrete model, tsp features only
    minutes_tsp: np.ndarray
    km_minutes: np.ndarray     # (n,) constant population restricted mean (training people)


def oof_tte(tab: BinTable, tte: TTEData, *, people: list[str] | None = None) -> TTEOof:
    """Leave-one-person-out predictions of the head and of its two baselines."""
    n = tab.n
    out = TTEOof(*(np.full(n, np.nan) for _ in range(5)))
    for o in people or tab.people:
        rest = [q for q in tab.people if q != o]
        tr, te = tab.rows_of(rest), tab.rows_of([o])
        m = DiscreteTimeModel("full").fit(tab, tte, tr)
        out.s60[te] = m.prob_no_progress_60s(tab, te)
        out.minutes[te] = m.expected_minutes(tab, te)
        b = DiscreteTimeModel("tsp").fit(tab, tte, tr)
        out.s60_tsp[te] = b.prob_no_progress_60s(tab, te)
        out.minutes_tsp[te] = b.expected_minutes(tab, te)
        out.km_minutes[te] = KMConstant().fit(tte, tr).expected_minutes()
    return out


def calibration_by_quantile(tab_people: np.ndarray, time_s: np.ndarray, event: np.ndarray, pred_min: np.ndarray, q: int = 5) -> list[dict]:
    """Predicted restricted mean against the Kaplan-Meier restricted mean within quantile groups of the prediction."""
    order = np.argsort(pred_min, kind="mergesort")
    groups = np.array_split(order, q)
    rows = []
    for g in groups:
        if g.size == 0:
            continue
        rows.append({"n": int(g.size), "predicted_min": float(pred_min[g].mean()),
                     "observed_km_min": km_restricted_mean(time_s[g], event[g]),
                     "n_people": int(len(set(tab_people[g].tolist())))})
    return rows
