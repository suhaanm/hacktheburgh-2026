"""The three roles: cog vocabulary, task grammar, timing tables, event emission tables, deficits and routines.

Benefits processor is the deep role (the five deficits of the pack, the entitlement-check expert policy). Data analyst
and programmer are thin: their pack cogs, a short task, and the two deficits their pack's ``persona.yaml`` names.

The timing tables start from each pack's ``persona.yaml`` (expert medians and sigmas) and fall back to the v1
vocabulary for base cogs. The KLM table gives mean operator counts per cog for the bottom-up family.
Nothing here is a claim about real casework: these are the shapes the generators need.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

from ..personas.apprentices import DEFICITS as BENEFITS_DEFICITS
from ..personas.vocab import BASE_DWELL, LABELS as BENEFITS_LABELS, SITES
from .core import Step, Unit, choose

BENEFITS, ANALYST, PROGRAMMER = "benefits-processor", "data-analyst", "programmer"
ROLE_ALIASES = {
    "benefits": BENEFITS, "benefits-processor": BENEFITS, "benefits_processor": BENEFITS,
    "analyst": ANALYST, "data-analyst": ANALYST, "data_analyst": ANALYST,
    "programmer": PROGRAMMER,
}


@dataclass(frozen=True)
class Emit:
    """How one cog looks as events. ``kind`` selects the emitter branch; the rest are enum tokens."""

    kind: str                        # ticks | single | search | reformulate | nav | copy_note | none | undo
    types: tuple[str, ...] = ()
    zone: str | None = None
    role: str | None = None
    source: str = "browser"
    first: str | None = None         # forced type of the first event (a focus opens a new segment)
    rest: tuple[str, ...] | None = None
    site: bool = False


@dataclass(frozen=True)
class DeficitSpec:
    id: str
    kind: str                        # omit | repeat | loop | freeze | copy
    cog: str                         # the cog whose step triggers the behaviour
    rework: tuple[str, ...] = ()
    skill: str = ""
    param: str = ""                  # hyper key giving the probability or mean at zero mastery
    doc: str = ""


@dataclass(frozen=True)
class RoutineT:
    id: str
    head: tuple[str, ...] = ()
    group: tuple[str, ...] = ()
    tail: tuple[str, ...] = ()
    k: tuple[int, int] = (1, 1)
    sites: bool = False              # the group's OPEN_CALCULATOR steps cycle through the three calculators


@dataclass
class RoleSpec:
    id: str
    slug: str
    cogs: tuple[str, ...]
    dwell: dict[str, tuple[float, float]]               # expert median seconds, log-sigma
    klm: dict[str, dict[str, float]]                    # mean operator counts and response time
    emit: dict[str, Emit]
    zones: tuple[str, ...]                              # for wrong-zone noise
    labels: dict[str, list[str]]
    act_class: dict[str, str]
    units: tuple[Unit, ...]
    deficits: tuple[DeficitSpec, ...]
    deficit_types: dict[str, dict]
    routines: tuple[RoutineT, ...]
    detour_cogs: tuple[str, ...]
    pool: tuple[str, ...]
    strategy_dims: dict[str, tuple[str, ...]]
    sites: dict[str, str] = field(default_factory=dict)
    complexity_cog: str | None = None

    def deficit(self, did: str) -> DeficitSpec:
        return next(d for d in self.deficits if d.id == did)

    def deficit_for_cog(self, cog: str) -> list[DeficitSpec]:
        return [d for d in self.deficits if d.cog == cog]

    # ------------------------------------------------------------------ the grammar
    def nominal(self, strategy: dict[str, str], rnd: random.Random) -> list[Step]:
        return _BUILDERS[self.id](self, strategy, rnd)

    def frontier_walk(self, rnd: random.Random, prefs: dict[str, float], p_optional: float = 0.35) -> list[Step]:
        """A random linear extension of the pack's partial order, steered by per-unit preference weights."""
        todo = [u for u in self.units if u.required or rnd.random() < p_optional]
        ids = {u.id for u in todo}
        done: set[str] = set()
        out: list[Step] = []
        while todo:
            ready = [u for u in todo if all(a in done or a not in ids for a in u.after)]
            u = choose(rnd, ready, [max(prefs.get(x.id, 1.0), 1e-3) for x in ready])
            out.extend(Step(s.cog, s.site, u.id) for s in u.steps)
            done.add(u.id)
            todo.remove(u)
        return out


