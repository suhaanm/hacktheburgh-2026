"""Next-step candidates (CUE-1): the top three steps an expert would take next, from the expert transition counts and the pack's
order rules. A path prior, not a guess by a language model.

Two parts, both plain counting and code:

1. **Smoothed n-gram over expert cogs.** For a history ``h`` of cogs (the last ``k``), ``P(c | h)`` is a Dirichlet-style backoff: the
   order-j estimate adds ``beta`` pseudo-counts spread by the order-(j-1) estimate, down to an additive-smoothed unigram. Sparse
   contexts therefore fall back to shorter ones instead of getting probability zero. The end of the episode is a token of its own.
2. **Pack order rules as a mask.** ``coach.steps.StepPolicy.track`` runs on the history. Only cogs that would continue the step in
   progress, or start a step whose prerequisites are all done (``next_ready``), are candidates. The probabilities of the allowed
   cogs are renormalised, so the numbers mean "given that the next thing is a step the pack allows". Interchangeable steps (the
   three calculators) are one candidate: its id is the first one not started yet, its ``group`` the representative.

A cog that would start nothing the pack knows (an idle spell, a revert) is not a candidate: the prior says nothing about it.
"""
from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from pathlib import Path

from ..core import Cog
from .types import Candidate
from .vocab import StepVocab

START, END = "<s>", "</s>"
DEFAULT_K, DEFAULT_BETA, DEFAULT_ALPHA = 3, 2.0, 0.1
INTENT_WEIGHT = 3.0         # a question answer is a strong label: worth three observed expert transitions


def _matched(pattern: Sequence[str], history: Sequence[str], start: int) -> int:
    """How many cogs of ``pattern`` the history matches from index ``start`` (the same walk ``StepPolicy.track`` does)."""
    pos = 0
    for c in history[start:]:
        if pos < len(pattern) and c == pattern[pos]:
            pos += 1
        elif pos > 0 and c == pattern[0]:
            pos = 1
    return pos


def enabled_cogs(vocab: StepVocab, history: Sequence[str]) -> dict[str, tuple[str, bool]]:
    """``{cog: (step id, in_progress)}`` for every cog the pack allows next after ``history``.

    The step in progress claims its next cog first; then, in policy order, each step that is ready and not yet started claims its
    first cog (the first of an interchangeable group wins, so the next calculator is the first one not started). A cog already
    claimed is not claimed again."""
    policy = vocab.policy
    cogs = [Cog(float(i), float(i + 1), c) for i, c in enumerate(history)]
    prog = policy.track(cogs)
    out: dict[str, tuple[str, bool]] = {}
    for sid, occ in prog.occurrences.items():
        if occ.complete:
            continue
        pat = policy.steps[sid].cogs
        m = _matched(pat, history, occ.start)
        if 0 < m < len(pat):
            out.setdefault(pat[m], (sid, True))
    for sid in policy.next_ready(prog):
        if sid in prog.occurrences:
            continue
        first = policy.steps[sid].cogs[0]
        out.setdefault(first, (sid, False))
    return out


