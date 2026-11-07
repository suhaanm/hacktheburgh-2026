"""Event emission: segments become schema-valid events, with capture noise and the progress process.

Everything written here is an enum, a number or a salted hash (the L0 rules apply to generated data too): no free text,
no URLs, no field values. The shared parts of the three families live here: the emitter, the noise model, the
progress point process and the stuck self-reports.

Noise (per person: a device multiplier on the dataset's rates): dropped events (with outages that drop the next one to
five), timestamp jitter, double-fires, wrong zone, missing label hash, whole-second timestamps, a missing ``task_end``,
and a clock skew of the OS source. The cog mapper then makes of this what it can: the analytics never see the planted
segment list.

The ``progress`` label is a separate point process (see ``PLAN.md``): rate = person base rate x a soft activity
multiplier per cog class x the hidden stuck multiplier of the episode the moment belongs to.
"""
from __future__ import annotations

import math
import random
from datetime import datetime, timezone

from ..store.hashing import SYNTHETIC_SALT, hash_label
from ..store.validate import fmt_t
from ..personas.vocab import domain_hash
from .core import CasePlan, Seg, poisson
from .people import Person
from .roles import Emit, RoleSpec

_label_cache: dict[tuple[str, str], str] = {}
PROGRESS_KIND = {"READ_RESULT": "result_read", "COPY_TO_NOTE": "note_field", "CHECK_CLIFF": "cliff_checked"}


def _lab(role: RoleSpec, zone: str, idx: int) -> str:
    names = role.labels.get(zone) or ["element"]
    name = names[idx % len(names)]
    key = (zone, name)
    if key not in _label_cache:
        _label_cache[key] = hash_label(f"{zone}:{name}", salt=SYNTHETIC_SALT)
    return _label_cache[key]


def iso(t: float) -> str:
    return fmt_t(datetime.fromtimestamp(t, tz=timezone.utc))


class Emitter:
    """Collects raw event rows for one person. Times stay in unix seconds until ``finalize``."""

    def __init__(self, person: Person, role: RoleSpec, h: dict, rnd: random.Random, prefix: str):
        self.p, self.role, self.h, self.rnd, self.prefix = person, role, h, rnd, prefix
        self.rows: list[dict] = []
        self._n = 0
        self.skew = rnd.uniform(-h["os_skew_s"], h["os_skew_s"])      # clock skew of the OS source against the browser source

    def _mk(self, typ: str, t: float, *, source: str = "browser", zone: str | None = None, trole: str | None = None,
            label_idx: int | None = None, site: str | None = None, meta: dict | None = None, task_id: str | None = None) -> dict:
        self._n += 1
        row: dict = {"schema": 1, "id": f"{self.prefix}-{self._n:07d}", "t": t, "origin": "synthetic", "actor": "human",
                     "person": self.p.id, "role": self.role.id, "source": source, "type": typ}
        tgt: dict = {}
        if trole:
            tgt["role"] = trole
        if zone and label_idx is not None:
            tgt["label_hash"] = _lab(self.role, zone, label_idx)
        if site:
            tgt["domain_hash"] = domain_hash(site)
        if tgt:
            row["target"] = tgt
        if task_id:
            row["task_id"] = task_id
        m = dict(meta or {})
        if zone:
            m["zone"] = zone
        if m:
            row["meta"] = m
        return row

    def plain(self, typ: str, t: float, **kw) -> dict:
        row = self._mk(typ, t, **kw)
        self.rows.append(row)
        return row


# ------------------------------------------------------------------------------------------ inside a case
def _tick_times(rnd: random.Random, h: dict, dur: float) -> list[float]:
    """Bursty times inside a segment (lognormal gaps), first event near the start."""
    if dur < 3.0:
        return [min(0.3, dur * 0.1)]
    sigma = h["event_gap_sigma"]
    med = (1.0 / h["event_rate_per_s"]) * math.exp(-sigma * sigma / 2.0)
    out = [rnd.uniform(0.0, min(1.0, dur * 0.1))]
    t = out[0]
    while True:
        t += max(0.05, rnd.lognormvariate(math.log(med), sigma))
        if t >= dur * 0.97:
            break
        out.append(t)
    if out[-1] < dur * 0.8 and dur > 8:
        out.append(dur * rnd.uniform(0.85, 0.97))
    return out


