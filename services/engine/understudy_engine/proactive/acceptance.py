"""Per-person acceptance learning (PRO-3). A press is an accept, a dismissal is a decline, and a decline is a label.

Same idea as the engine-handoff proposal timing (``routines/timing.py``, HND-7): a Beta posterior over accepts and
declines, started from the role prior (``priors.yaml: accept``, Beta(2, 3), mean 0.4), reimplemented here so the
proactive layer imports nothing from the handoff track. The estimate for a kind of card (practice, automate and so on)
is shrunk toward the person's overall rate, so one decline of one kind does not bury the others.

An expired card (never touched) is not a label: ignoring a card is not the same as declining it.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .candidates import KINDS

DEFAULT_PRIOR = (2.0, 3.0)


def role_prior(role: str | None, packs_dir: Path | None = None) -> tuple[float, float]:
    """The role's accept prior (alpha, beta) from its pack, or Beta(2, 3)."""
    if not role:
        return DEFAULT_PRIOR
    try:
        import yaml

        from .paths import packs_dir as default_packs

        p = (packs_dir or default_packs()) / role / "priors.yaml"
        from ..yamlcache import load_yaml_file

        a = (load_yaml_file(p) or {}).get("accept") or {}
        return float(a.get("alpha", DEFAULT_PRIOR[0])), float(a.get("beta", DEFAULT_PRIOR[1]))
    except Exception:
        return DEFAULT_PRIOR


@dataclass
class AcceptanceModel:
    alpha0: float = DEFAULT_PRIOR[0]
    beta0: float = DEFAULT_PRIOR[1]
    shrink: float = 3.0            # pseudo-observations pulling a kind's estimate toward the person's overall rate
    acc: dict[str, int] = field(default_factory=dict)
    dec: dict[str, int] = field(default_factory=dict)

    @classmethod
    def from_labels(cls, labels: Iterable[dict[str, Any]], prior: tuple[float, float] = DEFAULT_PRIOR) -> AcceptanceModel:
        m = cls(alpha0=prior[0], beta0=prior[1])
        for lb in labels:
            m.observe(str(lb.get("kind")), bool(lb.get("accepted")))
        return m

    def observe(self, kind: str, accepted: bool) -> None:
        (self.acc if accepted else self.dec)[kind] = (self.acc if accepted else self.dec).get(kind, 0) + 1

    def overall(self) -> float:
        a, d = sum(self.acc.values()), sum(self.dec.values())
        return (self.alpha0 + a) / (self.alpha0 + self.beta0 + a + d)

    def p(self, kind: str) -> float:
        base = self.overall()
        a, d = self.acc.get(kind, 0), self.dec.get(kind, 0)
        return (a + self.shrink * base) / (a + d + self.shrink)

    def n_labels(self) -> int:
        return sum(self.acc.values()) + sum(self.dec.values())

    def summary(self) -> dict[str, Any]:
        """For the card's explanation and the evaluation: counts and the estimate per kind."""
        return {"labels": self.n_labels(), "accepted": sum(self.acc.values()), "declined": sum(self.dec.values()),
                "p_overall": round(self.overall(), 3),
                "by_kind": {k: {"accepted": self.acc.get(k, 0), "declined": self.dec.get(k, 0), "p": round(self.p(k), 3)}
                            for k in KINDS if k in self.acc or k in self.dec}}
