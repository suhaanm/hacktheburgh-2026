"""Scripted programs for the programmer workbench: lists of step tuples in the ``programs_util`` vocabulary (click / fill / replace / select by
a needle of a control's label). Pure and deterministic. Used by the sandbox tests, the expert recordings and the fake participants.

Styles: ``expert`` (the full discipline: reads the failure, looks at the inputs, writes the failing test first where the task needs one, fixes
completely, re-runs, probes the edges in the console, reviews the diff, stages only the fix, commits with a message that says what changed, marks
done; ``variation`` 0..3 permutes the allowed orders), ``skipper`` (the tempting path: the naive fix, run tests, commit everything, a generic message,
mark done; never opens the inputs, never probes, never reads the diff, never writes a test first) and ``claimer`` (presses Mark done without fixing).
"""
from __future__ import annotations

from .page import LABELS
from .tasks import TASKS, names_of, naive, reference, src_paths, test_path

PROBES: dict[tuple[str, int], list[str]] = {
    ("p-boundary-1", 1): ["pageCount(9, 3)", "pageCount(0, 3)"], ("p-boundary-1", 2): ["rowsNeeded(8, 4)", "rowsNeeded(0, 4)"],
    ("p-boundary-2", 1): ["inRange(1, 1, 5)", "inRange(5, 5, 5)"], ("p-boundary-2", 2): ["isWithinWindow(0, 0, 60)", "isWithinWindow(30, 30, 30)"],
    ("p-missing-1", 1): ["average([])", "average([1, undefined, 3])"], ("p-missing-1", 2): ["averageRating([])", "averageRating([{ stars: 4 }, {}])"],
    ("p-missing-2", 1): ["displayName(null)", "displayName({ id: 5 })"], ("p-missing-2", 2): ["shippingCity(null)", "shippingCity({ id: 5 })"],
    ("p-discipline-1", 1): ["slugify('a   b    c')", "slugify('')"], ("p-discipline-1", 2): ["formatPrice(50)", "formatPrice(0)"],
    ("p-discipline-2", 1): ["greeting('Ada', 11)", "greeting('Ada', 0)"], ("p-discipline-2", 2): ["isSenior(64)", "isSenior(0)"],
}
MESSAGES: dict[tuple[str, int], str] = {
    ("p-boundary-1", 1): "Fix pageCount: round up so exact multiples and empty lists are right",
    ("p-boundary-1", 2): "Fix rowsNeeded: round up so full rows and empty albums are right",
    ("p-boundary-2", 1): "Fix inRange: include both ends of the band",
    ("p-boundary-2", 2): "Fix isWithinWindow: include opening and closing minute",
    ("p-missing-1", 1): "Fix average: ignore missing values and return 0 for an empty list",
    ("p-missing-1", 2): "Fix averageRating: ignore unrated reviews and return 0 when none",
    ("p-missing-2", 1): "Fix displayName: fall back to email then Guest when profile is missing",
    ("p-missing-2", 2): "Fix shippingCity: fall back to billing city then Unknown",
    ("p-discipline-1", 1): "Fix slugify double hyphens and add a regression test for repeated spaces",
    ("p-discipline-1", 2): "Fix formatPrice to always show two decimals and add a regression test",
    ("p-discipline-2", 1): "Fix greeting at noon: 12 is the afternoon",
    ("p-discipline-2", 2): "Fix isSenior boundary: 65 year olds get the senior fare",
}
NEW_TESTS: dict[tuple[str, int], str] = {
    ("p-discipline-1", 1): "\ntest('repeated spaces collapse to one hyphen', () => {\n  assertEqual(slugify('Hello  World'), 'hello-world');\n});\n",
    ("p-discipline-1", 2): "\ntest('whole pounds show two decimals', () => {\n  assertEqual(formatPrice(500), '£5.00');\n});\n",
}


def _ax(task_id: str, variant: int):
    t = TASKS[task_id]
    return t, t.variants[variant]


def _fix_steps(task_id: str, variant: int, files: dict[str, str]) -> list[tuple]:
    steps: list[tuple] = []
    for path, content in files.items():
        steps += [("click", path), ("fill", "editor", content)]
    return steps


def _segments(task_id: str, variant: int, L: dict[str, str], *, style: str) -> dict[str, list[tuple]]:
    t, v = _ax(task_id, variant)
    sp = src_paths(task_id, variant)
    tp = test_path(task_id, variant)
    seg: dict[str, list[tuple]] = {}
    seg["T"] = [("click", L["run"])]                                       # run the tests: the failure
    seg["I"] = [("click", L["inputs"])]                                    # sample inputs
    seg["K"] = [("click", L["docs"])]                                      # a glance at the docs
    seg["O"] = [("click", sp[0])]                                          # read the source file
    if t.kind == "test_first":
        old = v.files[tp]
        seg["W"] = [("click", tp), ("fill", "editor", old.rstrip("\n") + "\n" + NEW_TESTS[(task_id, variant)]), ("click", L["run"])]
    ref = reference(task_id, variant)
    seg["F"] = _fix_steps(task_id, variant, ref if style == "expert" else naive(task_id, variant))
    seg["R"] = [("click", L["run"])]
    seg["P"] = [s for expr in PROBES[(task_id, variant)] for s in (("fill", L["probe"], expr), ("click", L["probeRun"]))]
    seg["D"] = [("click", L["diff"])]
    changed_for_commit = list(sp) + ([tp] if t.kind == "test_first" else [])
    seg["S"] = [("click", f"Stage {p}") for p in changed_for_commit]
    seg["C"] = [("fill", L["message"], MESSAGES[(task_id, variant)]), ("click", L["commit"])]
    seg["N"] = [("click", L["done"])]
    return seg


ORDERS = {
    0: "T I O W F R P D S C N",
    1: "O T I W F R D P S C N",
    2: "T O I K W F P R D S C N",
    3: "T I O W F R P S D C N",
}


def program(task_id: str, variant: int, style: str, *, variation: int = 0, layout: str = "v1") -> list[tuple]:
    """The step list for one case. See the module docstring for the styles."""
    t, v = _ax(task_id, variant)
    L = LABELS[layout]
    if style == "claimer":
        return [("click", L["done"])]
    if style == "skipper":
        sp = src_paths(task_id, variant)
        steps: list[tuple] = [("click", L["run"])]
        steps += _fix_steps(task_id, variant, naive(task_id, variant))
        steps += [("click", L["run"])]
        every_changed = list(sp) + list(v.head_overrides)               # the tempting "stage everything"
        steps += [("click", f"Stage {p}") for p in every_changed]
        steps += [("fill", L["message"], "fix"), ("click", L["commit"]), ("click", L["done"])]
        return steps
    if style != "expert":
        raise ValueError(f"unknown style {style!r}")
    seg = _segments(task_id, variant, L, style="expert")
    out: list[tuple] = []
    for key in ORDERS[variation % 4].split():
        if key == "I" and t.kind == "boundary":                        # the boundary tasks do not need the inputs panel
            continue
        if key == "W" and t.kind != "test_first":
            continue
        if key == "K" and variation % 4 != 2:
            continue
        out += seg[key]
    return out


def snippets(task_id: str, variant: int, layout: str = "v1") -> dict[str, list[tuple]]:
    """Step lists a fake participant inserts when the coach prompt for that step arrives."""
    t, v = _ax(task_id, variant)
    L = LABELS[layout]
    seg = _segments(task_id, variant, L, style="expert")
    return {"probe_edges": seg["P"], "inspect_inputs": seg["I"], "review_diff": seg["D"],
            "write_failing_test": seg.get("W", []), "read_trace_first": seg["T"]}
