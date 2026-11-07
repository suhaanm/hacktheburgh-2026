"""The v1 data as one more "family" for the matrix: personas (hazard, routines) and apprentices (genome).

The v1 generators are run with their own seeds into a temporary directory and are never modified. Only the owners' public
loaders are used to read them back.
"""
from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from ..core import Episode


@dataclass
class V1Data:
    persona_eps: dict[str, list[Episode]]            # person -> episodes (pack mapping)
    persona_labels: dict[str, dict[str, str]]        # person -> task_id -> routine name (absent = adhoc)
    planted: dict[str, list[tuple[float, float]]]
    cohort: object                                   # genome.Cohort of the apprentices (8 experts, 16 novices, 2 cases each)
    truth: dict
    root: Path = field(default=None)                 # type: ignore[assignment]


def load_v1(root: Path | None = None) -> V1Data:
    from ..genome import GenomeService
    from ..genome.service import TASK
    from ..hazard.data import load_persona_episodes
    from ..personas import PERSONAS, apprentices, write_persona
    from ..routines.evaluate import persona_episodes
    from ..store import EventStore

    if root is None:
        root = Path(tempfile.mkdtemp(prefix="realism_v1_"))
    for spec in PERSONAS:
        write_persona(spec, root, with_mc=False)
    apprentices.generate(root)
    eps_by: dict[str, list[Episode]] = {}
    labels_by: dict[str, dict[str, str]] = {}
    for spec in PERSONAS:
        eps, labels, truth = persona_episodes(spec.slug, root)
        eps_by[truth["person"]] = eps
        labels_by[truth["person"]] = labels
    _eps, planted, _info = load_persona_episodes(root)
    bundle = GenomeService(EventStore(root)).bundle(TASK, "synthetic")
    return V1Data(eps_by, labels_by, planted, bundle.cohort, bundle.truth, root)
