"""Step-level checkpoint of one household run (REQ-7 LH-2): a run that was stopped, killed or crashed resumes from where it was,
not from the start of the household.

The file is typed. It holds ids (run, household, calculator reference, case-note id, approval-queue id), enums (stage, state),
counts (steps), the three TYPED outputs of a calculator whose result code verified (the amount as a number, eligible as a bool, the
reference as an id) and one `WorkingMemory.snapshot()` per navigator (itself ids, enums and counts). It holds NO household fact value,
NO page text, NO control name, NO model word and NO cliff text. `load` validates every field and refuses anything else, so a file
edited by hand (or by a page that somehow reached it) cannot carry text into a later prompt.

What a resume can and cannot skip (honest limits): a calculator whose result was verified is not run again (its three typed outputs
are rebuilt as a `ResultFields`; the amount text and status wording are rebuilt from the number and the flag with the site's own formatters, so
they read exactly as the page showed them); a calculator that was mid-form restarts on a fresh page (a killed browser keeps no form), but
with its step counter, its verified list and its working memory restored (`mark_resumed`: nothing is assumed about the page, every
handle is pending again); a saved case-note draft is never saved twice (the checkpoint holds its id); a run that already reached the
approval gate is not gated again (its queue id is in the file). The run never presses Submit, resumed or not.
"""
from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .completion import NOTE_ID_RE, REF_RE, ResultFields
from .context.working import ID_RE, TypedIdError, WorkingMemory

CHECKPOINT_VERSION = 1
STAGES = ("start", "navigators", "verified", "reconciled", "note_saved", "gated")
CALC_STATES = ("pending", "running", "done", "escalated")
SITES = ("a", "b", "c")
_QUEUE_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,60}$")


class CheckpointError(ValueError):
    """A checkpoint file is not what `save` writes. The message never contains the offending value."""


def _id(v: Any, what: str, *, allow_empty: bool = True) -> str:
    if v == "" and allow_empty:
        return ""
    if not isinstance(v, str) or not ID_RE.match(v):
        raise CheckpointError(f"{what} is not a short id")
    return v


def calc_result(amount: float, eligible: bool, site: str, ref: str) -> ResultFields:
    """The calculator's typed outputs as a `ResultFields`. The two wordings are rebuilt from the number and the flag with the site's
    own formatters, so they read exactly as the page showed them."""
    from .sandbox_sites.sites import display_wording

    amount_text, status_text = display_wording(site, float(amount), bool(eligible))
    return ResultFields(site=site, amount_text=amount_text, amount=float(amount), status_text=status_text,
                        eligible=bool(eligible), ref=ref)


@dataclass
class CalcProgress:
    state: str = "pending"                  # pending | running | done | escalated
    steps: int = 0                          # navigator steps written so far (the next resume numbers its steps from here)
    ref: str = ""                           # the quote reference, once the result was verified by code
    amount: float | None = None             # typed outputs of a verified result (a number and a flag), never the displayed words
    eligible: bool | None = None
    cliff: bool = False                     # the cliff check was done (the panel's text is never kept)
    wm: dict[str, Any] | None = None        # WorkingMemory.snapshot()

    def to_json(self) -> dict[str, Any]:
        return {"state": self.state, "steps": self.steps, "ref": self.ref, "amount": self.amount, "eligible": self.eligible,
                "cliff": self.cliff, "wm": self.wm}

    @classmethod
    def from_json(cls, d: Any) -> "CalcProgress":
        if not isinstance(d, dict) or d.get("state") not in CALC_STATES:
            raise CheckpointError("bad calculator progress")
        steps = d.get("steps", 0)
        if not isinstance(steps, int) or isinstance(steps, bool) or steps < 0:
            raise CheckpointError("steps must be a count")
        ref = d.get("ref", "")
        if ref != "" and not (isinstance(ref, str) and REF_RE.fullmatch(ref)):
            raise CheckpointError("ref is not a quote reference")
        amount, elig = d.get("amount"), d.get("eligible")
        if amount is not None and (isinstance(amount, bool) or not isinstance(amount, (int, float)) or not 0 <= amount < 1e7):
            raise CheckpointError("amount is not a number")
        if elig is not None and not isinstance(elig, bool):
            raise CheckpointError("eligible is not a flag")
        if d["state"] == "done" and (not ref or amount is None or elig is None):
            raise CheckpointError("a done calculator needs its three typed outputs")
        wm = d.get("wm")
        if wm is not None:
            try:
                WorkingMemory.restore(wm)                      # validates every id in the snapshot
            except (TypedIdError, ValueError, KeyError, TypeError) as exc:
                raise CheckpointError("bad working-memory snapshot") from exc
        return cls(d["state"], steps, ref, None if amount is None else float(amount), elig, bool(d.get("cliff", False)), wm)


