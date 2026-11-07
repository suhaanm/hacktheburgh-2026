"""The stuck signal: the hazard model's probability that no progress comes in the next minute (ANA-5), with a plain fallback.

The model (``hazard.HazardModel``, the full variant) is fitted once, in the background, on the synthetic personas and
apprentices that are on disk. Until it is ready, or when no data is on disk, a transparent rule is used instead: the
chance of being stuck rises with the time since the last progress event. The source is reported with every reading so
a decision always says which one spoke. Nothing here calls a language model.
"""
from __future__ import annotations

import math
import threading
from typing import Sequence

import numpy as np

from ..core import Cog, Episode

HORIZON = 60.0


def heuristic_p(tsp_s: float) -> float:
    """Fallback: logistic in time since progress, 0.5 at 75 s."""
    return 1.0 / (1.0 + math.exp(-(tsp_s - 75.0) / 20.0))


class StuckScorer:
    def __init__(self, root=None, *, fit: bool = True) -> None:
        self.root = root
        self.fit_enabled = fit
        self._model = None
        self._state = "cold"          # cold | fitting | ready | unavailable
        self._lock = threading.Lock()

    @property
    def state(self) -> str:
        return self._state

    def warm(self, background: bool = True):
        if not self.fit_enabled:
            self._state = "unavailable"
            return None
        with self._lock:
            if self._state != "cold":
                return None
            self._state = "fitting"
        if background:
            th = threading.Thread(target=self._fit, name="coach-hazard-fit", daemon=True)
            th.start()
            return th
        self._fit()
        return None

    def _fit(self) -> None:
        try:
            from ..hazard import HazardModel, build_bins
            from ..hazard.data import load_apprentice_episodes, load_persona_episodes

            eps, _, _ = load_persona_episodes(self.root)
            apps, _, _ = load_apprentice_episodes(self.root)
            tab = build_bins(eps + apps)
            if tab.n < 200:
                raise FileNotFoundError("too little data")
            model = HazardModel("full").fit(tab, np.arange(tab.n))
            self._model, self._state = model, "ready"
        except Exception:           # no data on disk, or anything else: the rule below speaks instead
            self._model, self._state = None, "unavailable"

    def p_stuck(self, *, cogs: Sequence[Cog], progress_t: Sequence[float], t0: float, now: float, person: str, role: str) -> tuple[float, str]:
        """``(p, source)`` at time ``now`` for the episode so far."""
        last = max([p for p in progress_t if p <= now] or [t0])
        tsp = max(0.0, now - last)
        if self._state == "cold":
            self.warm(background=True)
        if self._model is None or not cogs:
            return heuristic_p(tsp), "heuristic"
        try:
            from ..hazard import build_bins

            ep = Episode(task_id="t_live", person=person, role=role, origin="real", t0=t0, t1=now + 2 * HORIZON, cogs=list(cogs), progress_t=list(progress_t))
            tab = build_bins([ep])
            if tab.n == 0:
                return heuristic_p(tsp), "heuristic"
            k = int(np.searchsorted(tab.t, now, side="right")) - 1
            k = min(max(k, 0), tab.n - 1)
            p = float(self._model.predict(tab, np.array([k]))[0])
            return p, "hazard"
        except Exception:
            return heuristic_p(tsp), "heuristic"
