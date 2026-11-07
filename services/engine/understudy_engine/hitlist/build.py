"""The repeated-work hit list: pure compute from episodes. No model, no network, no clock, no disk.

What it answers: "which things have I done many times by hand that could run for me, and how much of my week do they take?"
It is built from the routine finder's own clusters of repeated sequences (``routines.finder``) over a time window, then filtered and
ranked by fixed rules. The order of the rules is the order a reader would ask the questions:

1. WINDOW. Episodes that started inside the last ``window_days`` and after the worker last pressed "start counting again".
2. FINDER. Average-linkage clusters of episode skeletons. A cluster needs at least ``min_repeats`` (3) members; one that matches no
   pack routine needs ``min_repeats_unmatched`` (5) on at least ``min_days_unmatched`` (2) different days, because three look-alike
   episodes picked out of random work are common and a routine seen on one afternoon is a batch, not a habit.
3. HELD BACK, with one reason each, counted but never listed: the first step is irreversible or outward (an automation would stop
   before it starts), the pack marks the routine as needing judgement or its judgement share is over ``max_judgement_share``,
   the sequence varies too much (mean edit distance to the medoid over ``max_variation``), or it touches something on the worker's
   denylist.
4. MERGE the same task done through different tools: clusters that match the same pack routine, or whose steps are the same kinds
   of work in the same order (``vocab.family_signature``), become one row; the count adds up and the variants are counted.
5. STATUS from the routine registry (what the worker has already decided). Declined for good ("never") leaves the list. Already
   running with its trust earned (rung A2 or more) goes to ``automated``. A row the worker hid stays hidden until its count has
   doubled.
6. OVERLAP. If one row's steps sit inside another's, keep the one worth more minutes and show the other as part of it.
7. RANK by minutes saved a week (rounded to 0.1), then count, then id: fully deterministic. At most ``max_rows`` are shown.

Minutes saved a week = repeats per week x average time per run x (1 - judgement share): the worker still does the judgement part.
The interval (95%) comes from two things the finder knows: the count is Poisson (a Gamma posterior on the weekly rate) and the time
per run is bootstrapped from the member episodes' own durations. Fixed seeds, so the same data gives the same numbers.
"""
from __future__ import annotations

import zlib
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Any

import numpy as np

from ..core import Episode
from ..memory.packinfo import PackView
from ..routines.finder import Cluster, FinderConfig, collapse, edit_distance, find_routines, skeleton
from ..routines.proposal import build_proposal
from ..routines.scoring import auto_id, judgement_share, match_template
from ..routines.value import hours_per_run_draws
from . import vocab as V

DAY = 86400.0


@dataclass(frozen=True)
class HitConfig:
    min_repeats: int = 3
    min_repeats_unmatched: int = 5
    min_days_unmatched: int = 2
    max_variation: float = 0.25          # mean normalised edit distance of the members to the medoid
    max_judgement_share: float = 0.4
    min_minutes_saved: float = 1.0       # a row worth under a minute a week is not worth a row
    max_rows: int = 10
    min_episodes_for_verdict: int = 6    # fewer cases than this in the window and nothing found: say there is too little data
    hide_factor: float = 2.0             # a hidden row comes back once its count is this many times what it was
    same_task_distance: float = 0.3      # the registry's own rule for "the same unnamed routine seen again"
    draws: int = 2000
    seed: int = 17
    finder: FinderConfig = field(default_factory=FinderConfig)


@dataclass(frozen=True)
class RoutineView:
    """What the worker's routine registry says about one routine (``routines.store``): decisions are theirs, never ours."""

    id: str
    status: str            # proposed | declined | never | shadow | approval | unattended
    rung: str = "A0"
    proposable: bool = True


Lookup = Callable[[str, "tuple[str, ...]"], "RoutineView | None"]


def iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def status_of(view: RoutineView | None) -> str:
    """Candidate (nothing happening), proposed (a card is waiting), learning (watching first), running (let it run, trust not yet
    earned) or automated (let it run and the trust ladder reached A2 or more)."""
    if view is None:
        return "candidate"
    if view.status == "shadow":
        return "learning"
    if view.status in ("approval", "unattended"):
        return "automated" if view.rung in ("A2", "A3") else "running"
    if view.status == "proposed":
        return "proposed" if view.proposable else "candidate"
    return "candidate"           # declined for now ("not now")


def _contains(big: Sequence[str], small: Sequence[str]) -> bool:
    n, m = len(small), len(big)
    return 0 < n < m and any(tuple(big[i:i + n]) == tuple(small) for i in range(m - n + 1))