# ------------------------------------------------------------------------------------------ emission tables
_COMMON_EMIT = {
    "IDLE": Emit("none"),
    "REVERT": Emit("undo"),
    "COPY": Emit("single", ("copy",), "doc", "document"),
    "PASTE": Emit("single", ("paste",), "doc", "textbox"),
    "SEARCH": Emit("search", ("scroll",), "search_box", "searchbox"),
    "REFORMULATE": Emit("reformulate", ("focus", "click"), "query_edit", "searchbox"),
    "NAVIGATE": Emit("nav", ("nav",), "page", "link"),
    "READ": Emit("ticks", ("scroll", "focus"), "doc", "document", first="focus", rest=("scroll",)),
    "ENTER": Emit("ticks", ("click", "focus"), "form_field", "textbox"),
    "COMPARE": Emit("ticks", ("tab", "click"), "compare_view", "tab"),
    "CHECK": Emit("ticks", ("click",), "check_box", "checkbox"),
    "DECIDE": Emit("ticks", ("click",), "decision_btn", "button"),
    "ASK": Emit("ticks", ("click",), "help", "button"),
}
_COMMON_LABELS = {
    "doc": ["case file", "guidance page", "letter"], "form_field": ["name field", "reference field", "date field", "notes field"],
    "search_box": ["search box"], "query_edit": ["search box"], "compare_view": ["left tab", "right tab"],
    "check_box": ["verified box", "eligibility box"], "decision_btn": ["confirm", "defer"], "help": ["help button", "guidance link"],
}

_BEN_EMIT = {
    **_COMMON_EMIT,
    "OPEN_CALCULATOR": Emit("single", ("nav",), "calc_site", "link", site=True),
    "ENTER_HOUSEHOLD": Emit("ticks", ("click", "focus"), "household_form", "textbox"),
    "READ_RESULT": Emit("ticks", ("scroll", "focus"), "calc_result", "region", first="focus", rest=("scroll",)),
    "CHECK_CLIFF": Emit("ticks", ("click", "scroll"), "cliff_panel", "button", first="focus", rest=("click", "scroll")),
    "RECONCILE": Emit("ticks", ("tab", "click"), "results_tabs", "tab"),
    "COPY_TO_NOTE": Emit("copy_note", (), "case_note", "textbox"),
}
_PRG_EMIT = {
    **_COMMON_EMIT,
    "READ_TRACE": Emit("ticks", ("scroll", "click", "focus"), "ci_log", "region"),
    "READ_CODE": Emit("ticks", ("scroll", "click", "focus"), "code_view", "region"),
    "EDIT_CODE": Emit("ticks", ("click", "focus"), "code_editor", "textbox"),
    "RUN_TESTS": Emit("single", ("click",), "test_runner", "button"),
    "REVIEW_DIFF": Emit("ticks", ("scroll", "click", "focus"), "diff_view", "region"),
    "COMMIT": Emit("ticks", ("click", "focus"), "commit_box", "textbox"),
    "SEARCH_DOCS": Emit("ticks", ("nav", "tab", "scroll", "click"), "docs_page", "link"),
}
_ANA_EMIT = {
    **_COMMON_EMIT,
    "LOAD_DATA": Emit("ticks", ("nav", "click", "focus"), "data_browser", "link"),
    "PROFILE_DATA": Emit("ticks", ("click", "focus", "scroll"), "profile_panel", "region"),
    "WRITE_QUERY": Emit("ticks", ("click", "focus"), "sql_editor", "textbox"),
    "RUN_QUERY": Emit("single", ("click",), "run_control", "button"),
    "INSPECT_RESULT": Emit("ticks", ("scroll", "focus", "click"), "query_result", "region"),
    "PLOT": Emit("ticks", ("click", "focus"), "chart_panel", "region"),
    "EXPORT_RESULT": Emit("single", ("click",), "export_panel", "button"),
}

