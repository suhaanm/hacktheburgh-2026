"""Evaluation of the next-step candidates on held-out expert paths (CUE-1).

Question: given the last cogs of an expert's case, how often is the step the expert takes next among the top candidate and the top three,
and are the probabilities honest? Units and rules, fixed before any run:

* A POSITION is one place in an expert case: the history of cogs so far, and the cog that came next. Its truth is the interchangeable-step
  group (calc_a/b/c are one group) that the next cog starts or continues under the pack's own order rules. Positions whose next cog
  belongs to no step (an idle spell, a repeated cog the rules do not enable) are counted and left out (``off_policy``).
* ``boundary`` positions (the next cog starts a new step, that is, the worker has finished one step and must choose the next) are the
  headline: continuing a step in progress is trivial. ``all`` positions are reported beside them.
* Split: leave-one-person-out over experts (a person's own cases are never in the model that scores them). Intervals: percentile
  bootstrap over PEOPLE (clusters), 95%.
* Predictors: ``cue`` (n-gram of order 3 with backoff, plus the pack order rules), ``cue_order1`` (order 1 with rules), ``ngram_no_rules``
  (order 3, no rules), ``bigram`` (order 1, no rules; the "bigram only" baseline) and ``unigram`` (the most common next cog overall;
  the constant baseline). All produce a distribution over the same step groups, so one set of metrics applies to all.
* Metrics: top-1 and top-3 accuracy, Brier score of the top-1 probability (binary: is the top-1 right), ECE with 10 bins, and the negative
  log-likelihood of the true group. A calibration table (reliability) for ``cue``.
* Families: A = the 8 synthetic apprentice experts (two scripted orderings), B = 30 experts sampled from the pack's order rules with person
  style and noise. B follows the pack's rules by construction, so B tests spread, not the rules. Cross-family: fit on A, test on B and the
  other way round.

All of it is synthetic and says so.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from ..trust.meta import analytic_meta
from . import expert_data as XD
from .candidates import NextStepModel, enabled_cogs
from .vocab import StepVocab, get_vocab

N_BINS = 10
PREDICTORS = ("cue", "cue_order1", "ngram_no_rules", "bigram", "unigram")


@dataclass(frozen=True)
class Position:
    history: tuple[str, ...]
    truth: str
    boundary: bool


def positions_of(vocab: StepVocab, seq: list[str]) -> tuple[list[Position], int]:
    out, off = [], 0
    for i, c in enumerate(seq):
        em = enabled_cogs(vocab, seq[:i])
        if c in em:
            sid, in_prog = em[c]
            out.append(Position(tuple(seq[:i]), vocab.group(sid), not in_prog))
        else:
            off += 1
    return out, off


def _models(vocab: StepVocab, train: list[list[str]]) -> dict[str, tuple[NextStepModel, bool]]:
    return {
        "cue": (NextStepModel(vocab, k=3).fit(train), True),
        "cue_order1": (NextStepModel(vocab, k=1).fit(train), True),
        "ngram_no_rules": (NextStepModel(vocab, k=3).fit(train), False),
        "bigram": (NextStepModel(vocab, k=1).fit(train), False),
        "unigram": (NextStepModel(vocab, k=0).fit(train), False),
    }


def _score_positions(models: dict[str, tuple[NextStepModel, bool]], pos: list[Position]) -> dict[str, dict[str, np.ndarray]]:
    """Per predictor, per position: p_top1, top1 correct, top3 correct, p of the truth."""
    out: dict[str, dict[str, list[float]]] = {k: defaultdict(list) for k in models}
    for p in pos:
        for name, (m, rules) in models.items():
            sc = m.group_scores(p.history, rules=rules)
            order = sorted(sc, key=lambda g: -sc[g])
            out[name]["p1"].append(sc[order[0]])
            out[name]["hit1"].append(float(order[0] == p.truth))
            out[name]["hit3"].append(float(p.truth in order[:3]))
            out[name]["pt"].append(max(sc.get(p.truth, 0.0), 1e-6))
            out[name]["boundary"].append(float(p.boundary))
    return {k: {kk: np.array(vv) for kk, vv in d.items()} for k, d in out.items()}


def _sums(a: dict[str, np.ndarray], mask: np.ndarray) -> np.ndarray:
    """Sufficient statistics of one person for one predictor: [n, hit1, hit3, brier, nll, bins(n, psum, correct) x N_BINS]."""
    p1, h1, h3, pt = a["p1"][mask], a["hit1"][mask], a["hit3"][mask], a["pt"][mask]
    b = np.minimum((p1 * N_BINS).astype(int), N_BINS - 1)
    bins = np.zeros((N_BINS, 3))
    for k in range(N_BINS):
        sel = b == k
        bins[k] = [sel.sum(), p1[sel].sum(), h1[sel].sum()]
    return np.concatenate([[mask.sum(), h1.sum(), h3.sum(), ((p1 - h1) ** 2).sum(), (-np.log(pt)).sum()], bins.ravel()])


def _metrics(S: np.ndarray) -> dict[str, float]:
    """From summed sufficient statistics (axis 0 already summed) to the metrics."""
    n = S[0]
    if n <= 0:
        return {k: float("nan") for k in ("top1", "top3", "brier", "ece", "nll")}
    bins = S[5:].reshape(N_BINS, 3)
    ece = float(sum(abs(b[1] / b[0] - b[2] / b[0]) * b[0] for b in bins if b[0] > 0) / n)
    return {"top1": S[1] / n, "top3": S[2] / n, "brier": S[3] / n, "ece": ece, "nll": S[4] / n}


def _interval(per_person: np.ndarray, n_boot: int, seed: int) -> dict[str, list[float | None]]:
    """Bootstrap over people of the pooled metrics; ``per_person`` is (people, stats)."""
    rng = np.random.default_rng(seed)
    P = per_person.shape[0]
    draws = rng.integers(0, P, (n_boot, P))
    vals = {k: [] for k in ("top1", "top3", "brier", "ece", "nll")}
    for d in draws:
        m = _metrics(per_person[d].sum(0))
        for k in vals:
            vals[k].append(m[k])
    return {k: [round(float(x), 4) for x in np.nanquantile(v, [0.025, 0.975])] for k, v in vals.items()}


def _round(m: dict[str, float]) -> dict[str, float | None]:
    return {k: (None if v != v else round(float(v), 4)) for k, v in m.items()}


def evaluate_family(vocab: StepVocab, paths_by_person: dict[str, list[list[str]]], *, n_boot: int = 400, seed: int = 0,
                    train_extra: dict[str, list[list[str]]] | None = None) -> dict[str, Any]:
    """Leave-one-person-out over ``paths_by_person`` (``train_extra`` people are always in training and never scored)."""
    people = sorted(paths_by_person)
    per = {name: [] for name in PREDICTORS}
    per_boundary = {name: [] for name in PREDICTORS}
    cal: dict[str, list[list[float]]] = defaultdict(list)
    n_pos = n_bound = off = 0
    extra = [s for cases in (train_extra or {}).values() for s in cases]
    for held in people:
        train = [s for p in people if p != held for s in paths_by_person[p]] + extra
        models = _models(vocab, train)
        pos: list[Position] = []
        for s in paths_by_person[held]:
            ps, o = positions_of(vocab, s)
            pos += ps
            off += o
        n_pos += len(pos)
        n_bound += sum(p.boundary for p in pos)
        sc = _score_positions(models, pos)
        for name in PREDICTORS:
            allm = np.ones(len(pos), bool)
            bm = sc[name]["boundary"].astype(bool)
            per[name].append(_sums(sc[name], allm))
            per_boundary[name].append(_sums(sc[name], bm))
    out: dict[str, Any] = {"n_people": len(people), "n_positions": n_pos, "n_boundary_positions": n_bound, "off_policy_positions": off, "all": {}, "boundary": {}}
    for scope, store in (("all", per), ("boundary", per_boundary)):
        for name in PREDICTORS:
            arr = np.array(store[name])
            out[scope][name] = {"value": _round(_metrics(arr.sum(0))), "ci": _interval(arr, n_boot, seed + 1), "n": int(arr[:, 0].sum())}
    cue = np.array(per_boundary["cue"])
    bins = cue[:, 5:].reshape(len(people), N_BINS, 3).sum(0)
    out["calibration_boundary"] = [{"p_mean": round(float(b[1] / b[0]), 4), "freq": round(float(b[2] / b[0]), 4), "n": int(b[0])} for b in bins if b[0] > 0]
    # paired: cue minus bigram-only (same people drawn), boundary positions
    rng = np.random.default_rng(seed + 2)
    bg = np.array(per_boundary["bigram"])
    un = np.array(per_boundary["unigram"])
    draws = rng.integers(0, len(people), (n_boot, len(people)))
    diffs = {"top1_minus_bigram": [], "top1_minus_unigram": [], "brier_minus_bigram": []}
    for d in draws:
        c, b, u = _metrics(cue[d].sum(0)), _metrics(bg[d].sum(0)), _metrics(un[d].sum(0))
        diffs["top1_minus_bigram"].append(c["top1"] - b["top1"])
        diffs["top1_minus_unigram"].append(c["top1"] - u["top1"])
        diffs["brier_minus_bigram"].append(c["brier"] - b["brier"])
    out["paired_boundary"] = {k: {"value": round(float(np.mean(v)), 4), "ci": [round(float(x), 4) for x in np.quantile(v, [0.025, 0.975])]} for k, v in diffs.items()}
    return out


def cross_family(vocab: StepVocab, train: dict[str, list[list[str]]], test: dict[str, list[list[str]]], *, n_boot: int = 300, seed: int = 0) -> dict[str, Any]:
    """Fit on one family, score the other (every test person is held out of training by construction)."""
    models = _models(vocab, [s for cs in train.values() for s in cs])
    per = {name: [] for name in PREDICTORS}
    for p in sorted(test):
        pos = []
        for s in test[p]:
            pos += positions_of(vocab, s)[0]
        sc = _score_positions(models, pos)
        bm = sc["cue"]["boundary"].astype(bool)
        for name in PREDICTORS:
            per[name].append(_sums(sc[name], bm))
    return {name: {"value": _round(_metrics(np.array(per[name]).sum(0))), "ci": _interval(np.array(per[name]), n_boot, seed), "n": int(np.array(per[name])[:, 0].sum())}
            for name in PREDICTORS}


def evaluate_candidates(*, fast: bool = False, root: Path | str | None = None, seed: int = 0) -> dict[str, Any]:
    n_boot = 150 if fast else 400
    out: dict[str, Any] = {}
    benefits = get_vocab("benefits-processor")
    A = XD.apprentice_expert_paths(root)
    if not A:
        import tempfile

        from ..personas import apprentices

        with tempfile.TemporaryDirectory(prefix="cue-apprentices-") as td:
            apprentices.generate(Path(td))
            A = XD.apprentice_expert_paths(td)
    B = XD.sample_paths(benefits, n_people=15 if fast else 30, cases=3, seed=101 + seed)
    out["benefits_A_apprentices"] = evaluate_family(benefits, A, n_boot=n_boot, seed=seed)
    out["benefits_B_sampled"] = evaluate_family(benefits, B, n_boot=n_boot, seed=seed)
    out["benefits_A_to_B"] = cross_family(benefits, A, B, n_boot=n_boot, seed=seed)
    out["benefits_B_to_A"] = cross_family(benefits, B, A, n_boot=n_boot, seed=seed)
    for role in ("programmer", "data-analyst"):
        v = get_vocab(role)
        if v is not None:
            out[f"{role}_B_sampled"] = evaluate_family(v, XD.sample_paths(v, n_people=15 if fast else 30, cases=3, seed=202 + seed), n_boot=n_boot, seed=seed)
    n_people = sum(r["n_people"] for r in out.values() if isinstance(r, dict) and "n_people" in r)
    out["meta"] = analytic_meta("synthetic", n_people, "personas", "leave-one-person-out over experts; cluster bootstrap over people (95%)",
                                note="Expert paths are synthetic: 8 scripted apprentice experts (two orderings) and experts sampled from the pack's own order rules.")
    out["limitations"] = [
        "Family A has two orderings and 8 people, so top-1 accuracy at boundaries is bounded by how often the held-out person used the rarer ordering; the interval is wide.",
        "Family B is written from the pack's order rules, so the rules cannot lose on it. It shows spread, not that the rules are right.",
        "These are expert paths from a generator; real experts will do things neither family contains.",
    ]
    return out
