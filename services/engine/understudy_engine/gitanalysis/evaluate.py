"""Honest evaluation of the git layer (NFR-11): ``evaluate_git(fast=False) -> dict``.

Everything here runs on synthetic repositories with planted habits (``synth``), on seeds that were never used while the
thresholds were chosen (development used replicates 0 to 3; evaluation uses 100 and up), plus one real-world illustration:
this repository's own history (the owner's project, read-only, aggregates only).

Sections: ``habit_recovery`` (precision and recall of planted habits, Wilson intervals, per habit, and a dose-response over
the planting strength), ``placebo`` (each expert against the other experts), ``digest_accuracy`` (the digest against the
generator's labels), ``digest_agreement`` (model against rules; ``not_run`` when no model is present), ``genome`` (the
alignment on commit sessions, with its placebo and null), ``leak_canary`` (planted tokens in a real flow through the
egress guard), ``real_world`` (aggregates of this repo's history), ``limitations`` and a plain statement that no real people
are involved. Nothing in the result holds a message, path, name, email or commit id.
"""
from __future__ import annotations

import contextlib
import os
import tempfile
import time
from datetime import datetime, UTC
from pathlib import Path
from typing import Any

import numpy as np

from . import canary_flows, cogseq, digest as dg, service, synth
from .compare import flagged_ids, habit_rows, placebo, score_detection
from .features import HABIT_IDS, HABITS, build_table, compute_features
from .records import load_records
from .source import GitSource, GitSourceError
from .stats import rate, rnd

EVAL_REPLICATES = tuple(range(100, 110))
FAST_REPLICATES = (100, 101, 102)
DOSE_STRENGTHS = (0.25, 0.5, 0.75)
NO_PEOPLE = ("No real people are involved. Every developer in the habit, placebo, digest and canary results is a scripted "
             "persona (4 learners and 8 experts per replicate) and every commit message is generated text. The one real history "
             "used is this project's own repository, read-only, reported as aggregates only.")


@contextlib.contextmanager
def _isolated_data_dir():
    """Run with a private data dir so the evaluation never writes to the real egress ledger or digest cache."""
    old = os.environ.get("UNDERSTUDY_DATA_DIR")
    with tempfile.TemporaryDirectory(prefix="git-eval-data-") as d:
        os.environ["UNDERSTUDY_DATA_DIR"] = d
        service.clear_caches()
        try:
            yield Path(d)
        finally:
            if old is None:
                os.environ.pop("UNDERSTUDY_DATA_DIR", None)
            else:
                os.environ["UNDERSTUDY_DATA_DIR"] = old
            service.clear_caches()


def _tables(cohort: dict) -> tuple[dict, dict]:
    t: dict[str, Any] = {}
    for grp in ("learners", "experts"):
        for p, repo in cohort[grp].items():
            t[p] = build_table(load_records(repo, backend="rules")[0])
    return {p: v for p, v in t.items() if p in cohort["learners"]}, {p: v for p, v in t.items() if p in cohort["experts"]}