_PRG_LABELS = {**_COMMON_LABELS, "ci_log": ["log pane", "failure summary"], "code_view": ["file view", "blob"], "code_editor": ["editor"],
               "test_runner": ["rerun button"], "diff_view": ["diff"], "commit_box": ["commit box"], "docs_page": ["docs page", "reference"]}
_ANA_LABELS = {**_COMMON_LABELS, "data_browser": ["table list", "schema"], "profile_panel": ["profile"], "sql_editor": ["editor"],
               "run_control": ["run button"], "query_result": ["result grid", "totals row"], "chart_panel": ["chart"], "export_panel": ["export"]}

# ------------------------------------------------------------------------------------------ timing tables
_BEN_DWELL = {  # from packages/packs/benefits-processor/persona.yaml where listed, else the v1 vocabulary
    "READ": (35, .30), "OPEN_CALCULATOR": (10, .35), "ENTER_HOUSEHOLD": (60, .25), "READ_RESULT": (25, .30), "CHECK_CLIFF": (45, .30),
    "RECONCILE": (60, .30), "COPY_TO_NOTE": (50, .25), "CHECK": (20, .30), "SEARCH": (14, .40), "REFORMULATE": (10, .40),
    "NAVIGATE": (4, .40), "REVERT": (6, .40), "IDLE": (12, .60),
    "ENTER": (BASE_DWELL["ENTER"], .35), "COPY": (BASE_DWELL["COPY"], .40), "PASTE": (BASE_DWELL["PASTE"], .40),
    "COMPARE": (BASE_DWELL["COMPARE"], .40), "DECIDE": (BASE_DWELL["DECIDE"], .40), "ASK": (BASE_DWELL["ASK"], .45),
}
_PRG_DWELL = {
    "READ_TRACE": (40, .40), "READ_CODE": (50, .45), "EDIT_CODE": (90, .50), "RUN_TESTS": (12, .40), "COMMIT": (15, .35),
    "SEARCH_DOCS": (35, .50), "REVIEW_DIFF": (45, .45), "REVERT": (6, .40), "IDLE": (12, .60),
    "READ": (30, .35), "SEARCH": (14, .40), "REFORMULATE": (10, .40), "NAVIGATE": (4, .40), "ENTER": (10, .35),
    "COPY": (3, .40), "PASTE": (3, .40), "COMPARE": (16, .40), "CHECK": (15, .35), "DECIDE": (6, .40), "ASK": (20, .45),
}
_ANA_DWELL = {
    "LOAD_DATA": (15, .40), "PROFILE_DATA": (40, .35), "WRITE_QUERY": (120, .45), "RUN_QUERY": (15, .50), "INSPECT_RESULT": (45, .35),
    "PLOT": (60, .40), "EXPORT_RESULT": (10, .40), "CHECK": (30, .35), "REVERT": (6, .40), "IDLE": (12, .60),
    "READ": (30, .35), "SEARCH": (14, .40), "REFORMULATE": (10, .40), "NAVIGATE": (4, .40), "ENTER": (10, .35),
    "COPY": (3, .40), "PASTE": (3, .40), "COMPARE": (16, .40), "DECIDE": (6, .40), "ASK": (20, .45),
}