@dataclass
class RunCheckpoint:
    run_id: str
    household: str
    stage: str = "start"
    calcs: dict[str, CalcProgress] = field(default_factory=lambda: {s: CalcProgress() for s in SITES})
    note_id: str = ""
    queue_id: str = ""
    resumed: int = 0
    scribe_steps: int = 0
    updated: float = 0.0

    # ------------------------------------------------------------------ typed validation
    def to_json(self) -> dict[str, Any]:
        return {"v": CHECKPOINT_VERSION, "run_id": self.run_id, "household": self.household, "stage": self.stage,
                "calcs": {s: c.to_json() for s, c in self.calcs.items()}, "note_id": self.note_id, "queue_id": self.queue_id,
                "resumed": self.resumed, "scribe_steps": self.scribe_steps, "updated": self.updated}

    @classmethod
    def from_json(cls, d: Any) -> "RunCheckpoint":
        if not isinstance(d, dict) or d.get("v") != CHECKPOINT_VERSION:
            raise CheckpointError("not a checkpoint of this version")
        stage = d.get("stage")
        if stage not in STAGES:
            raise CheckpointError("bad stage")
        calcs_in = d.get("calcs")
        if not isinstance(calcs_in, dict) or set(calcs_in) != set(SITES):
            raise CheckpointError("calculators must be a, b and c")
        note_id, queue_id = d.get("note_id", ""), d.get("queue_id", "")
        if note_id != "" and not (isinstance(note_id, str) and NOTE_ID_RE.fullmatch(note_id)):
            raise CheckpointError("note id is not a note id")
        if queue_id != "" and not (isinstance(queue_id, str) and _QUEUE_ID_RE.fullmatch(queue_id)):
            raise CheckpointError("queue id is not an id")
        resumed, ss = d.get("resumed", 0), d.get("scribe_steps", 0)
        if not all(isinstance(x, int) and not isinstance(x, bool) and x >= 0 for x in (resumed, ss)):
            raise CheckpointError("counts must be counts")
        return cls(_id(d.get("run_id"), "run id", allow_empty=False), _id(d.get("household"), "household", allow_empty=False), stage,
                   {s: CalcProgress.from_json(c) for s, c in calcs_in.items()}, note_id, queue_id, resumed, ss, float(d.get("updated", 0.0)))

    # ------------------------------------------------------------------ files
    def save(self, path: Path) -> None:
        """Atomic: write beside the file, then rename, so a kill mid-write leaves the previous checkpoint intact."""
        self.updated = round(time.time(), 3)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(f".{os.getpid()}.tmp")
        tmp.write_text(json.dumps(self.to_json(), separators=(",", ":")), encoding="utf-8")
        os.replace(tmp, path)

    @classmethod
    def load(cls, path: Path) -> "RunCheckpoint | None":
        """None when there is no file. A file that is not a valid checkpoint raises `CheckpointError` (never silently ignored:
        a run must not start from nothing on top of a file it could not read)."""
        try:
            raw = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        try:
            return cls.from_json(json.loads(raw))
        except json.JSONDecodeError as exc:
            raise CheckpointError("the checkpoint is not valid JSON") from exc

    # ------------------------------------------------------------------ writers (all typed)
    def set_stage(self, stage: str) -> None:
        if stage not in STAGES:
            raise CheckpointError("bad stage")
        if STAGES.index(stage) >= STAGES.index(self.stage):
            self.stage = stage

    def calc_done(self, site: str, r: ResultFields, *, steps: int, wm: dict[str, Any] | None) -> None:
        self.calcs[site] = CalcProgress("done", steps, r.ref, float(r.amount), bool(r.eligible), self.calcs[site].cliff, wm)

    def finished_results(self) -> dict[str, ResultFields]:
        return {s: calc_result(float(c.amount), bool(c.eligible), s, c.ref) for s, c in self.calcs.items() if c.state == "done"
                and c.amount is not None and c.eligible is not None}