class NextStepModel:
    """Counts on expert cog sequences plus the pack vocabulary. ``fit`` once, ``candidates`` many times; ``clone`` for a person's
    own copy (question answers add pseudo-counts to the clone only)."""

    def __init__(self, vocab: StepVocab, k: int = DEFAULT_K, beta: float = DEFAULT_BETA, alpha: float = DEFAULT_ALPHA) -> None:
        self.vocab, self.k, self.beta, self.alpha = vocab, int(k), float(beta), float(alpha)
        self.counts: list[dict[tuple, Counter]] = [defaultdict(Counter) for _ in range(self.k + 1)]
        self.V: set[str] = {END} | {c for s in vocab.policy.steps.values() for c in s.cogs}
        self.n_sequences = 0

    # ---------------------------------------------------------------- fitting
    def _ctx(self, history: Sequence[str], j: int) -> tuple:
        if j == 0:
            return ()
        padded = [START] * j + list(history)
        return tuple(padded[-j:])

    def _add(self, history: Sequence[str], cog: str, w: float = 1.0) -> None:
        self.V.add(cog)
        for j in range(self.k + 1):
            self.counts[j][self._ctx(history, j)][cog] += w

    def fit(self, sequences: Iterable[Sequence[str]]) -> "NextStepModel":
        for seq in sequences:
            seq = list(seq)
            for i, c in enumerate(seq):
                self._add(seq[:i], c)
            self._add(seq, END)
            self.n_sequences += 1
        return self

    def observe_intent(self, history: Sequence[str], step_id: str, weight: float = INTENT_WEIGHT) -> bool:
        """A question answer: the worker said this step is next, from this history. Adds pseudo-counts for the step's next cog."""
        em = enabled_cogs(self.vocab, history)
        for cog, (sid, _) in em.items():
            if sid == step_id or self.vocab.group(sid) == self.vocab.group(step_id):
                self._add(history, cog, weight)
                return True
        return False

    def clone(self) -> "NextStepModel":
        m = NextStepModel(self.vocab, self.k, self.beta, self.alpha)
        m.V = set(self.V)
        m.n_sequences = self.n_sequences
        m.counts = [defaultdict(Counter, {ctx: Counter(c) for ctx, c in lvl.items()}) for lvl in self.counts]
        return m

    # ---------------------------------------------------------------- probabilities
    def p_cog(self, history: Sequence[str]) -> dict[str, float]:
        """Backoff probability of every cog in the vocabulary after ``history`` (sums to 1)."""
        V = sorted(self.V)
        uni = self.counts[0][()]
        total = sum(uni.values())
        den = total + self.alpha * len(V)
        p = {c: (uni.get(c, 0.0) + self.alpha) / den for c in V}
        for j in range(1, self.k + 1):
            cnt = self.counts[j].get(self._ctx(history, j))
            if not cnt:
                continue                        # unseen context: keep the lower order
            n = sum(cnt.values())
            p = {c: (cnt.get(c, 0.0) + self.beta * p[c]) / (n + self.beta) for c in V}
        return p

    def candidates(self, history: Sequence[str], top: int = 3) -> tuple[list[Candidate], float]:
        """The top candidates after ``history`` and the share of the model's mass that fell on allowed cogs (a diagnostic)."""
        em = enabled_cogs(self.vocab, history)
        if not em:
            return [], 0.0
        p = self.p_cog(history)
        mass = sum(p.get(c, 0.0) for c in em)
        order = {sid: i for i, sid in enumerate(self.vocab.policy.order)}
        rows = []
        for cog, (sid, prog) in em.items():
            q = p.get(cog, 0.0) / mass if mass > 1e-12 else 1.0 / len(em)
            rows.append((q, sid, prog))
        rows.sort(key=lambda r: (-r[0], order.get(r[1], 0)))
        out = []
        for q, sid, prog in rows[:top]:
            v = self.vocab
            out.append(Candidate(id=sid, group=v.group(sid), label=v.label(sid), p=float(q), skill=v.skill(sid),
                                 reason_id=v.reason_id(sid), cogs=v.cogs(sid), in_progress=prog))
        return out, float(mass)

    def group_scores(self, history: Sequence[str], rules: bool = True) -> dict[str, float]:
        """A distribution over group representatives, for the evaluation. ``rules=False`` ignores the pack's order rules (the
        ablation and the baselines): a group scores the best probability of any of its cogs."""
        v = self.vocab
        reps = [sid for sid in v.policy.order if v.group(sid) == sid]
        if rules:
            cands, _ = self.candidates(history, top=len(v.policy.order))
            sc = {r: 0.0 for r in reps}
            for c in cands:
                sc[c.group] = max(sc[c.group], c.p)
            tot = sum(sc.values())
            return {r: (s / tot if tot > 0 else 1.0 / len(reps)) for r, s in sc.items()}
        p = self.p_cog(history)
        sc = {r: max((p.get(c, 0.0) for c in v.policy.steps[r].cogs), default=0.0) for r in reps}
        tot = sum(sc.values())
        return {r: (s / tot if tot > 0 else 1.0 / len(reps)) for r, s in sc.items()}

    # ---------------------------------------------------------------- persistence of a person's answers
    def intents_line(self, history: Sequence[str], step_id: str, weight: float = INTENT_WEIGHT) -> dict:
        return {"ctx": list(history)[-self.k:], "step": step_id, "w": weight}


def apply_intents(model: NextStepModel, path: Path, person: str) -> int:
    """Replay a person's stored answers onto a clone. The file holds cog ids and step ids only (pack vocabulary)."""
    n = 0
    if not path.is_file():
        return 0
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("person") == person and isinstance(row.get("ctx"), list) and isinstance(row.get("step"), str):
            n += int(model.observe_intent([str(c) for c in row["ctx"]], row["step"], float(row.get("w", INTENT_WEIGHT))))
    return n


def margin_of(cands: Sequence[Candidate]) -> float:
    if not cands:
        return 0.0
    if len(cands) == 1:
        return float(cands[0].p)
    return float(cands[0].p - cands[1].p)


def nll(p_true: float, floor: float = 1e-6) -> float:
    return -math.log(max(p_true, floor))