_KLM_COMMON = {
    "READ": dict(M=18, P=1), "SEARCH": dict(M=5, P=2, K=22, R=1.5), "REFORMULATE": dict(M=4, P=1, K=18, R=1.5),
    "NAVIGATE": dict(M=1, P=1, R=1.5), "ENTER": dict(M=3, P=2, K=10), "COPY": dict(P=1, K=2, H=1), "PASTE": dict(P=1, K=2, H=1),
    "COMPARE": dict(M=10, P=3), "CHECK": dict(M=10, P=2), "DECIDE": dict(M=4, P=1, choices=3), "ASK": dict(M=10, P=3, K=30),
    "REVERT": dict(M=1, K=2), "IDLE": dict(M=1),
}
_KLM_BEN = {**_KLM_COMMON, "OPEN_CALCULATOR": dict(M=1, P=2, R=2.0), "ENTER_HOUSEHOLD": dict(M=6, P=8, K=40, H=2, R=1.5, choices=3),
            "READ_RESULT": dict(M=14, P=1), "CHECK_CLIFF": dict(M=22, P=3, R=2.0), "RECONCILE": dict(M=30, P=4, choices=3),
            "COPY_TO_NOTE": dict(M=12, P=5, K=15, H=2)}
_KLM_PRG = {**_KLM_COMMON, "READ_TRACE": dict(M=28, P=2), "READ_CODE": dict(M=34, P=3), "EDIT_CODE": dict(M=30, P=6, K=60, H=3),
            "RUN_TESTS": dict(M=1, P=1, R=8.0), "COMMIT": dict(M=6, P=3, K=35, H=2), "SEARCH_DOCS": dict(M=22, P=4, K=20, R=2.0),
            "REVIEW_DIFF": dict(M=30, P=4)}
_KLM_ANA = {**_KLM_COMMON, "LOAD_DATA": dict(M=3, P=3, R=4.0), "PROFILE_DATA": dict(M=26, P=5, R=3.0), "WRITE_QUERY": dict(M=22, P=6, K=110, H=3),
            "RUN_QUERY": dict(M=1, P=1, R=10.0), "INSPECT_RESULT": dict(M=30, P=4), "PLOT": dict(M=20, P=8, K=10, R=3.0),
            "EXPORT_RESULT": dict(M=4, P=3, R=3.0)}


def _act(commit=(), read=(), seek=(), revert=("REVERT",), pause=("IDLE",)):
    out = {}
    for cls, cogs in (("commit", commit), ("read", read), ("seek", seek), ("revert", revert), ("pause", pause)):
        for c in cogs:
            out[c] = cls
    return out


_BEN_ACT = _act(commit=("ENTER_HOUSEHOLD", "ENTER", "CHECK_CLIFF", "RECONCILE", "COPY_TO_NOTE", "COPY", "PASTE", "CHECK", "DECIDE"),
                read=("READ", "READ_RESULT"), seek=("SEARCH", "REFORMULATE", "NAVIGATE", "OPEN_CALCULATOR", "COMPARE", "ASK"))
_PRG_ACT = _act(commit=("EDIT_CODE", "RUN_TESTS", "COMMIT", "ENTER", "COPY", "PASTE", "CHECK", "DECIDE"),
                read=("READ", "READ_TRACE", "READ_CODE", "REVIEW_DIFF"), seek=("SEARCH", "REFORMULATE", "NAVIGATE", "SEARCH_DOCS", "COMPARE", "ASK"))
_ANA_ACT = _act(commit=("WRITE_QUERY", "RUN_QUERY", "PLOT", "EXPORT_RESULT", "ENTER", "COPY", "PASTE", "CHECK", "DECIDE"),
                read=("READ", "PROFILE_DATA", "INSPECT_RESULT", "LOAD_DATA"), seek=("SEARCH", "REFORMULATE", "NAVIGATE", "COMPARE", "ASK"))

# ------------------------------------------------------------------------------------------ task grammars
S = Step


def _benefits_units() -> tuple[Unit, ...]:
    us = [Unit("read_case", (S("READ"),))]
    for k, site in zip("abc", ("calc1", "calc2", "calc3")):
        us.append(Unit(f"calc_{k}", (S("OPEN_CALCULATOR", site), S("ENTER_HOUSEHOLD"), S("READ_RESULT")), after=("read_case",)))
    for k in "abc":
        us.append(Unit(f"cliff_{k}", (S("CHECK_CLIFF"),), after=(f"calc_{k}",), critical=True))
    us.append(Unit("reconcile", (S("RECONCILE"),), after=tuple(f"calc_{k}" for k in "abc") + tuple(f"cliff_{k}" for k in "abc"), critical=True))
    us.append(Unit("write_note", (S("COPY_TO_NOTE"),), after=("reconcile",)))
    us.append(Unit("verify_note", (S("CHECK"),), after=("write_note",), required=False))
    return tuple(us)


