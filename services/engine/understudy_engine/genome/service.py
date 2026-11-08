"""Glue between the store and the genome maths: roster, cohort cache, the shapes the API returns."""
from __future__ import annotations

import json
import threading
from pathlib import Path
from dataclasses import dataclass

from ..cogs import segment_episodes
from ..core import AnalyticMeta
from ..store import EventStore
from .align import align
from .cohort import Cohort
from .decompose import decompose
from .graph import transition_graph
from .labels import components, deficit_prices, label_columns

TASK = "benefits-household-entry"
TASK_ALIASES = {TASK, "benefits", "benefits-processor", "benefits-household", "t_entitlement_check", "entitlement-check"}
APPRENTICE_TRUTH = ("synthetic", "apprentices", "truth.json")


def consequences_path() -> Path:
    from ..store.paths import evals_dir

    return evals_dir() / "cases" / "skip_consequences.json"


_ALIASES = {
    "step": ("step", "id", "skipped_step", "skip"),
    "p_error": ("p_error", "share", "share_changed", "p_outcome_changes", "p_changes_outcome", "p"),
    "mean_error_gbp": ("mean_error_gbp", "mean_error", "pound_error", "mean_gbp", "mean_abs_error_gbp"),
    "n": ("n", "n_households", "count"),
    "source": ("source", "note"),
}


def _pick(row: dict, key: str):
    for a in _ALIASES[key]:
        if a in row:
            return row[a]
    return None


SRC = "evals/cases/skip_consequences.json"
# the file's own fields copied beside the four standard keys (never typed here)
_CLIFF_EXTRAS = ("households_near_an_edge", "share_near", "share_near_ci95_wilson", "of_those_sites_disagree",
                 "material_threshold_gbp_per_month", "material_n", "material_share_of_near", "impact_gbp_per_month_among_near")


def _read_consequences() -> dict | None:
    p = consequences_path()
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _from_sets(doc: dict) -> list[dict]:
    """The platform's format: ``sets.<set>.{RECONCILE, CHECK_CLIFF}`` priced in answers. The largest set is used."""
    sets = doc["sets"]
    name = max(sets, key=lambda k: sets[k].get("n") or 0)
    st = sets[name]
    out: list[dict] = []
    rec = st.get("RECONCILE")
    if isinstance(rec, dict):
        pooled = rec.get("error_gbp_pooled_over_the_three_choices") or {}
        out.append({
            "step": "RECONCILE", "label": "Reconcile skipped", "p_error": rec.get("expected_wrong_share"),
            "p_error_ci95": rec.get("expected_wrong_share_ci95_bootstrap_by_household"),
            "mean_error_gbp": pooled.get("mean_when_wrong"), "n": rec.get("n", st.get("n")), "n_unit": st.get("n_unit", "households"),
            "source": f"{SRC}#sets.{name}.RECONCILE", "note": rec.get("sentence"), "skipped_means": rec.get("skipped_means"),
            "error_gbp": pooled or None,
        })
    cl = st.get("CHECK_CLIFF")
    if isinstance(cl, dict):
        # today's figure is unaffected by skipping the cliff check: the cost is an unwarned edge, so there is no p_error to give
        row = {
            "step": "CHECK_CLIFF", "label": "Cliff check skipped", "p_error": cl.get("p_error"), "mean_error_gbp": cl.get("mean_error_gbp"),
            "n": cl.get("of", st.get("n")), "n_unit": st.get("n_unit", "households"), "source": f"{SRC}#sets.{name}.CHECK_CLIFF",
            "note": cl.get("sentence"), "skipped_means": cl.get("skipped_means"),
        }
        row.update({k: cl[k] for k in _CLIFF_EXTRAS if k in cl})
        out.append(row)
    return out


