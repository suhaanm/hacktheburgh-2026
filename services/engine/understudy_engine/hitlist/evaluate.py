"""Evaluation of the repeated-work hit list: ``evaluate_hitlist(fast=True) -> dict``. Pure compute, deterministic, no model, no network.

PLAN (written before the first run; there is no tuning here: every threshold below is the one in ``build.HitConfig`` as committed)
------------------------------------------------------------------------------------------------------------------------------
What this is. A check, on SYNTHETIC people, that the rules in ``build.py`` behave as designed: they find planted repeated routines, stay quiet on people
who have none, hold back what they should for the right reason, merge one task done through two tools, survive small data loss, give the same answer
every time, never break k-anonymity in the firm aggregate, and handle the edge cases. What it is not: no real person appears; the generators below were
written by the author of the rules, so planted routines are cleaner than real habits; dev seeds only (0 to 9), so there is NO held-out claim; nothing here
says workers find the list useful or that the minutes match what a real worker would save.

Worlds. Each person is an independent world made from a seed: 28 days of noise episodes (random cog sequences, about 5 a working day) and, where a
measure says so, planted routines inside the last 7 days. ``now`` is the end of the world. The unit is the person (clusters are people); rates carry
Wilson intervals (one independent world per person) and pooled quantities carry person-level bootstrap intervals. Full run: 10 dev seeds x 6 people = 60
people per cell; fast run: 4 seeds x 6 = 24.

Measures and what I expect before looking (an expectation is not a tuned target; a miss is reported as a miss):
1. RECALL of a planted routine at 3, 5 and 8 repeats in a 7 day window, with a 12% chance that a run has one slip, for two kinds: a routine the role pack
   names (``calc-entry-3x``) and one it does not (an unnamed sequence). A row counts as the planted routine when its steps are within edit distance 0.3 of
   the planted skeleton and its count is at least 60% of the planted runs. Expected: named at least 0.9 at every size; unnamed 0 at 3 repeats BY DESIGN (the
   rule asks 5 repeats on 2 days of a sequence the pack does not name) and at least 0.8 at 5 and 8.
2. FALSE ROWS on NULL people (noise only, no planted repeat): the share of people who get at least one row, windows 7 and 30 days, at the baseline noise
   (5 a day) and a busy one (12 a day). Target set by the lead: at most 5%; `met` is judged on the point estimate and the interval is shown.
3. HELD-BACK AUDIT: five planted routines, each alone in a noise-free world so the answer is exact: first step irreversible (a submit), first step outward (a
   letter), pack routine marked as needing judgement, a sequence that is mostly judgement, a pack routine whose tool is on the worker's denylist. Expected:
   in 100% of people no row is listed and the held-back list is exactly one entry with the right reason.
4. MERGING: calc-entry-3x done through two tools (half the runs with different but same-kind steps) must be ONE row with count within 2 of the runs; control:
   two different tasks must stay TWO rows. Expected: at least 0.9 for the merge, 1.0 for the control.
5. STABILITY under 5% loss: drop each step of each episode with probability 0.05 (event loss), and, separately, drop each episode with probability 0.05.
   Stable = the same top row (same task) and the same set of tasks; also the relative change in the top row's minutes. Expected: top row unchanged in at
   least 0.9 of people; minutes move by under 15% on average.
6. INTERVAL COVERAGE (not a hit list claim the lead asked for, but the interval is a number we print): with a known weekly rate (Poisson runs) and a known
   mean run time, does the 95% interval on minutes saved a week contain the true value? Expected: about 0.95; conditional on the row being listed (a
   selection effect, stated).
7. DETERMINISM and SHUFFLE INVARIANCE: the same input twice, and the episodes in a random order, give byte-identical answers. Expected: 100%.
8. FIRM K-ANONYMITY: across random firms with group sizes 1 to 12 (and the built-in firm), the number of listed rows with fewer than 5 people, and of
   person ids in the answer. Must be 0; the count of suppressed groups must equal the number of groups under 5.
9. EDGE CASES: a new user, no data in the window, capture off for a real person, a window longer than the history, counting again after a reset, a hidden
   row returning only when its count doubles, a routine the worker declined for good.

Limits stated up front: no real people; generators by the same author; dev seeds only; the held-back reason "too varied" and the ranking order are covered by
unit tests, not here; k-anonymity here is the group-size rule only (no defence against differencing across windows or role filters).
"""
from __future__ import annotations

import json
import math
import os
import random
import tempfile
import zlib
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

import numpy as np

from ..core import BASE_COGS, Cog, Episode
from ..memory.packinfo import PackView, load_pack
from ..routines.finder import edit_distance, skeleton
from ..trust.meta import analytic_meta
from . import firm as F
from .build import RoutineView, build_hitlist