def _programmer_units() -> tuple[Unit, ...]:
    return (
        Unit("read_trace_first", (S("READ_TRACE"),), critical=True),
        Unit("read_code", (S("READ_CODE"),), after=("read_trace_first",)),
        Unit("docs", (S("SEARCH_DOCS"),), after=("read_trace_first",), required=False),
        Unit("edit", (S("EDIT_CODE"),), after=("read_code",)),
        Unit("review_diff", (S("REVIEW_DIFF"),), after=("edit",), required=False),
        Unit("commit", (S("COMMIT"),), after=("edit",)),
        Unit("rerun", (S("RUN_TESTS"),), after=("commit",), critical=True),
        Unit("confirm", (S("READ_TRACE"),), after=("rerun",), critical=True),
    )


def _analyst_units() -> tuple[Unit, ...]:
    return (
        Unit("load", (S("LOAD_DATA"),)),
        Unit("profile_inputs", (S("PROFILE_DATA"),), after=("load",), critical=True),
        Unit("write_query", (S("WRITE_QUERY"),), after=("profile_inputs",)),
        Unit("run_query", (S("RUN_QUERY"),), after=("write_query",)),
        Unit("inspect", (S("INSPECT_RESULT"),), after=("run_query",)),
        Unit("sanity_check", (S("CHECK"),), after=("inspect",), critical=True),
        Unit("plot", (S("PLOT"),), after=("inspect",), required=False),
        Unit("export", (S("EXPORT_RESULT"),), after=("sanity_check",), required=False),
    )


def _benefits_plan(role: RoleSpec, st: dict[str, str], rnd: random.Random) -> list[Step]:
    """Explicit strategy: calculator order, cliff placement, copy versus retype, read up front versus just in time, verify, compare."""
    order = [int(c) for c in st["calc_order"]]
    sites = {1: "calc1", 2: "calc2", 3: "calc3"}
    out: list[Step] = []
    jit = st["read_mode"] == "jit"
    if not jit:
        out.append(S("READ", unit="read_case"))
    for n, i in enumerate(order):
        u = f"calc_{'abc'[i - 1]}"
        if jit:
            out.append(S("READ", unit=u))
        out.append(S("OPEN_CALCULATOR", sites[i], u))
        if st["enter_mode"] == "copy" and n > 0:
            out += [S("COPY", unit=u), S("PASTE", unit=u)]
        out += [S("ENTER_HOUSEHOLD", unit=u), S("READ_RESULT", unit=u)]
        if st["cliff_mode"] == "immediate":
            out.append(S("CHECK_CLIFF", unit=f"cliff_{'abc'[i - 1]}"))
        elif st["cliff_mode"] == "mixed" and n < 2:
            out.append(S("CHECK_CLIFF", unit=f"cliff_{'abc'[i - 1]}"))
    if st["cliff_mode"] == "batched":
        out += [S("CHECK_CLIFF", unit=f"cliff_{k}") for k in "abc"]
    elif st["cliff_mode"] == "mixed":
        out.append(S("CHECK_CLIFF", unit=f"cliff_{'abc'[order[2] - 1]}"))
    out.append(S("RECONCILE", unit="reconcile"))
    if st["reconcile_mode"] == "compare":
        out += [S("COMPARE", unit="reconcile"), S("RECONCILE", unit="reconcile")]
    out.append(S("COPY_TO_NOTE", unit="write_note"))
    if st["verify"] == "yes":
        out += [S("READ_RESULT", unit="verify_note"), S("CHECK", unit="verify_note")]
    return out