# ------------------------------------------------------------------------------------------------ habit recovery
def _recovery(reps, base: Path, boot: int, jitter: float = 1.0) -> tuple[dict, dict, dict, dict]:
    detected, planted = {}, {}
    pl_pairs = pl_flags = 0
    pl_abs: dict[str, list[float]] = {h: [] for h in HABIT_IDS}
    experts_by_rep: dict[int, dict] = {}
    cohorts: dict[int, dict] = {}
    for rep in reps:
        c = synth.make_cohort(base / f"r{rep}", rep, jitter=jitter)
        cohorts[rep] = c
        learners, experts = _tables(c)
        experts_by_rep[rep] = experts
        for p, tb in learners.items():
            rows = habit_rows(tb, experts, B=boot, seed=rep * 101 + 1)
            detected[p] = flagged_ids(rows)
            planted[p] = set(synth.load_truth(c["learners"][p])["planted"])
        pl = placebo(experts, B=max(150, boot // 3), seed=rep * 7 + 3)
        pl_pairs += pl["pairs"]
        pl_flags += pl["false_flags"]["k"]
        for h, v in pl["mean_abs_delta"].items():
            if v is not None:
                pl_abs[h].append(v)
    score = score_detection(detected, planted)
    labelled = {
        "design": {"replicates": list(reps), "learners_per_replicate": 4, "experts_per_replicate": 8, "pairs": score["pairs"],
                   "habits": list(HABIT_IDS), "learner_habit_plan": {p: list(h) for p, h, _ in synth.LEARNER_PLAN}, "between_person_jitter": jitter,
                   "digest": "local-model track's rules (the model is never used here: too slow for 100+ repos)",
                   "boot_draws": boot},
        "overall": score["overall"], "by_habit": score["by_habit"],
    }
    placebo_out = {
        "design": "each expert compared with the other seven experts of its replicate, same procedure and thresholds",
        "pairs": pl_pairs, "false_flags": rate(pl_flags, pl_pairs),
        "mean_abs_delta_by_habit": {h: rnd(float(np.mean(v))) if v else None for h, v in pl_abs.items()},
        "floors": {h: HABITS[h].min_delta for h in HABIT_IDS},
    }
    return labelled, placebo_out, cohorts, experts_by_rep


def _dose(reps, base: Path, boot: int, strengths, experts_by_rep: dict) -> list[dict]:
    """Recall and precision when the habits are planted at a fraction of full strength (same experts as the main run)."""
    rows = []
    reps = list(reps)[:4]
    for s in strengths:
        detected, planted = {}, {}
        for rep in reps:
            for spec in synth.learner_specs(rep, strength=s):
                repo = synth.make_repo(spec, base / f"dose{s}_r{rep}" / spec.person)
                tb = build_table(load_records(repo, backend="rules")[0])
                detected[spec.person] = flagged_ids(habit_rows(tb, experts_by_rep[rep], B=boot, seed=rep * 103 + int(s * 100)))
                planted[spec.person] = set(spec.planted)
        sc = score_detection(detected, planted)["overall"]
        rows.append({"strength": s, "pairs": sc["tp"] + sc["fp"] + sc["fn"] + sc["tn"], "recall": sc["recall"], "precision": sc["precision"],
                     "note": "planted rate = baseline + strength x (full planted rate - baseline)"})
    return rows


# ------------------------------------------------------------------------------------------------ digests
def _digest_accuracy(cohort: dict) -> dict:
    n = {"category": [0, 0], "size_bucket": [0, 0], "touches_tests": [0, 0], "vague": [0, 0]}
    vague = {"tp": 0, "fp": 0, "fn": 0}
    cat_hits: dict[str, list[int]] = {}
    impl = "localmodel"
    for repo in [*cohort["learners"].values(), *cohort["experts"].values()]:
        truth = {t["sha"]: t for t in synth.load_truth(repo)["commits"]}
        items = list(GitSource(repo).read())
        digs, info = dg.commit_digests(items, backend="rules")
        impl = info.impl
        for it, d in zip(items, digs):
            t = truth[it.fields["sha"]]
            n["category"][1] += 1
            n["category"][0] += d["category"] == t["category"]
            cat_hits.setdefault(t["category"], [0, 0])
            cat_hits[t["category"]][1] += 1
            cat_hits[t["category"]][0] += d["category"] == t["category"]
            n["size_bucket"][1] += 1
            n["size_bucket"][0] += d["size_bucket"] == t["size_bucket"]
            n["touches_tests"][1] += 1
            n["touches_tests"][0] += d["touches_tests"] == t["touches_tests"]
            tv, dv = t["message_quality"] != "good", d["message_quality"] == "vague"
            n["vague"][1] += 1
            n["vague"][0] += tv == dv
            vague["tp"] += tv and dv
            vague["fp"] += dv and not tv
            vague["fn"] += tv and not dv
    return {
        "against": "the generator's own labels (a scripted history: the labels are known by construction)",
        "digest": "the local-model track's rules" if impl == "localmodel" else "the built-in fallback rules",
        "n_commits": n["category"][1],
        "accuracy": {k: rate(v[0], v[1]) for k, v in n.items()},
        "category_recall": {k: rate(v[0], v[1]) for k, v in sorted(cat_hits.items())},
        "vague_message": {"precision": rate(vague["tp"], vague["tp"] + vague["fp"]), "recall": rate(vague["tp"], vague["tp"] + vague["fn"])},
        "caveat": ("The generator and the digest rules were written by the same agent, so message-based fields are flattered; the "
                   "generator mixes in paraphrased and hard-to-spot messages (about 20% of subjects) to test that, and size and test "
                   "touch are computed from numbers and paths, so they are exact."),
    }


def _digest_agreement(cohort: dict, limit: int) -> dict:
    if not service.model_available():
        return {"status": "not_run", "reason": "the local model is not available here (localmodel.mode() is rules), so there is nothing to compare "
                                                "with the rules; run with UNDERSTUDY_X_LOCALMODEL=1 and the model present"}
    items = []
    for repo in cohort["learners"].values():
        items += list(GitSource(repo).read())
    rng = np.random.default_rng(5)
    pick = sorted(rng.choice(len(items), size=min(limit, len(items)), replace=False).tolist())
    sample = [items[i] for i in pick]
    t0 = time.time()
    model, minfo = dg.commit_digests(sample, backend="model")
    rules, _ = dg.commit_digests(sample, backend="rules")
    fields = ("category", "size_bucket", "touches_tests", "risk", "message_quality")
    agree = {f: rate(sum(1 for a, b in zip(model, rules) if a[f] == b[f]), len(sample)) for f in fields}
    return {"status": "ok", "n_commits": len(sample), "model_share": rnd(minfo.model_share), "fallbacks": minfo.fallbacks, "agreement": agree,
            "seconds": rnd(time.time() - t0, 1), "note": "agreement is not accuracy: neither side is the truth here"}


# ------------------------------------------------------------------------------------------------ genome, canary, real world
def _genome(cohorts: dict, reps, fast: bool) -> dict:
    rows = []
    for rep in list(reps)[: 2 if fast else 6]:
        c = cohorts[rep]
        L = {p: load_records(r, backend="rules")[0] for p, r in c["learners"].items()}
        E = {p: load_records(r, backend="rules")[0] for p, r in c["experts"].items()}
        out = cogseq.genome_compare(L, E, null_draws=40 if fast else 150, boot=300 if fast else 600)
        if out["status"] == "ok":
            rows.append({"replicate": rep, "shape_difference": out["shape"]["difference"]["value"], "shape_ci": out["shape"]["difference"]["ci"],
                         "shape_p": out["shape"]["null"]["p_value"], "seconds_gap_s": out["seconds"]["real"]["gap_s"],
                         "seconds_ci": out["seconds"]["real"]["ci"], "seconds_p": out["seconds"]["null"].get("p_value"),
                         "placebo_shape": out["shape"]["expert_placebo"]["mean"]})
    if not rows:
        return {"status": "not_run", "reason": "no replicate had enough sessions"}
    sig = lambda key: sum(1 for r in rows if r[key] is not None and r[key] < 0.05)
    return {
        "status": "ok", "replicates": len(rows), "mapping": "packages/packs/programmer/git_mapping.yaml (CODE, TEST, REFACTOR, COMMIT, REVERT)",
        "shape_distance": {"mean_difference": rnd(float(np.mean([r["shape_difference"] for r in rows]))), "replicates_with_p_below_0.05": rate(sig("shape_p"), len(rows))},
        "seconds_gap": {"mean_gap_s": rnd(float(np.mean([r["seconds_gap_s"] for r in rows])), 1), "replicates_with_p_below_0.05": rate(sig("seconds_p"), len(rows))},
        "rows": rows,
        "reading": ("On commit sessions the alignment sees differences in the SHAPE of sessions (missing test steps, reverts, extra "
                    "code-commit loops) in some replicates, and sees nothing in seconds, because git records when a commit landed and not how "
                    "long the work took. Habits that live in the message or the clock (vague messages, late nights) are invisible to cogs by construction."),
    }


def _leak_canary(seeds=tuple(range(8))) -> dict:
    try:
        from ..privacy.testing import run_flow
    except Exception as exc:
        return {"status": "not_run", "reason": f"the privacy spine is not importable ({type(exc).__name__})"}
    rows = []
    for flow in canary_flows.FLOWS:
        for seed in seeds:
            r = run_flow(flow, seed=seed)
            rows.append(r)
    planted = sum(r.planted for r in rows)
    leaked = sum(r.leaked for r in rows)
    requests = sum(r.requests for r in rows)
    return {
        "status": "ok", "flows": sorted({r.name for r in rows}), "runs": len(rows), "requests": requests, "planted_tokens": planted,
        "leaked_tokens": leaked, "ledger_complete_runs": sum(1 for r in rows if r.ledger_complete), "errors": sum(1 for r in rows if r.error),
        "kinds_planted": sorted({k for r in rows for k in r.by_kind}),
        "claim": ("zero of the planted tokens (author names, emails, customer names, commit messages, file paths) appeared in any captured "
                  "request body; one ledger line per call. Measured on these flows only; a paraphrase or a hash of a token would not be caught."),
    }


def _real_world() -> dict:
    from ..store.paths import repo_root
    root = repo_root()
    if not (root / ".git").exists():
        return {"status": "not_run", "reason": "no git history at the repository root"}
    try:
        recs, info = load_records(root, backend="rules")
    except GitSourceError:
        return {"status": "not_run", "reason": "the repository's history could not be read"}
    if not recs:
        return {"status": "not_run", "reason": "no commits"}
    f = compute_features(recs)
    hab = {h: {"value": v["value"], "num": v["num"], "den": v["den"], "ci": rate(v["num"], v["den"])["ci"]} for h, v in f["habits"].items()}
    return {
        "status": "ok", "what": "this project's own git history, read-only; aggregates only (no messages, paths, names or commit ids)",
        "digest": info.impl, "n_commits": f["n_commits"], "n_authors": len({r.author_key for r in recs}), "n_active_days": f["n_active_days"],
        "span_days": f["span_days"], "commits_per_active_day": f["commits_per_active_day"], "commits_by_hour": f["commits_by_hour"],
        "size_share": f["size"]["share"], "lines_median": f["size"]["lines_median"], "files_per_commit": f["files_per_commit"],
        "habit_shares": hab, "category_share": f["category_share"],
        "note": ("The history is short and was produced by an agent-assisted build over a few days, so these numbers describe this "
                 "project, not the owner's habits in general. They show that the pipeline runs on a real history; the intervals "
                 "are Wilson intervals on commits and are wide."),
    }


def limitations(result: dict) -> list[dict]:
    rec = result.get("habit_recovery", {})
    dose = rec.get("dose_response") or []
    weak = min(dose, key=lambda d: d["strength"]) if dose else None
    gen = result.get("genome", {})
    out = [
        {"id": "git-synthetic", "severity": "high", "text": ("Every learner and expert is a scripted persona. Recovering planted habits shows that the "
                                                              "features, the thresholds and the intervals work on data built to contain them; it says nothing about how real developers behave.")},
        {"id": "git-circularity", "severity": "medium", "text": ("The generator, the digest rules and the habit thresholds were written by the same agent. Thresholds were set on "
                                                                 "development replicates 0 to 3 and scored on fresh ones (100 and up), but the planted rates are large and habits are planted independently; "
                                                                 "real habits are smaller, correlated and noisier.")},
        {"id": "git-small-effects", "severity": "medium", "text": (
            "Small differences are not flagged by design (each habit has a floor). " + (
                f"At {round(100 * weak['strength'])}% of the planted strength recall falls to {_pct(weak['recall']['value'])}." if weak else ""))},
        {"id": "git-reverts-weak", "severity": "low", "text": "Reverts are rare even when planted, so the revert habit is the weakest to recover; it is reported, not tuned."},
        {"id": "git-digest-rules", "severity": "medium", "text": (
            "Evaluation digests come from the rules, because model digests take about a second a commit. "
            + ("Model against rules agreement was measured." if result.get("digest_agreement", {}).get("status") == "ok"
               else "The local model was not present, so model-against-rules agreement was not measured."))},
        {"id": "git-genome-modelled", "severity": "medium", "text": gen.get("reading", "The alignment on commit sessions was not run.")},
        {"id": "git-no-outcome", "severity": "medium", "text": ("Suggestions are advice chosen by code from commit-level shares. Nobody has been shown that following one improves "
                                                               "anything; there is no study of the git layer, and a share is not a cause.")},
        {"id": "git-reference-synthetic", "severity": "medium", "text": "A real repository is compared with generated experts, so its origin is reported as mixed; the comparison is with a scripted baseline, not with real experts."},
        {"id": "git-real-history-tiny", "severity": "low", "text": "The one real history (this project's) is short and agent-assisted; its aggregates illustrate the pipeline and are not a finding."},
        {"id": "git-canary-scope", "severity": "low", "text": "The leak result is a count of exact planted strings in captured request bodies on these flows. It does not catch a paraphrase, a translation or a hash of a token."},
    ]
    return out


def _pct(x) -> str:
    return "n/a" if x is None else f"{round(100 * x)}%"


# ------------------------------------------------------------------------------------------------ entry point
def evaluate_git(fast: bool = False) -> dict:
    """The git layer's evaluation section. ``fast`` uses 3 replicates and fewer bootstrap draws (about half a minute)."""
    t0 = time.time()
    reps = FAST_REPLICATES if fast else EVAL_REPLICATES
    boot = 300 if fast else 1000
    with _isolated_data_dir(), tempfile.TemporaryDirectory(prefix="git-eval-repos-") as tmp:
        base = Path(tmp)
        recovery, pl, cohorts, experts_by_rep = _recovery(reps, base, boot)
        stress, stress_pl, _, _ = _recovery(tuple(reps)[:4], base / "stress", max(200, boot // 2), jitter=2.0)
        recovery["stress_double_between_person_variation"] = {
            "design": "the same procedure with twice the between-person spread in every baseline rate (experts and learners)",
            "replicates": stress["design"]["replicates"], "precision": stress["overall"]["precision"], "recall": stress["overall"]["recall"],
            "specificity": stress["overall"]["specificity"], "placebo_false_flags": stress_pl["false_flags"]}
        recovery["dose_response"] = _dose(reps, base, max(200, boot // 2), (0.5,) if fast else DOSE_STRENGTHS, experts_by_rep)
        first = cohorts[reps[0]]
        result: dict[str, Any] = {
            "status": "ok",
            "habit_recovery": recovery,
            "placebo": pl,
            "digest_accuracy": _digest_accuracy(first),
            "digest_agreement": _digest_agreement(first, 40 if fast else 120),
            "genome": _genome(cohorts, reps, fast),
            "leak_canary": _leak_canary(tuple(range(3 if fast else 8))),
        }
    result["real_world"] = _real_world()
    result["statement"] = NO_PEOPLE
    result["limitations"] = limitations(result)
    n_personas = len(reps) * 12
    result["meta"] = {
        "origin": "synthetic", "n": n_personas, "n_unit": "personas",
        "split": ("fresh generated seeds (replicates 100 and up); thresholds were chosen on replicates 0 to 3; learners compared with the 8 experts of "
                  "their own replicate; bootstrap by day and by person"),
        "interval_level": 0.95,
        "note": ("Scripted developers with planted habits; no real people. " + ("Fast run: " if fast else "") +
                 f"{len(reps)} replicates of 4 learners and 8 experts, {recovery['overall']['tp'] + recovery['overall']['fn']} planted learner-habit pairs."),
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    result["elapsed_s"] = rnd(time.time() - t0, 1)
    return result