def match_cluster_template(cl: Cluster, templates: Sequence[dict[str, Any]]) -> dict[str, Any] | None:
    """The pack routine this cluster is. First the finder's own rule (the medoid within the template's ``match_distance``); failing
    that, the template that at least half of the members are within ``match_distance`` of, because a window can pick an odd
    episode as the medoid of what is plainly the same routine."""
    tmpl, _ = match_template(tuple(cl.medoid), templates)
    if tmpl is not None:
        return tmpl
    best, best_key = None, None
    for t in templates:
        tc, md = collapse(t["cogs"]), float(t.get("match_distance", 0.3))
        ds = [edit_distance(skeleton(e), tc) for e in cl.episodes]
        frac = sum(1 for d in ds if d <= md) / max(len(ds), 1)
        if frac >= 0.5:
            key = (-frac, sum(ds) / len(ds), str(t["id"]))
            if best_key is None or key < best_key:
                best, best_key = t, key
    return best


def _deny_terms(entries: Iterable[Mapping[str, Any]]) -> list[str]:
    out: list[str] = []
    for e in entries or ():
        v = str(e.get("value", "")).strip().lower()
        if not v:
            continue
        out.append(v.split(".")[0] if e.get("kind") == "domain" and "." in v else v)
    return [t for t in out if t]


def _denied(touches: Iterable[str], terms: Sequence[str]) -> bool:
    for t in touches:
        t = str(t).lower()
        if any(term in t or t in term for term in terms):
            return True
    return False


def _minutes(durations_s: Sequence[float], count: int, weeks: float, j: float, draws: int, seed: int) -> tuple[float, float, float, np.ndarray]:
    """``(point, lo, hi, draws)`` in minutes saved a week."""
    mean_min = float(np.mean(durations_s)) / 60.0 if len(durations_s) else 0.0
    keep = max(0.0, 1.0 - j)
    point = count / weeks * mean_min * keep
    rng = np.random.default_rng(seed)
    rate = rng.gamma(shape=max(count, 1), scale=1.0 / weeks, size=draws)          # runs a week, Poisson count with a flat prior
    per_run = hours_per_run_draws(durations_s, draws, seed) * 60.0               # minutes a run, bootstrapped
    d = rate * per_run * keep
    lo, hi = (float(x) for x in np.quantile(d, [0.025, 0.975]))
    return point, min(lo, point), max(hi, point), d


def _interval(point: float, lo: float, hi: float) -> dict[str, float]:
    return {"point": round(point, 1), "lo": round(lo, 1), "hi": round(hi, 1)}


def _seed(base: int, rid: str) -> int:
    return (base + zlib.crc32(rid.encode())) % (2 ** 31)


@dataclass
class _Group:
    template: dict[str, Any] | None
    clusters: list[Cluster] = field(default_factory=list)

    @property
    def main(self) -> Cluster:
        return sorted(self.clusters, key=lambda c: (-c.size, c.medoid))[0]


def _empty(window_days: int, start: float, now: float, since: float | None, n_win: int, state: str, message: str,
           held: Mapping[str, int] | None = None, hidden: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "state": state, "message": message, "window_days": window_days, "window_from": iso(start), "window_to": iso(now),
        "counting_since": iso(since) if since is not None else None, "episodes_in_window": n_win,
        "rows": [], "automated": [], "hidden": hidden or [], "held_back": [{"reason": r, "count": n} for r, n in (held or {}).items() if n],
        "not_shown": 0, "total": None,
    }