def _programmer_plan(role: RoleSpec, st: dict[str, str], rnd: random.Random) -> list[Step]:
    out = [S("READ_TRACE", unit="read_trace_first")]
    if st["docs"] == "yes":
        out.append(S("SEARCH_DOCS", unit="docs"))
    cycles = int(st["cycles"])
    for c in range(cycles):
        out += [S("READ_CODE", unit="read_code"), S("EDIT_CODE", unit="edit")]
        if st["diff"] == "yes":
            out.append(S("REVIEW_DIFF", unit="review_diff"))
        if st["test_first"] == "yes":
            out += [S("RUN_TESTS", unit="rerun"), S("READ_TRACE", unit="confirm"), S("COMMIT", unit="commit")]
        else:
            out += [S("COMMIT", unit="commit"), S("RUN_TESTS", unit="rerun"), S("READ_TRACE", unit="confirm")]
    return out


def _analyst_plan(role: RoleSpec, st: dict[str, str], rnd: random.Random) -> list[Step]:
    out = [S("LOAD_DATA", unit="load"), S("PROFILE_DATA", unit="profile_inputs")]
    cycles = int(st["cycles"])
    for c in range(cycles):
        out += [S("WRITE_QUERY", unit="write_query"), S("RUN_QUERY", unit="run_query"), S("INSPECT_RESULT", unit="inspect")]
    if st["plot"] == "yes" and st["sanity_mode"] == "before":
        out += [S("PLOT", unit="plot"), S("CHECK", unit="sanity_check")]
    else:
        out.append(S("CHECK", unit="sanity_check"))
        if st["plot"] == "yes":
            out.append(S("PLOT", unit="plot"))
    if st["export"] == "yes":
        out.append(S("EXPORT_RESULT", unit="export"))
    return out


_BUILDERS = {BENEFITS: _benefits_plan, PROGRAMMER: _programmer_plan, ANALYST: _analyst_plan}

# ------------------------------------------------------------------------------------------ deficits
_BEN_DEFS = (
    DeficitSpec("skipped_check_cliff", "omit", "CHECK_CLIFF", rework=("REVERT", "ENTER_HOUSEHOLD", "CHECK_CLIFF", "READ_RESULT"),
                skill="check-the-cliff", param="pmax_skip_cliff"),
    DeficitSpec("repeated_read_result", "repeat", "READ_RESULT", skill="read-once", param="reread_mean_max"),
    DeficitSpec("search_loop", "loop", "ENTER_HOUSEHOLD", skill="search-less", param="search_rounds_max"),
    DeficitSpec("copy_error", "copy", "COPY_TO_NOTE", rework=("RECONCILE", "REVERT", "COPY_TO_NOTE"), skill="note-with-evidence", param="copy_error_pmax"),
    DeficitSpec("idle_before_enter", "freeze", "ENTER_HOUSEHOLD", skill="enter-household-once", param="idle_pmax"),
)
_PRG_DEFS = (
    DeficitSpec("edit_before_reading_trace", "omit", "READ_TRACE", rework=("REVERT", "READ_TRACE", "EDIT_CODE"), skill="read-the-trace-first", param="pmax_skip_cliff",
                doc="Edits code before reading the failing trace"),
    DeficitSpec("rerun_without_reading", "repeat", "RUN_TESTS", skill="confirm-the-fix", param="reread_mean_max",
                doc="Re-runs the job repeatedly without reading the result"),
)
_ANA_DEFS = (
    DeficitSpec("skip_profile", "omit", "PROFILE_DATA", rework=("REVERT", "WRITE_QUERY", "RUN_QUERY", "INSPECT_RESULT"), skill="profile-before-querying",
                param="pmax_skip_cliff", doc="Skips profiling the inputs"),
    DeficitSpec("trust_the_total", "omit", "INSPECT_RESULT", rework=("REVERT", "RUN_QUERY", "INSPECT_RESULT"), skill="inspect-before-trusting",
                param="copy_error_pmax", doc="Reads only the total, not sample rows"),
)

