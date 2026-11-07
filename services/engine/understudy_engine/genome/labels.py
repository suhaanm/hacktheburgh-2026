"""Name the gaps: turn alignment columns into waterfall bars (behaviours) and, for the benefits pack, deficits."""
from __future__ import annotations

from collections import defaultdict

from .align import Alignment, Column

PACE = "Slower on shared steps"
PAUSES = "Long pauses"
SEARCH_LOOPS = "Search loops"
REPEATED_READS = "Repeated reads"
MISSED_CHECK = "Missed check, redone"
WRONG_COPY = "Wrong figure, copied again"
REWORK = "Rework"
SKIPPED = "Skipped steps"
OTHER_EXTRA = "Other extra steps"

LABEL_ORDER = (PACE, PAUSES, SEARCH_LOOPS, REPEATED_READS, MISSED_CHECK, WRONG_COPY, REWORK, SKIPPED, OTHER_EXTRA)

# Waterfall bar -> the benefits-pack deficit it points at (the planted ones in personas/apprentices.py).
DEFICIT_OF_LABEL = {
    PAUSES: "idle_before_enter",
    SEARCH_LOOPS: "search_loop",
    REPEATED_READS: "repeated_read_result",
    MISSED_CHECK: "skipped_check_cliff",
    WRONG_COPY: "copy_error",
}

READ_FAMILY = {"READ", "READ_RESULT"}
SEARCH_FAMILY = {"SEARCH", "REFORMULATE"}
REDO_ENTER = {"ENTER_HOUSEHOLD", "CHECK_CLIFF"}
REDO_COPY = {"COPY_TO_NOTE", "RECONCILE"}


def _blocks(cols: list[Column]) -> list[list[int]]:
    """Maximal runs of consecutive columns that are not exact matches (gaps and mismatches)."""
    out: list[list[int]] = []
    cur: list[int] = []
    for k, c in enumerate(cols):
        if c.op != "match":
            cur.append(k)
        elif cur:
            out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    return out


def label_columns(al: Alignment) -> list[str]:
    cols = al.columns
    labels = [PACE] * len(cols)
    rework_cogs: set[str] = set()
    for block in _blocks(cols):
        extras = [cols[k].cog_novice for k in block if cols[k].op == "gap_expert"]
        contents = {c for k in block for c in (cols[k].cog_novice, cols[k].cog_expert) if c}
        novice_side = {cols[k].cog_novice for k in block if cols[k].cog_novice}
        has_revert = "REVERT" in extras
        if has_revert and novice_side & REDO_ENTER:
            rework_label = MISSED_CHECK
        elif has_revert and novice_side & REDO_COPY:
            rework_label = WRONG_COPY
        elif has_revert:
            rework_label = REWORK
        else:
            rework_label = None
        for k in block:
            c = cols[k]
            cog = c.cog_novice or c.cog_expert
            if c.op == "mismatch":
                labels[k] = rework_label or (SEARCH_LOOPS if contents & SEARCH_FAMILY else PACE)
                if rework_label == MISSED_CHECK and c.cog_novice:
                    rework_cogs.add(c.cog_novice)
            elif cog == "IDLE" and c.op == "gap_expert":
                labels[k] = PAUSES
            elif rework_label is not None and c.op == "gap_expert":
                labels[k] = rework_label
                if rework_label == MISSED_CHECK:
                    rework_cogs.add(cog)
            elif contents & SEARCH_FAMILY and c.op == "gap_expert":
                labels[k] = SEARCH_LOOPS
            elif c.op == "gap_expert" and cog in READ_FAMILY:
                labels[k] = REPEATED_READS
            elif c.op == "gap_novice":
                labels[k] = SKIPPED
            else:
                labels[k] = OTHER_EXTRA
    # a skipped step that the same trace redoes later is part of the same deficit (net price = rework minus the skipped time)
    if rework_cogs:
        for k, c in enumerate(cols):
            if c.op == "gap_novice" and labels[k] == SKIPPED and c.cog_expert in rework_cogs:
                labels[k] = MISSED_CHECK
    return labels


def components(al: Alignment) -> dict[str, float]:
    """Seconds per waterfall bar for one aligned trace. Sums to ``al.gap_s``."""
    out: dict[str, float] = defaultdict(float)
    for lab, col in zip(label_columns(al), al.columns):
        out[lab] += col.seconds
    return dict(out)


def deficit_prices(comp: dict[str, float]) -> dict[str, float]:
    """Waterfall bars that name a benefits deficit, as ``{deficit: seconds}``."""
    return {DEFICIT_OF_LABEL[lab]: s for lab, s in comp.items() if lab in DEFICIT_OF_LABEL}