DAY = 86400.0
NOW0 = datetime(2026, 11, 7, 18, 0, tzinfo=timezone.utc).timestamp()
ROLE = "benefits-processor"
PERSON = "p_eval"
DEV_SEEDS = tuple(range(10))
PER_SEED = 6
LEVEL = 0.95
SAME_TASK = 0.3                 # two step lists this close (normalised edit distance) are the same task

# the planted work (what a person does again and again). Step names are the benefits pack's own, or plain base cogs.
CALC = ("OPEN_CALCULATOR", "ENTER_HOUSEHOLD", "READ_RESULT") * 3            # the pack's calc-entry-3x
CALC_ALT = ("NAVIGATE", "ENTER_HOUSEHOLD", "READ") * 3                       # the same kinds of work through another tool
NOTE = ("READ_RESULT", "COPY_TO_NOTE", "READ_RESULT", "COPY_TO_NOTE")        # the pack's case-note-copy
QUEUE = ("NAVIGATE", "READ", "CHECK", "DECIDE") * 4                          # the pack's queue-sweep (needs judgement)
UNNAMED = (
    ("OPEN_CALCULATOR", "COPY", "READ_RESULT", "COPY", "OPEN_CALCULATOR", "COPY", "PASTE"),
    ("NAVIGATE", "ENTER", "COPY", "PASTE", "ENTER", "READ_RESULT", "COPY"),
    ("READ", "COPY", "OPEN_CALCULATOR", "ENTER_HOUSEHOLD", "COPY", "PASTE"),
)
SUBMIT_FIRST = ("SUBMIT_CASE", "READ_RESULT", "COPY_TO_NOTE", "READ_RESULT", "COPY_TO_NOTE")
LETTER_FIRST = ("SEND_LETTER", "READ_RESULT", "COPY_TO_NOTE", "READ_RESULT", "COPY_TO_NOTE")
MOSTLY_JUDGEMENT = ("SEARCH", "COMPARE", "DECIDE", "READ", "SEARCH", "DECIDE")
_DROPPED = {"IDLE", "REVERT", "REFORMULATE"}
_PACK: PackView | None = None


def _pack() -> PackView:
    global _PACK
    if _PACK is None:
        _PACK = load_pack(ROLE)
    return _PACK


def _rng(*parts: Any) -> random.Random:
    return random.Random(zlib.crc32(repr(parts).encode()))


# ------------------------------------------------------------------------------------------------ small statistics
def wilson(k: int, n: int, z: float = 1.959964) -> list[float]:
    if n <= 0:
        return [0.0, 1.0]
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(max(0.0, c - h), 4), round(min(1.0, c + h), 4)]


def rate(k: int, n: int) -> dict[str, Any]:
    return {"k": int(k), "n": int(n), "rate": round(k / n, 4) if n else None, "ci": wilson(k, n)}


def boot_mean(vals: Sequence[float], seed: int, B: int = 1000) -> dict[str, Any]:
    """Mean over people with a percentile bootstrap that resamples people."""
    a = np.asarray(vals, float)
    if a.size == 0:
        return {"n": 0, "mean": None, "ci": None}
    out: dict[str, Any] = {"n": int(a.size), "mean": round(float(a.mean()), 4), "ci": None}
    if a.size >= 2:
        idx = np.random.default_rng(seed).integers(0, a.size, size=(B, a.size))
        m = a[idx].mean(axis=1)
        out["ci"] = [round(float(np.quantile(m, 0.025)), 4), round(float(np.quantile(m, 0.975)), 4)]
    return out


def _pct(r: dict[str, Any]) -> str:
    return "n/a" if r["rate"] is None else f"{round(r['rate'] * 100)}% (95% interval {round(r['ci'][0] * 100)} to {round(r['ci'][1] * 100)}%, {r['k']} of {r['n']} people)"


# ------------------------------------------------------------------------------------------------ the synthetic worlds
@dataclass(frozen=True)
class Plant:
    """A routine a person repeats inside the last 7 days: an exact number of runs, or Poisson runs with a weekly mean."""

    seq: tuple[str, ...]
    runs: int | None = None
    weekly: float | None = None
    alt: tuple[str, ...] | None = None         # a second tool's version of the same steps, used for every other run
    slip: float = 0.12                         # chance a run has one extra or one missing step (never the first step)
    dur_s: float = 200.0                       # mean seconds a run takes
    sigma: float = 0.4
    tag: str = "p"


def _poisson(rng: random.Random, lam: float) -> int:
    L, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= L:
            return k
        k += 1


def _lognorm(rng: random.Random, mean: float, sigma: float) -> float:
    return max(8.0, math.exp(rng.gauss(math.log(mean) - sigma * sigma / 2, sigma)))


def _episode(seq: Sequence[str], t0: float, dur: float, tid: str) -> Episode:
    step = dur / len(seq)
    cogs = [Cog(t0 + i * step, t0 + (i + 1) * step, c) for i, c in enumerate(seq)]
    return Episode(task_id=tid, person=PERSON, role=ROLE, origin="synthetic", t0=t0, t1=t0 + dur, cogs=cogs)