_BEN_ROUTINES = (
    RoutineT("calc-entry-3x", group=("OPEN_CALCULATOR", "ENTER_HOUSEHOLD", "READ_RESULT"), tail=("RECONCILE",), k=(2, 3), sites=True),
    RoutineT("case-note-copy", group=("READ_RESULT", "COPY_TO_NOTE"), k=(2, 3)),
    RoutineT("cliff-recheck", head=("ENTER_HOUSEHOLD", "CHECK_CLIFF", "READ_RESULT", "CHECK_CLIFF", "COPY_TO_NOTE")),
    RoutineT("queue-sweep", group=("NAVIGATE", "READ", "CHECK", "DECIDE"), k=(3, 5)),
    RoutineT("weekly-report", head=("NAVIGATE", "READ", "COPY", "NAVIGATE", "PASTE", "ENTER", "ENTER", "DECIDE")),
)
_PRG_ROUTINES = (
    RoutineT("rerun-failed-ci", head=("READ_TRACE", "RUN_TESTS", "NAVIGATE", "READ_TRACE")),
    RoutineT("triage-issue", head=("READ_TRACE", "SEARCH_DOCS", "READ_CODE", "DECIDE")),
    RoutineT("review-pr", group=("REVIEW_DIFF", "READ_CODE"), tail=("DECIDE", "COMMIT"), k=(2, 4)),
    RoutineT("bump-dependency", head=("READ_CODE", "EDIT_CODE", "RUN_TESTS", "READ_TRACE", "COMMIT")),
)
_ANA_ROUTINES = (
    RoutineT("weekly-metric-refresh", head=("RUN_QUERY", "INSPECT_RESULT", "COPY", "PASTE", "PLOT")),
    RoutineT("daily-sanity", group=("RUN_QUERY", "INSPECT_RESULT", "CHECK"), k=(1, 3)),
    RoutineT("export-report", head=("LOAD_DATA", "RUN_QUERY", "INSPECT_RESULT", "EXPORT_RESULT", "NAVIGATE")),
    RoutineT("profile-new-table", head=("LOAD_DATA", "PROFILE_DATA", "INSPECT_RESULT", "PLOT")),
)

_THIN_DEFICIT_TYPES = {
    **{d.id: {"description": d.doc, "cogs": [d.cog, *d.rework]} for d in _PRG_DEFS},
    **{d.id: {"description": d.doc, "cogs": [d.cog, *d.rework]} for d in _ANA_DEFS},
}

