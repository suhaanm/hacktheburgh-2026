"""How a cog looks as events. Shared by the persona simulator and the apprentice generator.

The mapping in ``cogs/default_mapping.yaml`` is the inverse of this table: ``emit_cog`` writes the events
that the mapper turns back into the same cog. Events carry no text; the semantic hint is ``meta.zone``.
"""
from __future__ import annotations

import math

import numpy as np

from ..store.hashing import SYNTHETIC_SALT, hash_domain, hash_label

SITES = {
    "calc1": "entitled-to.sandbox.test",
    "calc2": "turn2us.sandbox.test",
    "calc3": "policyengine.sandbox.test",
}
BENEFITS_COGS = ("ENTER_HOUSEHOLD", "OPEN_CALCULATOR", "READ_RESULT", "CHECK_CLIFF", "COPY_TO_NOTE", "RECONCILE")

# Typical median dwell in seconds for one cog segment (before skill, persona speed and noise).
BASE_DWELL = {
    "READ": 14.0, "SEARCH": 9.0, "REFORMULATE": 8.0, "NAVIGATE": 5.0, "ENTER": 10.0, "COPY": 3.0, "PASTE": 3.0,
    "COMPARE": 16.0, "CHECK": 8.0, "DECIDE": 6.0, "IDLE": 20.0, "REVERT": 3.0, "ASK": 20.0,
    "ENTER_HOUSEHOLD": 42.0, "OPEN_CALCULATOR": 6.0, "READ_RESULT": 14.0, "CHECK_CLIFF": 28.0,
    "COPY_TO_NOTE": 14.0, "RECONCILE": 24.0,
}

# cog -> (event types used for ticks, zone, target role, source)
_TICKS = {
    "READ": (("scroll", "focus"), "doc", "document", "browser"),
    "ENTER": (("click", "focus"), "form_field", "textbox", "browser"),
    "COMPARE": (("tab", "click"), "compare_view", "tab", "browser"),
    "CHECK": (("click",), "check_box", "checkbox", "browser"),
    "DECIDE": (("click",), "decision_btn", "button", "browser"),
    "ASK": (("click",), "help", "button", "browser"),
    "ENTER_HOUSEHOLD": (("click", "focus"), "household_form", "textbox", "browser"),
    "READ_RESULT": (("scroll", "focus"), "calc_result", "region", "browser"),
    "CHECK_CLIFF": (("click", "scroll"), "cliff_panel", "button", "browser"),
    "RECONCILE": (("tab", "click"), "results_tabs", "tab", "browser"),
    "SEARCH": (("scroll",), "search_box", "searchbox", "browser"),
    "REFORMULATE": (("focus", "click"), "query_edit", "searchbox", "browser"),
}

LABELS = {
    "household_form": ["income", "partner income", "rent", "children", "childcare cost", "savings", "council tax band", "hours worked"],
    "form_field": ["name field", "reference field", "date field", "notes field"],
    "doc": ["case file", "guidance page", "letter"],
    "calc_result": ["entitlement result", "monthly amount", "breakdown"],
    "cliff_panel": ["income test", "what if earnings rise", "threshold check"],
    "case_note": ["case note field", "paste target"],
    "results_tabs": ["calc one tab", "calc two tab", "calc three tab"],
    "compare_view": ["left tab", "right tab"],
    "check_box": ["verified box", "eligibility box"],
    "decision_btn": ["confirm", "defer"],
    "help": ["help button", "guidance link"],
    "search_box": ["search box"],
    "query_edit": ["search box"],
}

# cogs whose first event is a focus (it opens a new segment, so back-to-back repeats stay separate cogs)
START_FOCUS = frozenset({"READ", "READ_RESULT", "CHECK_CLIFF"})

_label_cache: dict[tuple[str, str], str] = {}


def label_hash(zone: str, idx: int) -> str:
    names = LABELS.get(zone, ["element"])
    name = names[idx % len(names)]
    key = (zone, name)
    if key not in _label_cache:
        _label_cache[key] = hash_label(f"{zone}:{name}", salt=SYNTHETIC_SALT)
    return _label_cache[key]


_dom_cache: dict[str, str] = {}


def domain_hash(site: str) -> str:
    if site not in _dom_cache:
        _dom_cache[site] = hash_domain(SITES.get(site, site + ".sandbox.test"), salt=SYNTHETIC_SALT)
    return _dom_cache[site]