def build_hitlist(episodes: Sequence[Episode], pack: PackView, *, person: str, now: float, window_days: int = 7,
                  reset_at: float | None = None, hidden: Mapping[str, Mapping[str, Any]] | None = None, lookup: Lookup | None = None,
                  denylist: Iterable[Mapping[str, Any]] = (), cfg: HitConfig | None = None,
                  sig_out: dict[str, tuple[str, ...]] | None = None, only_ids: set[str] | None = None) -> dict[str, Any]:
    """The hit list for one person over the last ``window_days`` ending at ``now`` (unix seconds). Pure and deterministic.
    ``sig_out``, when given, is filled with each listed row's step signature (the hide mark needs it); it is never part of the answer.
    ``only_ids`` keeps just those routines (the seeded demo lists the ones its person owns); a row outside it is dropped without a word."""
    cfg = cfg or HitConfig()
    episodes = list(episodes)
    window_days = int(window_days)
    start = now - window_days * DAY
    since = reset_at if reset_at is not None and reset_at > start else None
    if since is not None:
        start = since
    win = sorted((e for e in episodes if start <= e.t0 <= now), key=lambda e: (e.t0, e.task_id))
    n_win = len(win)
    if not episodes:
        return _empty(window_days, start, now, since, 0, "new_user", V.sentence_new_user())

    first = min(e.t0 for e in episodes)
    observed_days = max(0.0, min(float(window_days), (now - max(start, first)) / DAY))
    weeks = max(observed_days, 7.0) / 7.0          # never extrapolate a short stretch: under a week counts as a week (the finder's rule)

    min_support = max(cfg.min_repeats, int(pack.template_defaults.get("min_support") or 0))
    clusters = find_routines(win, replace(cfg.finder, min_support=min_support))
    judgement = pack.judgement_cogs()
    terms = _deny_terms(denylist)
    held = {r: 0 for r in V.HELD_REASONS}

    # ---- 3. held back, and the evidence floor for sequences that match no pack routine
    kept: list[tuple[Cluster, dict[str, Any] | None, float]] = []
    for cl in clusters:
        sig = tuple(cl.medoid)
        tmpl = match_cluster_template(cl, pack.templates)
        j = judgement_share(sig, judgement)
        if V.step_risk(sig[0]):
            held["irreversible_first_step"] += 1
        elif (tmpl is not None and not tmpl.get("automatable", True)) or j > cfg.max_judgement_share:
            held["judgement"] += 1
        elif cl.mean_dist > cfg.max_variation:
            held["unstable"] += 1
        elif tmpl is not None and _denied(tmpl.get("touches") or [], terms):
            held["denylist"] += 1
        elif tmpl is None and (cl.size < cfg.min_repeats_unmatched or len({int(e.t0 // DAY) for e in cl.episodes}) < cfg.min_days_unmatched):
            continue
        else:
            kept.append((cl, tmpl, j))

    # ---- 4. merge the same task done through different tools
    groups: dict[str, _Group] = {}
    fam_home: dict[tuple[str, ...], str] = {}
    for cl, tmpl, _j in kept:
        if tmpl is not None:
            g = groups.setdefault("t:" + str(tmpl["id"]), _Group(tmpl))
            g.clusters.append(cl)
    for key, g in groups.items():
        for fs in (V.family_signature(g.template["cogs"]), V.family_signature(g.main.medoid)):          # type: ignore[index]
            if "step" not in fs and len(fs) >= 3:
                fam_home.setdefault(fs, key)
    for cl, tmpl, _j in kept:
        if tmpl is None:
            fs = V.family_signature(cl.medoid)
            known = "step" not in fs and len(fs) >= 3        # steps of an unknown kind say nothing about being the same task
            groups.setdefault((fam_home.get(fs) if known else None) or ("f:" + "-".join(fs) if known else "c:" + "|".join(cl.medoid)), _Group(None)).clusters.append(cl)
    jmap = {id(cl): j for cl, _t, j in kept}

    # ---- 5. numbers, status, never, hidden
    marks = dict(hidden or {})
    rows: list[dict[str, Any]] = []
    automated: list[dict[str, Any]] = []
    hidden_out: list[dict[str, Any]] = []
    sigs: dict[str, tuple[str, ...]] = {}
    draws_by: dict[str, np.ndarray] = {}
    used: set[str] = set()
    for key in sorted(groups):
        g = groups[key]
        main = g.main
        sig = tuple(main.medoid)
        eps = sorted((e for cl in g.clusters for e in cl.episodes), key=lambda e: (e.t0, e.task_id))
        count = len(eps)
        rid = str(g.template["id"]) if g.template else auto_id(sig)
        view = lookup(rid, sig) if lookup else None
        if view is not None and view.status == "never":
            continue                                                  # the worker said never: it does not come back as a suggestion
        if only_ids is not None and (view.id if view is not None else rid) not in only_ids:
            continue
        j = sum(jmap[id(cl)] * cl.size for cl in g.clusters) / count
        var = sum(cl.mean_dist * cl.size for cl in g.clusters) / count
        durs = [e.duration for e in eps]
        point, lo, hi, d = _minutes(durs, count, weeks, j, cfg.draws, _seed(cfg.seed, rid))
        if round(point, 1) < cfg.min_minutes_saved:
            continue
        final = view.id if view is not None and view.id not in used else rid
        used.add(final)
        label, bold, fam = V.label_for(g.template, sig)
        prop = build_proposal(title=label, template=g.template, medoid=list(sig), count=count, span_days=observed_days,
                              hours=[lo * 4 / 60, hi * 4 / 60], horizon_weeks=4, risk_irreversible=pack.risk_irreversible)
        stops = (V.stops_for_never(prop["never"]) if g.template else
                 V.worst(V.step_risk(c) for c in sig))
        durs_sorted = sorted(durs)
        row = {
            "id": final, "label": label, "key": bold, "family": fam, "count": count,
            "minutes_per_week": _interval(point, lo, hi), "judgement_share": round(j, 2),
            "status": status_of(view), "stops_before": stops, "variation": round(var, 2), "variants": len(g.clusters),
            "overlaps": [], "seconds_per_time": round(float(np.median(durs_sorted)), 1) if durs_sorted else 0.0,
            "t": round(max(e.t1 for e in eps), 1),
            "actions": {"routine_id": view.id if view is not None else None, "can_automate": view is not None and view.status != "never",
                        "card_id": _card_id(person, final)},
            "what": prop["what"], "touches": list(prop["touches"]), "never": list(prop["never"]),
        }
        sigs[final] = sig
        draws_by[final] = d
        if row["status"] == "automated":
            automated.append(row)
            continue
        mark = _find_mark(marks, final, sig, cfg.same_task_distance)
        if mark is not None and count < cfg.hide_factor * int(mark.get("count") or 0):
            hidden_out.append({"id": final, "label": label, "count": count, "returns_at": int(np.ceil(cfg.hide_factor * int(mark.get("count") or 0)))})
            continue
        rows.append(row)

    # ---- 6. overlap: keep the one worth more, show the other as part of it
    rows.sort(key=_rank)
    dropped: set[str] = set()
    for i, a in enumerate(rows):
        if a["id"] in dropped:
            continue
        for b in rows[i + 1:]:
            if b["id"] in dropped:
                continue
            if _contains(sigs[a["id"]], sigs[b["id"]]):
                a["overlaps"].append({"id": b["id"], "label": b["label"], "relation": "includes"})
                dropped.add(b["id"])
            elif _contains(sigs[b["id"]], sigs[a["id"]]):
                a["overlaps"].append({"id": b["id"], "label": b["label"], "relation": "inside"})
                dropped.add(b["id"])
    rows = [r for r in rows if r["id"] not in dropped]

    # ---- 7. rank and cap
    automated.sort(key=_rank)
    shown = rows[:cfg.max_rows]
    not_shown = len(rows) - len(shown)
    held_list = [{"reason": r, "count": held[r]} for r in V.HELD_REASONS if held[r]]
    hidden_out.sort(key=lambda h: (-h["count"], h["id"]))
    if sig_out is not None:
        sig_out.update({r["id"]: sigs[r["id"]] for r in shown + automated})
    if shown:
        total_d = np.sum([draws_by[r["id"]] for r in shown], axis=0)
        lo, hi = (float(x) for x in np.quantile(total_d, [0.025, 0.975]))
        pt = sum(r["minutes_per_week"]["point"] for r in shown)
        lo, hi = min(lo, pt), max(hi, pt)
        # the hours figure keeps two decimals: 0.2 h and 0.25 h are different weeks
        total = {"actions": len(shown), "repeats": sum(r["count"] for r in shown), "minutes_per_week": _interval(pt, lo, hi),
                 "hours_per_week": {"point": round(pt / 60, 2), "lo": round(lo / 60, 2), "hi": round(hi / 60, 2)}}
        state, message = "ok", ""
    else:
        total = None
        if since is not None and not (automated or hidden_out or held_list):
            state, message = "counting_again", V.sentence_counting_again(iso(since)[:10])
        elif automated or hidden_out or held_list:
            state, message = "all_handled", V.sentence_all_handled()
        elif n_win < cfg.min_episodes_for_verdict:
            state, message = "too_little_data", V.sentence_too_little(n_win, window_days)
        else:
            state, message = "nothing_repeats", V.sentence_nothing(window_days)
    return {
        "state": state, "message": message, "window_days": window_days, "window_from": iso(start), "window_to": iso(now),
        "counting_since": iso(since) if since is not None else None, "episodes_in_window": n_win,
        "rows": shown, "automated": automated[:cfg.max_rows], "hidden": hidden_out, "held_back": held_list,
        "not_shown": not_shown, "total": total,
    }


def _rank(r: Mapping[str, Any]) -> tuple[float, int, str]:
    return (-round(float(r["minutes_per_week"]["point"]), 1), -int(r["count"]), str(r["id"]))


def _card_id(person: str, rid: str) -> str:
    """The id the proactive layer gives the automate card for this routine (``proactive.candidates.card_id``): same rule, no import."""
    import hashlib

    return "c_" + hashlib.sha1(f"{person}|automate|routine:{rid}".encode()).hexdigest()[:12]


def _find_mark(marks: Mapping[str, Mapping[str, Any]], rid: str, sig: tuple[str, ...], dist: float) -> Mapping[str, Any] | None:
    """A hide mark applies to the same id, or to the same unnamed routine seen again (the registry's own signature rule)."""
    if rid in marks:
        return marks[rid]
    for m in marks.values():
        s = tuple(m.get("signature") or ())
        if s and edit_distance(s, sig) <= dist:
            return m
    return None