BENEFITS_SPEC = RoleSpec(
    id=BENEFITS, slug="ben",
    cogs=("READ", "SEARCH", "REFORMULATE", "NAVIGATE", "ENTER", "COPY", "PASTE", "COMPARE", "CHECK", "DECIDE", "IDLE", "REVERT", "ASK",
          "ENTER_HOUSEHOLD", "OPEN_CALCULATOR", "READ_RESULT", "CHECK_CLIFF", "COPY_TO_NOTE", "RECONCILE"),
    dwell=_BEN_DWELL, klm=_KLM_BEN, emit=_BEN_EMIT,
    zones=("doc", "form_field", "household_form", "calc_result", "cliff_panel", "results_tabs", "case_note", "page", "compare_view"),
    labels=BENEFITS_LABELS, act_class=_BEN_ACT, units=_benefits_units(), deficits=_BEN_DEFS, deficit_types=BENEFITS_DEFICITS,
    routines=_BEN_ROUTINES, detour_cogs=("SEARCH", "REFORMULATE", "READ", "READ_RESULT", "ASK", "REVERT", "NAVIGATE", "COMPARE"),
    pool=("READ", "SEARCH", "REFORMULATE", "NAVIGATE", "ENTER", "COPY", "PASTE", "COMPARE", "CHECK", "DECIDE", "ASK", "ENTER_HOUSEHOLD",
          "READ_RESULT", "COPY_TO_NOTE", "OPEN_CALCULATOR", "CHECK_CLIFF", "RECONCILE"),
    strategy_dims={
        "calc_order": ("123", "132", "213", "231", "312", "321"), "cliff_mode": ("immediate", "batched", "mixed"),
        "enter_mode": ("retype", "copy"), "read_mode": ("upfront", "jit"), "verify": ("no", "yes"), "reconcile_mode": ("single", "compare"),
    },
    sites=SITES, complexity_cog="ENTER_HOUSEHOLD",
)
PROGRAMMER_SPEC = RoleSpec(
    id=PROGRAMMER, slug="prg",
    cogs=("READ_TRACE", "READ_CODE", "EDIT_CODE", "RUN_TESTS", "REVIEW_DIFF", "COMMIT", "SEARCH_DOCS", "READ", "SEARCH", "REFORMULATE",
          "NAVIGATE", "ENTER", "COPY", "PASTE", "COMPARE", "CHECK", "DECIDE", "IDLE", "REVERT", "ASK"),
    dwell=_PRG_DWELL, klm=_KLM_PRG, emit=_PRG_EMIT,
    zones=("code_view", "code_editor", "test_runner", "ci_log", "diff_view", "commit_box", "docs_page", "doc", "form_field", "compare_view"),
    labels=_PRG_LABELS, act_class=_PRG_ACT, units=_programmer_units(), deficits=_PRG_DEFS, deficit_types=_THIN_DEFICIT_TYPES,
    routines=_PRG_ROUTINES, detour_cogs=("SEARCH_DOCS", "READ_CODE", "READ_TRACE", "ASK", "REVERT", "NAVIGATE", "COMPARE", "SEARCH"),
    pool=("READ_TRACE", "READ_CODE", "EDIT_CODE", "RUN_TESTS", "REVIEW_DIFF", "COMMIT", "SEARCH_DOCS", "SEARCH", "NAVIGATE", "COPY", "PASTE",
          "COMPARE", "CHECK", "DECIDE", "ASK"),
    strategy_dims={"docs": ("no", "yes"), "cycles": ("1", "2", "3"), "diff": ("no", "yes"), "test_first": ("no", "yes")},
)
ANALYST_SPEC = RoleSpec(
    id=ANALYST, slug="ana",
    cogs=("LOAD_DATA", "PROFILE_DATA", "WRITE_QUERY", "RUN_QUERY", "INSPECT_RESULT", "PLOT", "EXPORT_RESULT", "READ", "SEARCH", "REFORMULATE",
          "NAVIGATE", "ENTER", "COPY", "PASTE", "COMPARE", "CHECK", "DECIDE", "IDLE", "REVERT", "ASK"),
    dwell=_ANA_DWELL, klm=_KLM_ANA, emit=_ANA_EMIT,
    zones=("data_browser", "profile_panel", "sql_editor", "run_control", "query_result", "chart_panel", "export_panel", "doc", "form_field", "compare_view"),
    labels=_ANA_LABELS, act_class=_ANA_ACT, units=_analyst_units(), deficits=_ANA_DEFS, deficit_types=_THIN_DEFICIT_TYPES,
    routines=_ANA_ROUTINES, detour_cogs=("SEARCH", "REFORMULATE", "INSPECT_RESULT", "PROFILE_DATA", "ASK", "REVERT", "NAVIGATE"),
    pool=("LOAD_DATA", "PROFILE_DATA", "WRITE_QUERY", "RUN_QUERY", "INSPECT_RESULT", "PLOT", "EXPORT_RESULT", "SEARCH", "NAVIGATE", "COPY", "PASTE",
          "COMPARE", "CHECK", "DECIDE", "ASK"),
    strategy_dims={"cycles": ("1", "2", "3"), "plot": ("no", "yes"), "export": ("no", "yes"), "sanity_mode": ("before", "after")},
)

ROLES: dict[str, RoleSpec] = {BENEFITS: BENEFITS_SPEC, PROGRAMMER: PROGRAMMER_SPEC, ANALYST: ANALYST_SPEC}


def get_role(role: str) -> RoleSpec:
    key = ROLE_ALIASES.get(role)
    if key is None:
        raise KeyError(f"unknown role {role!r}; known: {sorted(ROLES)}")
    return ROLES[key]