def _skel(seq: Sequence[str]) -> tuple[str, ...]:
    return skeleton(_episode(seq, 0.0, 10.0, "s"))


def _noise_vocab() -> list[str]:
    return [c for c in BASE_COGS if c not in _DROPPED] + list(_pack().extra_cogs)


def make_world(rng: random.Random, plants: Sequence[Plant] = (), *, noise_per_day: float = 5.0, days: int = 28) -> list[Episode]:
    """Noise episodes over ``days`` days ending at ``NOW0`` and the planted routines inside the last 7 days."""
    vocab = _noise_vocab()
    eps: list[Episode] = []
    start = NOW0 - days * DAY
    for d in range(days):
        for j in range(_poisson(rng, noise_per_day)):
            seq = [rng.choice(vocab) for _ in range(rng.randint(3, 9))]
            eps.append(_episode(seq, start + d * DAY + rng.uniform(0, DAY - 700), _lognorm(rng, 60.0, 0.5), f"n{d}_{j}"))
    for pl in plants:
        n = pl.runs if pl.runs is not None else _poisson(rng, float(pl.weekly or 0.0))
        order = list(range(7))
        rng.shuffle(order)
        for i in range(n):
            day = order[i % 7] if pl.runs is not None else rng.randrange(7)          # the first runs fall on different days
            seq = list(pl.alt if (pl.alt and i % 2) else pl.seq)
            if rng.random() < pl.slip:
                pos = rng.randrange(1, len(seq))
                if rng.random() < 0.5:
                    seq.insert(pos, "CHECK")
                elif len(seq) > 3:
                    del seq[pos]
            t0 = NOW0 - 7 * DAY + day * DAY + rng.uniform(0, DAY - 700)
            eps.append(_episode(seq, t0, _lognorm(rng, pl.dur_s, pl.sigma), f"{pl.tag}{i}"))
    return eps


def hit(eps: Sequence[Episode], *, window: int = 7, **kw: Any) -> tuple[dict[str, Any], dict[str, tuple[str, ...]]]:
    sigs: dict[str, tuple[str, ...]] = {}
    d = build_hitlist(list(eps), _pack(), person=PERSON, now=NOW0, window_days=window, sig_out=sigs, **kw)
    return d, sigs


def _near(sig: Sequence[str], want: Sequence[str], dist: float = SAME_TASK) -> bool:
    return edit_distance(tuple(sig), tuple(want)) <= dist


def _people(fast: bool) -> list[tuple[int, int]]:
    seeds = DEV_SEEDS[:4] if fast else DEV_SEEDS
    return [(s, i) for s in seeds for i in range(PER_SEED)]