def load_consequences() -> list[dict]:
    """What skipping a step costs in outcome terms (evals/cases/skip_consequences.json, written by the platform track):
    ``[{step, p_error, mean_error_gbp, n, source, ...}]``. Empty when the file does not exist or cannot be read. The waterfall
    prices a skipped step as seconds saved, which is arithmetically right but misleading without this. Every number comes from
    the file; a field the file does not define is None."""
    doc = _read_consequences()
    if doc is None:
        return []
    if isinstance(doc, dict) and isinstance(doc.get("sets"), dict) and doc["sets"]:
        return _from_sets(doc)
    rows = doc
    if isinstance(doc, dict):
        rows = next((doc[k] for k in ("consequences", "steps", "rows", "skips") if k in doc), None)
        if rows is None:
            rows = [{"step": k, **v} for k, v in doc.items() if isinstance(v, dict)]
    if isinstance(rows, dict):
        rows = [{"step": k, **v} for k, v in rows.items() if isinstance(v, dict)]
    out = []
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        step = _pick(r, "step")
        if step is None:
            continue
        out.append({
            "step": str(step), "p_error": _pick(r, "p_error"), "mean_error_gbp": _pick(r, "mean_error_gbp"),
            "n": _pick(r, "n"), "source": _pick(r, "source") or SRC,
        })
    return out


def load_consequences_meta() -> dict | None:
    doc = _read_consequences()
    return doc.get("meta") if isinstance(doc, dict) and isinstance(doc.get("meta"), dict) else None


class GenomeError(Exception):
    def __init__(self, code: str, message: str, status: int = 404):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


@dataclass
class Bundle:
    cohort: Cohort
    origin: str
    truth: dict | None
    key: tuple
    results: dict
    #: the task id the answers carry, and what they show: "cohort" (the apprentices' study: cohort figures beside one case) or "person" (a worker's own cases against the nearest
    #: experienced worker's, nothing about anyone else: the worker's own page)
    task: str = TASK
    scope: str = "cohort"


def role_for_task(task: str) -> str | None:
    """The role whose own cohort a task name asks for: a role pack id other than the benefits one (``programmer``, ``data-analyst``), or that pack's task id (``fix-a-failing-build``).
    None for the benefits task and everything else, which are read exactly as before."""
    if task in TASK_ALIASES or task.startswith("t_"):
        return None
    try:
        from ..memory import list_pack_ids, load_pack

        for rid in list_pack_ids():
            if rid == "benefits-processor":
                continue
            if task == rid or task == (load_pack(rid).persona or {}).get("task"):
                return rid
    except Exception:
        return None
    return None


def _truth_levels(truth: dict) -> dict[str, str]:
    return {p["person"]: p["level"] for p in truth["people"]}


