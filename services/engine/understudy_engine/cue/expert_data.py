"""Expert cog paths for the path prior (CUE-1): the synthetic apprentices' experts, and a policy-sampled family.

Two families, so the candidate model is also tested on a generator it was not fitted to:

* **A, apprentices** (``data/synthetic/apprentices/truth.json``): 8 scripted experts with 2 cases each, two allowed orderings. Real
  v1 traces from the engine-data generator. Benefits pack only.
* **B, sampled from the pack policy** (``sample_paths``): for any pack with a step policy, random linear extensions of the pack's
  partial order with person-level style (a person batches the cliff checks after the calculators with some probability, or checks
  each right after its calculator), cog-level noise (a repeated read, an idle spell), and 20 to 40 people. It is written from the
  pack's order rules, so it agrees with them by construction: a test of how the model copes with spread, not of whether the rules
  are right.

Everything here is synthetic and says so.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from . import paths
from .vocab import StepVocab


def apprentice_expert_paths(root: Path | str | None = None) -> dict[str, list[list[str]]]:
    """``{person: [cog id list per case]}`` for the apprentices flagged as experts; ``{}`` when the file is absent."""
    base = Path(root) if root else paths.data_dir()
    p = base / "synthetic" / "apprentices" / "truth.json"
    if not p.is_file():
        return {}
    t = json.loads(p.read_text(encoding="utf-8"))
    experts = {x["person"] for x in t.get("people", []) if x.get("level") == "expert"}
    out: dict[str, list[list[str]]] = {}
    for tr in t.get("traces", []):
        if tr["person"] in experts:
            out.setdefault(tr["person"], []).append([c[0] for c in tr["cogs"]])
    return out


def apprentice_novice_paths(root: Path | str | None = None) -> dict[str, list[list[str]]]:
    base = Path(root) if root else paths.data_dir()
    p = base / "synthetic" / "apprentices" / "truth.json"
    if not p.is_file():
        return {}
    t = json.loads(p.read_text(encoding="utf-8"))
    nov = {x["person"] for x in t.get("people", []) if x.get("level") == "novice"}
    out: dict[str, list[list[str]]] = {}
    for tr in t.get("traces", []):
        if tr["person"] in nov:
            out.setdefault(tr["person"], []).append([c[0] for c in tr["cogs"]])
    return out


def sample_steps(vocab: StepVocab, rng: np.random.Generator, *, batch_p: float, optional_p: float = 0.6) -> list[str]:
    """One case as an ordered list of step ids: a random linear extension of the pack's partial order. A person who batches does all
    the calculators first (policy order); one who does not takes what was just unlocked first (each cliff check right after its
    calculator)."""
    policy = vocab.policy
    include = [sid for sid in policy.order if policy.steps[sid].required or rng.random() < optional_p]
    done: set[str] = set()
    unlocked_at: dict[str, int] = {}
    seq: list[str] = []
    batch = rng.random() < batch_p
    k = 0
    while len(done) < len(include):
        ready = [s for s in include if s not in done and all(a in done or a not in include for a in policy.steps[s].after)]
        if not ready:
            break
        for s in ready:
            unlocked_at.setdefault(s, k)
        sid = ready[0] if batch else max(ready, key=lambda s: (unlocked_at[s], -policy.order.index(s)))
        k += 1
        done.add(sid)
        seq.append(sid)
    return seq


def sample_path(vocab: StepVocab, rng: np.random.Generator, *, batch_p: float, optional_p: float = 0.6, noise_p: float = 0.05) -> list[str]:
    """One expert case as a cog sequence: the steps of ``sample_steps`` expanded to cogs, with light noise."""
    policy = vocab.policy
    seq: list[str] = []
    for sid in sample_steps(vocab, rng, batch_p=batch_p, optional_p=optional_p):
        for c in policy.steps[sid].cogs:
            seq.append(c)
            if rng.random() < noise_p / 2:
                seq.append(c)                            # a repeated read or check
        if rng.random() < noise_p:
            seq.append("IDLE")
    return seq


def sample_paths(vocab: StepVocab, *, n_people: int = 30, cases: int = 3, seed: int = 0, batch_beta: tuple[float, float] = (1.2, 4.0)) -> dict[str, list[list[str]]]:
    rng = np.random.default_rng(seed)
    out: dict[str, list[list[str]]] = {}
    for i in range(n_people):
        batch_p = float(rng.beta(*batch_beta))
        noise = float(rng.uniform(0.0, 0.08))
        out[f"p_s{i + 1:02d}"] = [sample_path(vocab, rng, batch_p=batch_p, noise_p=noise) for _ in range(cases)]
    return out


def expert_paths_for(vocab: StepVocab, root: Path | str | None = None) -> tuple[dict[str, list[list[str]]], str]:
    """The paths the live path prior is fitted on and a label saying where they came from."""
    if vocab.role == "benefits-processor":
        a = apprentice_expert_paths(root)
        if a:
            return a, "scripted apprentices (8 experts)"
    return sample_paths(vocab, n_people=30, cases=3, seed=17), "sampled from the pack's order rules (30 generated experts)"