# ------------------------------------------------------------------------------------------------ the measures
def m_recall(people: list[tuple[int, int]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for kind in ("named", "unnamed"):
        cells: dict[str, Any] = {}
        for r in (3, 5, 8):
            k = 0
            for s, i in people:
                seq = CALC if kind == "named" else UNNAMED[(s + i) % len(UNNAMED)]
                eps = make_world(_rng("recall", kind, r, s, i), [Plant(tuple(seq), runs=r)])
                d, sigs = hit(eps)
                want = _skel(seq)
                k += any(_near(sigs[row["id"]], want) and row["count"] >= math.ceil(0.6 * r) for row in d["rows"])
            cells[str(r)] = rate(k, len(people))
        out[kind] = cells
    expect = {"named": {"3": 0.9, "5": 0.9, "8": 0.9}, "unnamed": {"3": 0.0, "5": 0.8, "8": 0.8}}
    out["expected"] = {"named": "at least 0.9 at 3, 5 and 8 repeats", "unnamed": "0 at 3 repeats by design (the rule asks 5 repeats on 2 days); at least 0.8 at 5 and 8"}
    out["met"] = {kind: {r: (out[kind][r]["rate"] <= 0.0 if (kind == "unnamed" and r == "3") else out[kind][r]["rate"] >= expect[kind][r]) for r in ("3", "5", "8")}
                  for kind in ("named", "unnamed")}
    return out


def m_null(people: list[tuple[int, int]]) -> dict[str, Any]:
    out: dict[str, Any] = {"target": "at most 5% of null people get any row"}
    for noise in (5.0, 12.0):
        worlds = [make_world(_rng("null", noise, s, i), [], noise_per_day=noise) for s, i in people]
        for window in (7, 30):
            rows = [len(hit(eps, window=window)[0]["rows"]) for eps in worlds]
            cell = rate(sum(1 for r in rows if r > 0), len(rows))
            cell["rows_per_person"] = round(sum(rows) / len(rows), 4)
            cell["met"] = cell["rate"] is not None and cell["rate"] <= 0.05
            out[f"noise_{int(noise)}_a_day_window_{window}"] = cell
    return out


def m_audit(people: list[tuple[int, int]]) -> dict[str, Any]:
    cases = {
        "irreversible_first_step": (Plant(SUBMIT_FIRST, runs=8, slip=0.0), None),
        "outward_first_step": (Plant(LETTER_FIRST, runs=8, slip=0.0), None),
        "judgement_pack_routine": (Plant(QUEUE, runs=10, slip=0.0), None),
        "judgement_share": (Plant(MOSTLY_JUDGEMENT, runs=8, slip=0.0), None),
        "denylist": (Plant(CALC, runs=8, slip=0.0), [{"kind": "app", "value": "GovCalc"}]),
    }
    reason = {"irreversible_first_step": "irreversible_first_step", "outward_first_step": "irreversible_first_step",
              "judgement_pack_routine": "judgement", "judgement_share": "judgement", "denylist": "denylist"}
    out: dict[str, Any] = {"expected": "every planted routine is held back with the right reason and nothing is listed (noise-free worlds, so the answer is exact)"}
    for name, (plant, deny) in cases.items():
        k = 0
        for s, i in people:
            d, _ = hit(make_world(_rng("audit", name, s, i), [plant], noise_per_day=0.0), denylist=deny or ())
            k += d["rows"] == [] and d["automated"] == [] and d["held_back"] == [{"reason": reason[name], "count": 1}]
        out[name] = {**rate(k, len(people)), "reason": reason[name]}
    return out


def m_merging(people: list[tuple[int, int]]) -> dict[str, Any]:
    want_a, want_b = _skel(CALC), _skel(CALC_ALT)
    merged = counts = 0
    for s, i in people:
        d, sigs = hit(make_world(_rng("merge", s, i), [Plant(CALC, runs=12, alt=CALC_ALT)]))
        task = [r for r in d["rows"] if _near(sigs[r["id"]], want_a) or _near(sigs[r["id"]], want_b)]
        merged += len(task) == 1
        counts += len(task) == 1 and 10 <= task[0]["count"] <= 14
    control = 0
    want_n = _skel(NOTE)
    for s, i in people:
        d, sigs = hit(make_world(_rng("merge-control", s, i), [Plant(CALC, runs=8), Plant(NOTE, runs=8)]))
        a = [r["id"] for r in d["rows"] if _near(sigs[r["id"]], want_a)]
        b = [r["id"] for r in d["rows"] if _near(sigs[r["id"]], want_n)]
        control += len(a) == 1 and len(b) == 1 and a[0] != b[0]
    return {"expected": "at least 0.9 for the merge; 1.0 for the control", "one_row_for_two_tools": rate(merged, len(people)),
            "count_within_2_of_planted": rate(counts, len(people)), "two_different_tasks_stay_two_rows": rate(control, len(people))}


def _lose_steps(eps: Sequence[Episode], rng: random.Random, p: float) -> list[Episode]:
    out = []
    for e in eps:
        keep = [c for c in e.cogs if rng.random() >= p] or e.cogs[:1]
        out.append(Episode(e.task_id, e.person, e.role, e.origin, e.t0, e.t1, list(keep)))
    return out


def _lose_episodes(eps: Sequence[Episode], rng: random.Random, p: float) -> list[Episode]:
    return [e for e in eps if rng.random() >= p]


def _same_set(a: dict[str, tuple[str, ...]], rows_a: list[dict[str, Any]], b: dict[str, tuple[str, ...]], rows_b: list[dict[str, Any]]) -> bool:
    return (all(any(_near(a[x["id"]], b[y["id"]]) for y in rows_b) for x in rows_a)
            and all(any(_near(b[y["id"]], a[x["id"]]) for x in rows_a) for y in rows_b))


def m_stability(people: list[tuple[int, int]]) -> dict[str, Any]:
    out: dict[str, Any] = {"expected": "top row unchanged in at least 0.9 of people; minutes move under 15% on average"}
    for name, lose in (("step_loss_5pct", _lose_steps), ("episode_loss_5pct", _lose_episodes)):
        top = same = base_n = 0
        change: list[float] = []
        for s, i in people:
            eps = make_world(_rng("stab", s, i), [Plant(CALC, runs=8), Plant(UNNAMED[(s + i) % len(UNNAMED)], runs=8)])
            d0, g0 = hit(eps)
            if not d0["rows"]:
                continue
            base_n += 1
            d1, g1 = hit(lose(eps, _rng("loss", name, s, i), 0.05))
            if d1["rows"] and _near(g0[d0["rows"][0]["id"]], g1[d1["rows"][0]["id"]]):
                top += 1
                change.append(abs(d1["rows"][0]["minutes_per_week"]["point"] - d0["rows"][0]["minutes_per_week"]["point"]) / max(d0["rows"][0]["minutes_per_week"]["point"], 1e-9))
            same += _same_set(g0, d0["rows"], g1, d1["rows"])
        out[name] = {"same_top_row": rate(top, base_n), "same_set_of_tasks": rate(same, base_n), "relative_change_in_top_minutes": boot_mean(change, seed=zlib.crc32(name.encode()))}
    return out


def m_coverage(people: list[tuple[int, int]]) -> dict[str, Any]:
    out: dict[str, Any] = {"expected": "about 0.95, conditional on the row being listed (a selection effect: a week with under 3 runs gives no row)"}
    for lam in (6.0, 12.0):
        k = n = 0
        for s, i in people:
            d, _ = hit(make_world(_rng("cover", lam, s, i), [Plant(CALC, weekly=lam, dur_s=200.0)]))
            row = next((r for r in d["rows"] if r["id"] == "calc-entry-3x"), None)
            if row is None:
                continue
            n += 1
            truth = lam * 200.0 / 60.0                  # runs a week x mean minutes a run x (1 - 0 judgement)
            k += row["minutes_per_week"]["lo"] <= truth <= row["minutes_per_week"]["hi"]
        out[f"weekly_rate_{int(lam)}"] = {**rate(k, n), "listed": rate(n, len(people)), "true_minutes_a_week": round(lam * 200.0 / 60.0, 1)}
    return out


def m_determinism(people: list[tuple[int, int]]) -> dict[str, Any]:
    same_twice = same_shuffled = 0
    for s, i in people:
        eps = make_world(_rng("det", s, i), [Plant(CALC, runs=8), Plant(UNNAMED[(s + i) % len(UNNAMED)], runs=8)])
        a = json.dumps(hit(eps)[0], sort_keys=True)
        b = json.dumps(hit(eps)[0], sort_keys=True)
        shuffled = list(eps)
        _rng("shuffle", s, i).shuffle(shuffled)
        c = json.dumps(hit(shuffled)[0], sort_keys=True)
        same_twice += a == b
        same_shuffled += a == c
    return {"expected": "100%", "same_input_twice": rate(same_twice, len(people)), "episodes_in_a_random_order": rate(same_shuffled, len(people))}


def m_kanon(seeds: Sequence[int]) -> dict[str, Any]:
    groups = small_groups = violations = leaks = wrong_suppressed = 0
    for s in seeds:
        rng = _rng("kanon", s)
        people: list[dict[str, Any]] = []
        n_small = n_groups = 0
        pid = 0
        for role in ("benefits-processor", "data-analyst", "programmer"):
            for a in range(6):
                m = rng.randint(1, 12)
                n_groups += 1
                n_small += m < 5
                for _ in range(m):
                    pt = rng.uniform(5.0, 90.0)
                    people.append({"person": f"secret_person_{s}_{pid}", "role": role, "rows": [{
                        "id": f"{role}-action-{a}", "label": f"Action {a}", "key": None, "family": "step", "count": rng.randint(3, 20),
                        "minutes_per_week": {"point": pt, "lo": pt * 0.7, "hi": pt * 1.3}, "stops_before": "none"}]})
                    pid += 1
        d = F.aggregate(people, 7)
        groups += n_groups
        small_groups += n_small
        violations += sum(1 for r in d["rows"] if r["people"] < d["min_group"])
        leaks += "secret_person" in json.dumps(d)
        wrong_suppressed += d["suppressed"] != n_small
    built = 0
    for w in (7, 30):
        d, _ = F.firm_hitlist(w)
        built += sum(1 for r in d["rows"] if r["people"] < d["min_group"]) + ("f_" in json.dumps(d) and '"person"' in json.dumps(d))
    return {"expected": "0 violations, 0 leaks, suppressed equals the number of groups under 5", "firms": len(seeds), "groups": groups, "groups_under_5": small_groups,
            "rows_listed_with_under_5_people": int(violations), "firms_with_a_person_id_in_the_answer": int(leaks), "firms_with_wrong_suppressed_count": int(wrong_suppressed),
            "built_in_firm_violations": int(built), "min_group": 5}


@contextmanager
def _env(values: dict[str, str]) -> Iterator[None]:
    old = {k: os.environ.get(k) for k in values}
    os.environ.update(values)
    try:
        yield
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _capture_off_case() -> dict[str, Any]:
    """A real person with no capture consent line: nothing is counted; with the line, the list appears. Uses a throw-away home and fakes the person source."""
    from unittest import mock

    eps = make_world(_rng("capture"), [Plant(CALC, runs=8)])
    with tempfile.TemporaryDirectory() as tmp:
        with _env({"UNDERSTUDY_HOME": os.path.join(tmp, "home"), "UNDERSTUDY_DATA_DIR": os.path.join(tmp, "data")}):
            from .. import routes_handoff as rh
            from . import service as S

            pd = SimpleNamespace(person=PERSON, origin="real", role=ROLE, t_last=NOW0)
            with mock.patch.object(rh, "_resolve", lambda person: (PERSON, pd)), mock.patch.object(rh, "_sync_routines", lambda *a, **k: None), \
                    mock.patch.object(rh, "_src", lambda: SimpleNamespace(episodes=lambda _pd: eps, load=lambda p: None)):
                off = S.compute(PERSON, 7, now=NOW0).data
                home = os.path.join(tmp, "home")
                os.makedirs(home, exist_ok=True)
                with open(os.path.join(home, "memory.md"), "w", encoding="utf-8") as fh:
                    fh.write("---\nrole: benefits-processor\nrevision: 1\n---\n\n## Preferences\n- Capture: times only  <!-- id:l_capture | you agreed -->\n")
                on = S.compute(PERSON, 7, now=NOW0).data
    return {"off_state": off["state"], "off_rows": len(off["rows"]), "on_state": on["state"], "on_rows": len(on["rows"])}


def m_edge_cases() -> dict[str, Any]:
    cases: list[dict[str, Any]] = []

    def case(name: str, expected: str, observed: Any, ok: bool) -> None:
        cases.append({"case": name, "expected": expected, "observed": observed, "pass": bool(ok)})

    d, _ = hit([])
    case("new user: no episodes at all", "state new_user, no rows", {"state": d["state"], "rows": len(d["rows"])}, d["state"] == "new_user" and not d["rows"])
    old = [_episode(CALC, NOW0 - 60 * DAY + i * 3600.0, 200.0, f"o{i}") for i in range(10)]
    d, _ = hit(old, window=7)
    case("history exists but nothing in the window", "no rows, a plain reason", {"state": d["state"], "rows": len(d["rows"])},
         not d["rows"] and d["state"] in ("too_little_data", "nothing_repeats") and bool(d["message"]))
    d, _ = hit([_episode(CALC, NOW0 - DAY, 200.0, "one")])
    case("one lone episode", "too little data, no crash", {"state": d["state"]}, d["state"] == "too_little_data" and not d["rows"])
    short = [_episode(CALC, NOW0 - 14 * DAY + i * (14 * DAY - 7200) / 11, 200.0, f"s{i}") for i in range(12)]
    d, _ = hit(short, window=30)
    got = d["rows"][0]["minutes_per_week"]["point"] if d["rows"] else None
    want = 12 / 2.0 * 200.0 / 60.0
    case("window longer than the history (14 days of data, 30 day window)", "minutes use the 14 days seen: about 20 min a week, within 15%",
         {"minutes_per_week": got, "expected_about": round(want, 1)}, got is not None and abs(got - want) / want <= 0.15)
    runs = [_episode(CALC, NOW0 - 3 * DAY + i * 4000.0, 200.0, f"r{i}") for i in range(8)]
    d, _ = hit(runs, reset_at=NOW0 - 0.5 * DAY)
    case("counting again after a reset", "state counting_again, no rows", {"state": d["state"], "rows": len(d["rows"])}, d["state"] == "counting_again" and not d["rows"])
    marks = {"calc-entry-3x": {"count": 6, "signature": []}}
    d11, _ = hit([_episode(CALC, NOW0 - 3 * DAY + i * 4000.0, 200.0, f"h{i}") for i in range(11)], hidden=marks)
    d12, _ = hit([_episode(CALC, NOW0 - 3 * DAY + i * 4000.0, 200.0, f"h{i}") for i in range(12)], hidden=marks)
    case("a hidden row returns only when its count doubles", "hidden at 11, listed at 12 (mark was 6)", {"at_11": len(d11["rows"]), "at_12": len(d12["rows"])},
         not d11["rows"] and len(d12["rows"]) == 1)
    d, _ = hit(runs, lookup=lambda rid, sig: RoutineView(rid, "never"))
    case("a routine the worker declined for good", "not listed, not in the automated fold", {"rows": len(d["rows"]), "automated": len(d["automated"])}, not d["rows"] and not d["automated"])
    d, _ = hit(runs, lookup=lambda rid, sig: RoutineView(rid, "approval", "A2"))
    case("a routine already automated", "in the automated fold, not in the rows", {"rows": len(d["rows"]), "automated": len(d["automated"])}, not d["rows"] and len(d["automated"]) == 1)
    try:
        cap = _capture_off_case()
        case("capture off for a real person", "no rows until the capture line exists, then the list appears", cap,
             cap["off_state"] == "capture_off" and cap["off_rows"] == 0 and cap["on_state"] == "ok" and cap["on_rows"] == 1)
    except Exception as exc:                                                       # a broken sibling module must show as a failed case, not a crash
        case("capture off for a real person", "no rows until the capture line exists, then the list appears", f"{type(exc).__name__}: {exc}"[:200], False)
    return {"cases": cases, "passed": rate(sum(1 for c in cases if c["pass"]), len(cases))}


# ------------------------------------------------------------------------------------------------ the whole evaluation
LIMITATIONS = [
    "Synthetic people only: nobody in this evaluation is a person. The generators were written by the author of the rules, so planted routines are cleaner than real habits (exact step lists, a small chance of one slip).",
    "Dev seeds 0 to 9 only. There is no held-out claim: nothing here was run on seeds kept apart from the code, and the numbers are what the rules do on worlds their author could inspect.",
    "Recall is for routines that are present, repeated inside one 7 day window and made of steps the finder can separate; it says nothing about habits spread over many windows or tangled with other work.",
    "The false-row rate is for noise made of random step lists. Real work has habits that are not routines worth automating, so a real null rate could be higher.",
    "The held-back audit uses noise-free worlds so the answer is exact; with noise, a held-back count also includes chance clusters. The reason 'too varied' and the ranking order are covered by unit tests, not here.",
    "The 95% interval on minutes is checked against a known rate and mean run time, conditional on the row being listed. It does not say whether the run time a real worker would save equals the time spent (the judgement share is a pack setting, not a measurement).",
    "K-anonymity here is the group-size rule (fewer than 5 people are not listed). It does not defend against differencing across windows or role filters, and the synthetic firm is not a real workforce; a real deployment needs a lawful basis and a notice to workers (D41).",
    "Nothing here shows that workers find the list useful or that Automate leads to better work; the study is a separate piece of work.",
]


def _claims(r: dict[str, Any]) -> list[str]:
    rec, nul, aud, mer, sta, cov, det, kan, edg = r["recall"], r["null"], r["audit"], r["merging"], r["stability"], r["interval_coverage"], r["determinism"], r["k_anonymity"], r["edge_cases"]
    c = [
        f"Routines the role pack names were listed in {_pct(rec['named']['3'])} of people at 3 repeats, {_pct(rec['named']['5'])} at 5 and {_pct(rec['named']['8'])} at 8.",
        f"A routine the pack does not name was listed in {_pct(rec['unnamed']['3'])} at 3 repeats (the rule asks for 5, by design), {_pct(rec['unnamed']['5'])} at 5 and {_pct(rec['unnamed']['8'])} at 8.",
        f"On people with no planted repeat, {_pct(nul['noise_5_a_day_window_7'])} got a row in a 7 day window and {_pct(nul['noise_5_a_day_window_30'])} in a 30 day window at the baseline noise "
        f"(target at most 5%: {'met' if nul['noise_5_a_day_window_7']['met'] and nul['noise_5_a_day_window_30']['met'] else 'NOT met'}); at the busy noise {_pct(nul['noise_12_a_day_window_7'])} and {_pct(nul['noise_12_a_day_window_30'])}.",
        "Held back with the right reason and nothing listed: " + ", ".join(f"{k.replace('_', ' ')} {round(v['rate'] * 100)}%" for k, v in aud.items() if isinstance(v, dict) and "rate" in v) + ".",
        f"One task through two tools became one row in {_pct(mer['one_row_for_two_tools'])}; two different tasks stayed two rows in {_pct(mer['two_different_tasks_stay_two_rows'])}.",
        f"With 5% of steps lost the top row stayed the same in {_pct(sta['step_loss_5pct']['same_top_row'])}; with 5% of episodes lost, {_pct(sta['episode_loss_5pct']['same_top_row'])}.",
        f"The 95% interval on minutes a week held the true value in {_pct(cov['weekly_rate_6'])} (6 runs a week) and {_pct(cov['weekly_rate_12'])} (12 a week), among rows that were listed.",
        f"The same input gave byte-identical answers in {_pct(det['same_input_twice'])}, and in a random order in {_pct(det['episodes_in_a_random_order'])}.",
        f"Across {kan['firms']} synthetic firms ({kan['groups']} groups, {kan['groups_under_5']} under 5 people) {kan['rows_listed_with_under_5_people']} rows with fewer than 5 people were listed "
        f"and {kan['firms_with_a_person_id_in_the_answer']} answers held a person id.",
        f"Edge cases passed: {edg['passed']['k']} of {edg['passed']['n']}.",
    ]
    return c


def _exp(measure: str, expected: str, observed: str, met: bool) -> dict[str, Any]:
    return {"measure": measure, "expected": expected, "observed": observed, "met": bool(met)}


def _expectations(r: dict[str, Any]) -> list[dict[str, Any]]:
    """The expectations written in the PLAN before the first run, each checked against the numbers. A miss is a miss: it is listed, and named in the statement."""
    out: list[dict[str, Any]] = []
    for kind, sizes in (("named", ("3", "5", "8")), ("unnamed", ("3", "5", "8"))):
        for n in sizes:
            c = r["recall"][kind][n]
            floor = kind == "unnamed" and n == "3"
            out.append(_exp(f"recall, {kind} routine, {n} repeats", "0 by design (5 repeats are asked for)" if floor else ("at least 0.9" if kind == "named" else "at least 0.8"),
                            f"{c['k']} of {c['n']}", (c["rate"] == 0.0) if floor else (c["rate"] >= (0.9 if kind == "named" else 0.8))))
    for name, c in r["null"].items():
        if isinstance(c, dict) and "rate" in c:
            out.append(_exp(f"false rows on null people, {name.replace('_', ' ')}", "at most 5% of people", f"{c['k']} of {c['n']}", c["rate"] <= 0.05))
    for name, c in r["audit"].items():
        if isinstance(c, dict) and "rate" in c:
            out.append(_exp(f"held back with the right reason, {name.replace('_', ' ')}", "100%", f"{c['k']} of {c['n']}", c["rate"] == 1.0))
    m = r["merging"]
    out.append(_exp("one task through two tools is one row", "at least 0.9", f"{m['one_row_for_two_tools']['k']} of {m['one_row_for_two_tools']['n']}", m["one_row_for_two_tools"]["rate"] >= 0.9))
    out.append(_exp("two different tasks stay two rows", "1.0", f"{m['two_different_tasks_stay_two_rows']['k']} of {m['two_different_tasks_stay_two_rows']['n']}", m["two_different_tasks_stay_two_rows"]["rate"] == 1.0))
    for name in ("step_loss_5pct", "episode_loss_5pct"):
        st = r["stability"][name]
        out.append(_exp(f"top row unchanged, {name.replace('_', ' ')}", "at least 0.9", f"{st['same_top_row']['k']} of {st['same_top_row']['n']}", st["same_top_row"]["rate"] is not None and st["same_top_row"]["rate"] >= 0.9))
        chg = st["relative_change_in_top_minutes"]["mean"]
        out.append(_exp(f"minutes of the top row, {name.replace('_', ' ')}", "move under 15% on average", "n/a" if chg is None else f"{round(chg * 100, 1)}%", chg is not None and chg < 0.15))
    for name, c in r["interval_coverage"].items():
        if isinstance(c, dict) and "rate" in c:
            out.append(_exp(f"95% interval holds the true minutes, {name.replace('_', ' ')}", "about 0.95 (the 95% interval of the coverage contains 0.95)", f"{c['k']} of {c['n']}", c["ci"][0] <= 0.95 <= c["ci"][1]))
    for name, c in r["determinism"].items():
        if isinstance(c, dict) and "rate" in c:
            out.append(_exp(f"determinism, {name.replace('_', ' ')}", "100%", f"{c['k']} of {c['n']}", c["rate"] == 1.0))
    k = r["k_anonymity"]
    bad = k["rows_listed_with_under_5_people"] + k["firms_with_a_person_id_in_the_answer"] + k["firms_with_wrong_suppressed_count"] + k["built_in_firm_violations"]
    out.append(_exp("firm aggregate k-anonymity", "0 violations", f"{bad} violations in {k['groups']} groups", bad == 0))
    e = r["edge_cases"]["passed"]
    out.append(_exp("edge cases", "all pass", f"{e['k']} of {e['n']}", e["k"] == e["n"]))
    return out


def _statement(r: dict[str, Any]) -> str:
    ex = r["expectations"]
    missed = [x for x in ex if not x["met"]]
    base = ("Synthetic worlds written by the author of the rules, dev seeds only, no held-out claim. "
            f"{len(ex) - len(missed)} of {len(ex)} expectations written before the run were met.")
    if missed:
        base += " Missed: " + "; ".join(f"{x['measure']} ({x['observed']}, expected {x['expected']})" for x in missed) + "."
    return base + " " + " ".join(r["claims"][:3]) + " See limitations for what this does not show."


def evaluate_hitlist(fast: bool = True, **_kw: Any) -> dict[str, Any]:
    """Run the measures in the PLAN at the top of this module. ``fast`` uses 4 dev seeds x 6 people per cell (about 24); the full run uses 10 x 6 = 60. Deterministic."""
    people = _people(fast)
    seeds = DEV_SEEDS[:4] if fast else DEV_SEEDS
    res: dict[str, Any] = {"status": "ok"}
    res["recall"] = m_recall(people)
    res["null"] = m_null(people if not fast else people[:18])
    res["audit"] = m_audit(people[:12] if fast else people[:30])
    res["merging"] = m_merging(people)
    res["stability"] = m_stability(people)
    res["interval_coverage"] = m_coverage(people)
    res["determinism"] = m_determinism(people[:10] if fast else people[:20])
    res["k_anonymity"] = m_kanon(seeds)
    res["edge_cases"] = m_edge_cases()
    res["claims"] = _claims(res)
    res["expectations"] = _expectations(res)
    res["expectations_met"] = rate(sum(1 for x in res["expectations"] if x["met"]), len(res["expectations"]))
    res["statement"] = _statement(res)
    res["limitations"] = LIMITATIONS
    res["meta"] = analytic_meta("synthetic", len(people), "synthetic people per cell",
                                f"dev seeds {list(seeds)} x {PER_SEED} people; no held-out seeds", note="Synthetic worlds; dev seeds only; no held-out claim (see limitations).")
    return res


if __name__ == "__main__":  # pragma: no cover
    import sys

    print(json.dumps(evaluate_hitlist(fast="--full" not in sys.argv), indent=1, sort_keys=True, default=str))