class Emitter:
    """Collects event rows (plain dicts, schema shape) for one person."""

    def __init__(self, person: str, role: str, prefix: str, rng: np.random.Generator, origin: str = "synthetic", actor: str = "human"):
        self.person, self.role, self.prefix, self.rng = person, role, prefix, rng
        self.origin, self.actor = origin, actor
        self.rows: list[dict] = []
        self._n = 0
        self.task_id: str | None = None

    def add(self, typ: str, t: float, *, source: str = "browser", zone: str | None = None, role: str | None = None,
            label_idx: int | None = None, site: str | None = None, meta: dict | None = None, task: bool = True) -> None:
        self._n += 1
        row: dict = {
            "schema": 1, "id": f"{self.prefix}-{self._n:07d}", "t": t, "origin": self.origin, "actor": self.actor,
            "person": self.person, "role": self.role, "source": source, "type": typ,
        }
        tgt: dict = {}
        if role:
            tgt["role"] = role
        if zone and label_idx is not None:
            tgt["label_hash"] = label_hash(zone, label_idx)
        if site:
            tgt["domain_hash"] = domain_hash(site)
        if tgt:
            row["target"] = tgt
        if task and self.task_id:
            row["task_id"] = self.task_id
        m = dict(meta or {})
        if zone:
            m["zone"] = zone
        if m:
            row["meta"] = m
        self.rows.append(row)

    # --------------------------------------------------------------- cogs as events
    def _tick_times(self, t0: float, t1: float) -> list[float]:
        """Event times inside a segment; the largest gap is at most ~12 s so the mapper keeps it one segment."""
        dur = max(0.0, t1 - t0)
        spacing = float(self.rng.uniform(6.0, 12.0))
        if dur < 4.0:
            return [t0 + min(0.2, dur * 0.1)]
        n = int(math.ceil(dur * 0.93 / spacing)) + 1
        base = np.linspace(0.0, 0.93, n)
        jitter = self.rng.uniform(-0.1, 0.1, n) * (0.93 / max(1, n - 1)) * 0.5
        frac = np.clip(base + jitter, 0.0, 0.97)
        frac[0] = 0.0
        frac[-1] = max(frac[-1], 0.9)
        return [float(t0 + dur * f) for f in sorted(frac)]

    def cog(self, cog: str, t0: float, t1: float, *, site: str | None = None, query_len: int | None = None) -> None:
        """Write events for one cog segment spanning [t0, t1]."""
        rng = self.rng
        dur = t1 - t0
        if cog == "IDLE":
            if dur >= 25:
                a = float(min(15.0, dur * 0.5))
                self.add("idle", t0 + a, source="os", meta={"idle_s": int(round(a))})
            return
        if cog == "OPEN_CALCULATOR":
            self.add("nav", t0, zone="calc_site", role="link", label_idx=0, site=site or "calc1", meta={"site": site or "calc1"})
            return
        if cog == "NAVIGATE":
            self.add("nav", t0, zone="page", role="link", site=site or rng.choice(list(SITES)))
            return
        if cog in ("SEARCH", "REFORMULATE"):
            ln = int(query_len if query_len is not None else rng.integers(8, 40))
            self.add("search", t0, zone="search_box", role="searchbox", label_idx=0, meta={"len": ln})
            for t in self._tick_times(t0, t1)[1:]:
                self.add("scroll" if cog == "SEARCH" else "focus", t, zone="search_box" if cog == "SEARCH" else "query_edit",
                         role="searchbox", label_idx=0)
            return
        if cog == "REVERT":
            self.add("undo", t0 + 0.1)
            return
        if cog == "COPY":
            self.add("copy", t0 + 0.1, zone="doc", role="document", label_idx=int(rng.integers(0, 3)))
            return
        if cog == "PASTE":
            self.add("paste", t0 + 0.1, zone="doc", role="textbox", label_idx=int(rng.integers(0, 3)))
            return
        if cog == "COPY_TO_NOTE":
            wrong = False
            self.add("copy", t0 + 0.1, zone="calc_result", role="region", label_idx=int(rng.integers(0, 3)))
            if dur > 6:
                self.add("tab", t0 + dur * 0.35, zone="case_note", role="tab", label_idx=0)
            self.add("click", t0 + dur * 0.7, zone="case_note", role="textbox", label_idx=0)
            self.add("paste", max(t0 + 0.6, t1 - 1.0), zone="case_note", role="textbox", label_idx=0)
            del wrong
            return
        types, zone, role, source = _TICKS[cog]
        for i, t in enumerate(self._tick_times(t0, t1)):
            typ = str(rng.choice(types))
            if cog in START_FOCUS:
                typ = "focus" if i == 0 else ("scroll" if cog != "CHECK_CLIFF" else str(rng.choice(["click", "scroll"])))
            meta = {"depth_bin": int(rng.integers(0, 6))} if typ == "scroll" else None
            self.add(typ, t, source=source, zone=zone, role=role, label_idx=int(rng.integers(0, 8)), meta=meta)

    def progress(self, t: float, kind: str, idx: int | None = None) -> None:
        meta: dict = {"kind": kind}
        if idx is not None:
            meta["idx"] = idx
        self.add("progress", t, source="browser", meta=meta)

    def task_start(self, t: float, task_id: str) -> None:
        self.task_id = task_id
        self.add("task_start", t, source="desk")

    def task_end(self, t: float) -> None:
        self.add("task_end", t, source="desk")
        self.task_id = None