def _seg_events(em: Emitter, seg: Seg, t0: float, tid: str | None) -> list[dict]:
    rnd, role, h = em.rnd, em.role, em.h
    ev: list[dict] = []
    dur = seg.dur
    tid = tid if seg.traced else None

    def mk(typ, dt, **kw):
        ev.append(em._mk(typ, t0 + dt, task_id=tid, **kw))

    if seg.kind == "interrupt":
        mk("tab", min(0.4, dur * 0.05), meta=None)
        if dur > 6 and rnd.random() < 0.5:
            mk("click", min(dur - 0.5, 2.0 + rnd.random() * 3.0), trole="link", site=f"tool{rnd.randint(1, 3)}")
        return ev
    if seg.kind == "pause" or seg.cog == "IDLE":
        return ev
    spec: Emit | None = role.emit.get(seg.cog)
    if spec is None or spec.kind == "none":
        return ev
    k = spec.kind
    if k == "undo":
        mk("undo", 0.1)
    elif k == "single":
        site = seg.site if spec.site else None
        meta = {"site": site} if site else None
        mk(spec.types[0], min(0.2, dur * 0.1), zone=spec.zone, trole=spec.role, label_idx=0 if site else rnd.randrange(0, 3), site=site, meta=meta, source=spec.source)
    elif k == "nav":
        mk("nav", 0.1, zone=spec.zone, trole=spec.role, site=seg.site or f"tool{rnd.randint(1, 3)}")
    elif k in ("search", "reformulate"):
        ln = int(seg.query_len or rnd.randint(8, 40))
        mk("search", 0.0, zone="search_box", trole="searchbox", label_idx=0, meta={"len": ln})
        zone = "search_box" if k == "search" else "query_edit"
        for dt in _tick_times(rnd, h, dur)[1:]:
            mk("scroll" if k == "search" else "focus", dt, zone=zone, trole="searchbox", label_idx=0)
    elif k == "copy_note":
        mk("copy", 0.1, zone="calc_result", trole="region", label_idx=rnd.randrange(0, 3))
        if dur > 6:
            mk("tab", dur * 0.35, zone="case_note", trole="tab", label_idx=0)
        mk("click", dur * 0.7, zone="case_note", trole="textbox", label_idx=0)
        mk("paste", max(0.6, dur - 1.0), zone="case_note", trole="textbox", label_idx=0)
    else:  # ticks
        for i, dt in enumerate(_tick_times(rnd, h, dur)):
            if i == 0 and spec.first:
                typ = spec.first
            elif i > 0 and spec.rest:
                typ = spec.rest[rnd.randrange(len(spec.rest))]
            else:
                typ = spec.types[rnd.randrange(len(spec.types))]
            meta = {"depth_bin": rnd.randrange(0, 6)} if typ == "scroll" else None
            mk(typ, dt, zone=spec.zone, trole=spec.role, label_idx=rnd.randrange(0, 8), meta=meta, source=spec.source)
    return ev


def _apply_noise(em: Emitter, events: list[dict]) -> list[dict]:
    """Capture noise on one case's interaction events (task markers, progress and stuck reports are not affected)."""
    rnd, h = em.rnd, em.h
    cm = em.p.cap_mult
    drop = min(0.5, h["drop_p"] * cm)
    out: list[dict] = []
    outage = 0
    for e in sorted(events, key=lambda r: r["t"]):
        if outage > 0:
            outage -= 1
            continue
        if rnd.random() < drop:
            if rnd.random() < h["drop_burst_p"]:
                outage = rnd.randint(1, 5)
            continue
        e = dict(e)
        e["t"] = e["t"] + rnd.gauss(0.0, h["jitter_sd_s"] * cm)
        if rnd.random() < h["coarse_ts_p"]:
            e["t"] = float(round(e["t"]))
        if "meta" in e and "zone" in e["meta"] and rnd.random() < h["zone_err_p"] * cm:
            e["meta"] = {**e["meta"], "zone": em.role.zones[rnd.randrange(len(em.role.zones))]}
        if "target" in e and "label_hash" in e["target"] and rnd.random() < h["label_missing_p"]:
            tg = {k: v for k, v in e["target"].items() if k != "label_hash"}
            if tg:
                e["target"] = tg
            else:
                del e["target"]
        out.append(e)
        if rnd.random() < h["double_p"] * cm:
            d = dict(e)
            em._n += 1
            d["id"] = f"{em.prefix}-{em._n:07d}"
            d["t"] = e["t"] + rnd.uniform(0.02, 0.4)
            out.append(d)
    return out


