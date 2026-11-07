"""Genome graph (ANA-4 data for VIS-2): cog transitions for experts beside novices, and what the novice never takes."""
from __future__ import annotations

from collections import defaultdict
from typing import Sequence

from ..core import Episode

MISSING_RATIO = 0.85     # novice takes an edge less than this share as often as experts do ...
MIN_FREQ = 0.3           # ... and experts take it at least this often per episode


def _tally(eps: Sequence[Episode]):
    edges: dict[tuple[str, str], int] = defaultdict(int)
    dwell: dict[str, float] = defaultdict(float)
    for e in eps:
        for c in e.cogs:
            dwell[c.id] += c.dwell
        for a, b in zip(e.cogs, e.cogs[1:]):
            edges[(a.id, b.id)] += 1
    n = max(1, len(eps))
    return {k: v / n for k, v in edges.items()}, {k: v / n for k, v in dwell.items()}


def transition_graph(experts: Sequence[Episode], novices: Sequence[Episode], ratio: float = MISSING_RATIO, min_freq: float = MIN_FREQ) -> dict:
    """Nodes: cogs with mean seconds per case for each group. Edges: mean transitions per case for each group.

    ``missing_for_novice``: experts take the edge at least ``min_freq`` times per case and novices take it
    less than ``ratio`` times as often (never, in the limit). ``extra_for_novice`` is the mirror image.
    ``planted`` is left ``None``; the service fills it when it knows the ground truth.
    """
    ef, ed = _tally(experts)
    nf, nd = _tally(novices)
    cogs = sorted(set(ed) | set(nd))
    nodes = [{"id": c, "cog": c, "expert_dwell_s": round(ed.get(c, 0.0), 3), "novice_dwell_s": round(nd.get(c, 0.0), 3)} for c in cogs]
    edges = []
    for (a, b) in sorted(set(ef) | set(nf)):
        e, n = ef.get((a, b), 0.0), nf.get((a, b), 0.0)
        edges.append({
            "from": a, "to": b, "expert_freq": round(e, 4), "novice_freq": round(n, 4),
            "missing_for_novice": bool(e >= min_freq and n < ratio * e),
            "extra_for_novice": bool(n >= min_freq and e < ratio * n),
            "planted": None,
        })
    return {"nodes": nodes, "edges": edges}


def diff(experts: Sequence[Episode], novices: Sequence[Episode], **kw) -> list[tuple[str, str]]:
    """Edges the novices take much less than experts (``missing_for_novice``)."""
    g = transition_graph(experts, novices, **kw)
    return [(e["from"], e["to"]) for e in g["edges"] if e["missing_for_novice"]]