class GenomeService:
    def __init__(self, store: EventStore | None = None):
        self.store = store or EventStore()
        self._bundles: dict[str, Bundle] = {}
        self._lock = threading.RLock()

    # ---------------------------------------------------------------- cohort
    def _stamp(self, partition: str) -> tuple:
        files = self.store.files(partition)
        extra = [self.store.root / "real" / "roster.json", self.store.root.joinpath(*APPRENTICE_TRUTH)]
        return tuple((str(p), p.stat().st_mtime_ns, p.stat().st_size) for p in files + [x for x in extra if x.exists()])

    def _load(self, partition: str) -> Bundle | None:
        truth = None
        if partition == "synthetic":
            tp = self.store.root.joinpath(*APPRENTICE_TRUTH)
            if not tp.exists():
                return None
            truth = json.loads(tp.read_text())
            levels = _truth_levels(truth)
        else:
            rp = self.store.root / "real" / "roster.json"
            if not rp.exists():
                return None
            levels = json.loads(rp.read_text())
        persons = set(levels)
        events = [e for e in self.store.read(partition) if e.person in persons]
        if not events:
            return None
        eps = segment_episodes(events)
        co = Cohort(eps, levels)
        if len({e.person for e in co.experts}) < 2 or len({e.person for e in co.novices}) < 2:
            return None
        return Bundle(co, partition, truth, self._stamp(partition), {})

    # ---------------------------------------------------------------- a role's own cohort (the worker's page)
    def _role_files(self, role: str) -> tuple[Path, Path]:
        d = self.store.root / "roles" / role / "cohort"
        return d / "roster.json", d / "events.jsonl"

    def _role_bundle(self, task: str, role: str) -> Bundle:
        """The cohort written for ``role`` (``<data>/roles/<role>/cohort/``: a roster of who is experienced and who is learning, and their cases of the role's main task, the worker's own among
        them). Answers carry the worker's own cases and the nearest experienced worker's way of doing the task, never anyone else's identity (scope ``person``)."""
        roster, ev = self._role_files(role)
        if not (roster.exists() and ev.exists()):
            raise GenomeError("no_cohort", f"There is no history for the {role} role yet: nothing to compare with an experienced worker's way of doing the task.")
        stamp = tuple((str(p), p.stat().st_mtime_ns, p.stat().st_size) for p in (roster, ev))
        with self._lock:
            b = self._bundles.get(f"role:{role}")
            if b is not None and b.key == stamp:
                return b
            from ..routines.sources import pack_mapping

            levels = json.loads(roster.read_text())
            events = [e for e in self.store.read_file(ev) if e.person in levels]
            co = Cohort(segment_episodes(events, pack_mapping(role)), levels)
            if len({e.person for e in co.experts}) < 2 or len({e.person for e in co.novices}) < 1:
                raise GenomeError("no_cohort", f"The {role} history has too few cases to compare.")
            b = Bundle(co, "synthetic", None, stamp, {}, task=task if role_for_task(task) else role, scope="person")
            self._bundles[f"role:{role}"] = b
            return b

    def bundle(self, task: str, partition: str | None = None) -> Bundle:
        role = role_for_task(task)
        if role is not None:
            return self._role_bundle(task, role)
        # one task exists (the benefits household entry); an episode id such as t_nov03a also resolves to its cohort
        if task not in TASK_ALIASES and not task.startswith("t_"):
            raise GenomeError("unknown_task", f"Unknown task {task!r}. Known: {TASK}.")
        order = [partition] if partition else ["real", "synthetic"]
        for part in order:
            with self._lock:
                stamp = self._stamp(part)
                b = self._bundles.get(part)
                if b is None or b.key != stamp:
                    b = self._load(part)
                    if b is not None:
                        self._bundles[part] = b
                if b is not None:
                    return b
        raise GenomeError(
            "no_cohort",
            "No expert/novice cohort found. Real data needs data/real/roster.json ({person: expert|novice}) with at least 2 of each; "
            "generated data needs `understudy synth --all`.",
        )

    # --------------------------------------------------------------- results
    def _cached(self, b: Bundle, key: str, fn):
        with self._lock:
            if key not in b.results:
                b.results[key] = fn()
            return b.results[key]

    def meta(self, b: Bundle, note: str) -> AnalyticMeta:
        co = b.cohort
        n = len({e.person for e in co.episodes})
        return AnalyticMeta(
            origin=b.origin, n=n, n_unit="people",
            split="descriptive; each case is compared with its nearest expert, never with itself; intervals are a cluster bootstrap by person (1000 draws)",
            note=note,
        )

    def default_person_episode(self, task: str = TASK, partition: str | None = None) -> tuple[str, str]:
        """The median-gap novice and their first case: what the ribbon and the replay show when nobody is named."""
        b = self.bundle(task, partition)
        if b.scope == "person":
            who = self._own(b, None)
            return who, sorted((e for e in b.cohort.episodes if e.person == who), key=lambda e: e.t0)[0].task_id
        real = self._cached(b, "real:nearest_expert", lambda: b.cohort.real_gap("nearest_expert"))
        pp = real["per_person"]
        person = sorted(pp, key=lambda p: pp[p])[len(pp) // 2]
        ep = sorted((e for e in b.cohort.episodes if e.person == person), key=lambda e: e.t0)[0]
        return person, ep.task_id

    def _own(self, b: Bundle, person: str | None) -> str:
        """The learner a person-scope answer is about: the one asked for, else the role cohort's only worker of this device (the learner of the cohort)."""
        from ..seedroles import PERSON

        learners = sorted({e.person for e in b.cohort.novices})
        if person is not None and person != PERSON:             # the other learners of the cohort are not reachable by id: this page is the worker's own
            raise GenomeError("unknown_person", f"No cases of this task for {person!r}.")
        return PERSON if PERSON in learners else learners[0]

    def _genome_person(self, b: Bundle, person: str | None, reference: str, episode: str | None) -> tuple[dict, AnalyticMeta]:
        """A worker's own cases of the role's main task against the nearest experienced worker's: their latest case aligned step by step, the seconds they lose by kind, and the gap of
        each case in order (the learning curve). Nothing here names or counts another person: the experienced worker is "the nearest", never an id."""
        co = b.cohort
        person = self._own(b, person)
        eps = sorted([e for e in co.episodes if e.person == person], key=lambda e: e.t0)
        if not eps:
            raise GenomeError("unknown_person", f"No cases of this task for {person!r}.")
        if co.levels.get(person) != "novice":
            raise GenomeError("not_a_novice", f"{person} has no learning cases in this role's history.", 422)
        if episode:
            eps_pick = [e for e in eps if e.task_id == episode]
            if not eps_pick:
                raise GenomeError("unknown_person", f"No case {episode!r} for {person!r}.")
            ep = eps_pick[0]
        else:
            ep = eps[-1]
        def against(e):
            if reference == "consensus":
                return co.consensus(), 0.0
            ref_ep, _ = co.nearest(e)
            return ref_ep.cogs, ref_ep.t0

        ref_cogs, ref_t0 = against(ep)
        al = align(ref_cogs, ep.cogs, co.cost)
        labels = label_columns(al)
        rows = al.as_rows()
        for r, lab in zip(rows, labels):
            r["label"] = lab
        comp = components(al)
        curve = []
        for i, e in enumerate(eps, start=1):
            rc, _t0 = against(e)
            curve.append({"case": i, "episode": e.task_id, "gap_s": round(align(rc, e.cogs, co.cost).gap_s, 3)})
        data = {
            "task": b.task, "person": person, "episode": ep.task_id, "reference": reference, "scope": "person",
            "expert": {"segments": [{"cog": c.id, "t0": round(c.t0 - ref_t0, 3), "t1": round(c.t1 - ref_t0, 3)} for c in ref_cogs]},
            "novice": {"segments": [{"cog": c.id, "t0": round(c.t0 - ep.t0, 3), "t1": round(c.t1 - ep.t0, 3)} for c in ep.cogs]},
            "alignment": rows, "person_gap_s": round(al.gap_s, 3),
            "person_waterfall": [{"label": k, "seconds": round(v, 3)} for k, v in sorted(comp.items(), key=lambda kv: -abs(kv[1]))],
            "cases": curve,
        }
        meta = AnalyticMeta(origin=b.origin, n=len(eps), n_unit="cases", split="descriptive; each case is set beside the nearest experienced worker's case of the same task",
                            note="Your own cases of this task, each set beside the nearest experienced worker's. The seconds are what the steps took, split by kind.")
        return data, meta

    def genome(self, task: str, person: str | None = None, reference: str = "nearest_expert", partition: str | None = None, episode: str | None = None) -> tuple[dict, AnalyticMeta]:
        if reference not in ("nearest_expert", "consensus"):
            raise GenomeError("bad_reference", "reference must be nearest_expert or consensus", 422)
        b = self.bundle(task, partition)
        if b.scope == "person":
            return self._genome_person(b, person, reference, episode)
        co = b.cohort
        real = self._cached(b, f"real:{reference}", lambda: co.real_gap(reference))
        wf = self._cached(b, f"wf:{reference}", lambda: co.waterfall(reference))
        placebo = self._cached(b, "placebo", co.placebo)
        null = self._cached(b, "null", lambda: co.null(observed=co.real_gap("nearest_expert")["gap_s"]))
        # which novice to show: asked for, else the median-gap novice (not cherry-picked)
        pp = real["per_person"]
        if person is None:
            ordered = sorted(pp, key=lambda p: pp[p])
            person = ordered[len(ordered) // 2]
        eps = sorted([e for e in co.episodes if e.person == person], key=lambda e: e.t0)
        if task.startswith("t_") and task not in TASK_ALIASES and task in co.by_task and not episode:
            episode = task                      # the caller named one case
        if episode:
            eps = [e for e in eps if e.task_id == episode]
        if not eps:
            raise GenomeError("unknown_person", f"No episodes for {person!r} in this cohort.")
        if co.levels.get(person) != "novice":
            raise GenomeError("not_a_novice", f"{person} is not a novice in this cohort; pick one of: {', '.join(sorted(pp))}.", 422)
        ep = eps[0]
        if reference == "consensus":
            ref_cogs, ref_person, ref_t0 = co.consensus(), None, 0.0
        else:
            ref_ep, _ = co.nearest(ep)
            ref_cogs, ref_person, ref_t0 = ref_ep.cogs, ref_ep.person, ref_ep.t0
        al = align(ref_cogs, ep.cogs, co.cost)
        labels = label_columns(al)
        rows = al.as_rows()
        for r, lab in zip(rows, labels):
            r["label"] = lab
        comp = components(al)
        dec = self._cached(b, "decomp", lambda: decompose(co.episodes, co.levels, B=300))
        data = {
            "task": TASK, "person": person, "episode": ep.task_id, "expert_person": ref_person, "reference": reference,
            "expert": {"segments": [{"cog": c.id, "t0": round(c.t0 - ref_t0, 3), "t1": round(c.t1 - ref_t0, 3)} for c in ref_cogs]},
            "novice": {"segments": [{"cog": c.id, "t0": round(c.t0 - ep.t0, 3), "t1": round(c.t1 - ep.t0, 3)} for c in ep.cogs]},
            "alignment": rows,
            "waterfall": wf["rows"],
            "total_gap_s": wf["total_gap_s"], "total_gap_ci": wf["total_gap_ci"],
            "controls": {
                "placebo": {"gap_s": placebo["gap_s"], "ci": placebo["ci"]},
                "null": {"gap_s": null["gap_s"], "ci": null["ci"], "p_value": null.get("p_value")},
            },
            # additive: this person's own case
            "person_gap_s": round(al.gap_s, 3),
            "person_waterfall": [{"label": k, "seconds": round(v, 3)} for k, v in sorted(comp.items(), key=lambda kv: -abs(kv[1]))],
            "people": {"novices": sorted(pp), "experts": sorted({e.person for e in co.experts})},
            "decomposition": {k: v for k, v in dec.items() if k != "statsmodels"},
        }
        cons = load_consequences()
        if cons:                                         # additive: what skipping a step does to the outcome, beside the seconds it saves
            data["consequences"] = cons
            cmeta = load_consequences_meta()
            if cmeta:
                data["consequences_meta"] = {k: cmeta[k] for k in ("origin", "n_unit", "interval_level", "interval_method", "oracle_label", "note") if k in cmeta}
        if b.truth is not None:
            tr = next(t for t in b.truth["traces"] if t["task_id"] == ep.task_id)
            rec = deficit_prices(comp)
            data["planted"] = [
                {"deficit": d["type"], "price_s": d["price_s"], "recovered_s": round(rec.get(d["type"], 0.0), 3)} for d in tr["deficits"]
            ]
        note = (
            "Scripted apprentices with planted deficits; the ribbon is one novice case against its nearest expert. "
            f"Waterfall = mean seconds lost per case over {len(pp)} novices vs {len({e.person for e in co.experts})} experts."
            if b.origin == "synthetic" else
            f"Real traces. n = {len(pp)} novices vs {len({e.person for e in co.experts})} experts; the interval is wide because n is small."
        )
        return data, self.meta(b, note)

    def transitions(self, task: str, person: str | None = None, partition: str | None = None) -> tuple[dict, AnalyticMeta]:
        b = self.bundle(task, partition)
        co = b.cohort
        if b.scope == "person":
            person = self._own(b, person)                    # the worker's own steps against the experienced workers' way, never the other learners'
        novices = co.novices if person is None else [e for e in co.novices if e.person == person]
        if not novices:
            raise GenomeError("unknown_person", f"No novice episodes for {person!r}.")
        g = transition_graph(co.experts, novices)
        if b.scope == "person":
            return g, AnalyticMeta(origin=b.origin, n=len(novices), n_unit="cases", split="descriptive; mean transitions per case, the experienced workers' way beside your own",
                                   note="Edges are mean transitions per case. missing_for_novice: the experienced workers take the edge, you take it less than 85% as often.")
        if b.truth is not None:
            planted = planted_missing_edges(b.truth)
            for e in g["edges"]:
                e["planted"] = (e["from"], e["to"]) in planted if e["missing_for_novice"] else None
        note = "Edges are mean transitions per case. missing_for_novice: experts take the edge, novices take it less than 85% as often."
        return g, self.meta(b, note + (" Scripted apprentices; `planted` marks edges broken by a planted deficit." if b.truth else ""))


def planted_missing_edges(truth: dict) -> set[tuple[str, str]]:
    """Expert-reference edges that some planted-deficit trace does not take (the ground truth for highlighting)."""
    ref = truth["expert_reference"]["sequence_A"]
    ref_edges = set(zip(ref, ref[1:]))
    out: set[tuple[str, str]] = set()
    for t in truth["traces"]:
        if t["level"] != "novice" or not any(d["instances"] for d in t["deficits"]):
            continue
        seq = [c for c, _, _ in t["cogs"]]
        out |= ref_edges - set(zip(seq, seq[1:]))
    return out