def emit_case(em: Emitter, plan: CasePlan, t0: float, tid: str, *, with_markers: bool = True) -> tuple[float, list[tuple[float, float]]]:
    """Write one case's events. Returns the end time and each segment's (start, end)."""
    rnd, h, p, role = em.rnd, em.h, em.p, em.role
    spans: list[tuple[float, float]] = []
    t = t0
    interaction: list[dict] = []
    for seg in plan.segs:
        spans.append((t, t + seg.dur))
        interaction.extend(_seg_events(em, seg, t, tid))
        if seg.kind in ("pause", "interrupt") and seg.dur >= p.idle_threshold_s:
            em.plain("idle", t + p.idle_threshold_s + em.skew, source="os", meta={"idle_s": int(p.idle_threshold_s)})
        t += seg.dur
    t_end = t
    for e in _apply_noise(em, interaction):
        em.rows.append(e)
    # the progress process: a point process on the time axis
    base = p.progress_rate_min / 60.0
    lag = h["progress_lag_s"]
    stuck_supp = {s.id: s.supp for s in plan.stuck}
    n_prog = 0
    for seg, (a, b) in zip(plan.segs, spans):
        if seg.kind == "interrupt":
            continue
        cls = "pause" if seg.kind == "pause" else role.act_class.get(seg.cog, "seek")
        lam = base * p.progress_mult[cls] * (stuck_supp.get(seg.stuck_id, 1.0) if seg.stuck_id else 1.0)
        for _ in range(poisson(rnd, lam * (b - a))):
            tp = a + rnd.random() * (b - a) + (rnd.expovariate(1.0 / lag) if lag > 0 else 0.0)
            em.plain("progress", min(tp, t_end + 3.0), source="browser", meta={"kind": PROGRESS_KIND.get(seg.cog, "step_done")}, task_id=tid)
            n_prog += 1
    dur_h = (t_end - t0) / 3600.0
    for _ in range(poisson(rnd, h["spurious_progress_per_h"] * dur_h)):
        em.plain("progress", t0 + rnd.random() * (t_end - t0), source="browser", meta={"kind": "step_done"}, task_id=tid)
    # self-reported stuck, and false reports
    reports: list[float] = []
    for s in plan.stuck:
        if rnd.random() < p.stuck_report_p:
            a, b = spans[s.i0][0], spans[s.i1 - 1][1]
            tr = a + (b - a) * rnd.uniform(0.4, 0.9)
            em.plain("stuck", tr, source="desk", task_id=tid)
            s.reported = True
            reports.append(tr)
    for _ in range(poisson(rnd, h["stuck_false_per_h"] * dur_h)):
        em.plain("stuck", t0 + rnd.random() * (t_end - t0), source="desk", task_id=tid)
    if with_markers:
        em.plain("task_start", t0 - abs(rnd.gauss(0.0, 0.4)), source="desk", task_id=tid)
        if rnd.random() >= h["task_end_missing_p"]:
            em.plain("task_end", t_end + 0.2 + abs(rnd.gauss(0.0, 0.3)), source="desk", task_id=tid)
    return t_end, spans


def finalize(rows: list[dict]) -> list[dict]:
    """Sort by time then id, convert times to the canonical timestamp string."""
    rows = sorted(rows, key=lambda r: (r["t"], r["id"]))
    for r in rows:
        r["t"] = iso(r["t"])
    return rows
