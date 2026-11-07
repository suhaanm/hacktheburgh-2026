"""Small measurements of the v1 synthetic data for evals/realism/DIAGNOSIS.md. Read-only on data/synthetic."""
import json, math, statistics as st, collections, sys
from pathlib import Path
import numpy as np

ROOT = Path("/Users/suhaan/Desktop/hacktheburgh/data/synthetic")


def lj(p):
    return [json.loads(l) for l in (p).read_text().splitlines() if l.strip()]


out = {}
# ------------------------------------------------------------ apprentices
tr = json.loads((ROOT / "apprentices/truth.json").read_text())
traces = tr["traces"]
exp = [t for t in traces if t["level"] == "expert"]
nov = [t for t in traces if t["level"] == "novice"]
out["app_n_people"] = len(tr["people"]); out["app_n_traces"] = len(traces)
seqs_exp = collections.Counter(tuple(c for c, _, _ in t["cogs"]) for t in exp)
out["app_expert_distinct_cog_sequences"] = len(seqs_exp)
out["app_expert_sequence_lengths"] = sorted({len(k) for k in seqs_exp})
# novice: sequence determined by deficits
nov_seqs = collections.Counter(tuple(c for c, _, _ in t["cogs"]) for t in nov)
out["app_novice_distinct_cog_sequences"] = len(nov_seqs)
# person-level constancy of deficits across the two cases
by_p = collections.defaultdict(list)
for t in nov:
    by_p[t["person"]].append(frozenset(d["type"] for d in t["deficits"]))
out["app_novice_deficit_set_same_in_both_cases"] = sum(1 for v in by_p.values() if len(set(v)) == 1)
out["app_novice_n"] = len(by_p)
out["app_novices_with_zero_deficits"] = sum(1 for v in by_p.values() if not v[0])
out["app_novice_deficit_count_hist"] = dict(collections.Counter(len(v[0]) for v in by_p.values()))
# dwell dispersion
dw = collections.defaultdict(list)
for t in exp:
    for c, d, tag in t["cogs"]:
        if tag is None:
            dw[c].append(d)
res = {}
for c, v in dw.items():
    v = np.array(v)
    if len(v) >= 8:
        res[c] = {"n": len(v), "median": round(float(np.median(v)), 1), "p99_over_median": round(float(np.quantile(v, .99) / np.median(v)), 2),
                  "log_sd": round(float(np.std(np.log(v))), 3)}
out["app_expert_dwell_by_cog"] = res
tot_exp = np.array([t["duration_s"] for t in exp]); tot_nov = np.array([t["duration_s"] for t in nov])
out["app_expert_total_median_s"] = round(float(np.median(tot_exp)), 1)
out["app_expert_total_cv"] = round(float(tot_exp.std() / tot_exp.mean()), 3)
out["app_novice_total_median_s"] = round(float(np.median(tot_nov)), 1)
out["app_speed_factor_expert_range"] = [min(p["speed_factor"] for p in tr["people"] if p["level"] == "expert"), max(p["speed_factor"] for p in tr["people"] if p["level"] == "expert")]
out["app_speed_factor_novice_range"] = [min(p["speed_factor"] for p in tr["people"] if p["level"] == "novice"), max(p["speed_factor"] for p in tr["people"] if p["level"] == "novice")]
out["app_levels_do_not_overlap_in_speed"] = max(p["speed_factor"] for p in tr["people"] if p["level"] == "expert") < min(p["speed_factor"] for p in tr["people"] if p["level"] == "novice")
# separability of expert vs novice by total time
out["app_total_time_overlap_novice_min_vs_expert_max"] = [round(float(tot_nov.min()), 1), round(float(tot_exp.max()), 1)]
pr = [d["price_s"] for t in nov for d in t["deficits"]]
out["app_deficit_price_s_quantiles"] = [round(float(x), 1) for x in np.quantile(pr, [0, .25, .5, .75, 1])] if pr else None
# stuck labels
sl = [s["labelled"] for s in tr["stuck_episodes"]]
out["app_stuck_blocks"] = len(sl); out["app_stuck_labelled_share"] = round(sum(sl) / max(1, len(sl)), 3)

# events: dedupe/drop/jitter/inter-event times
ev = lj(ROOT / "apprentices/events.jsonl")
from datetime import datetime
def ts(s): return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
by_task = collections.defaultdict(list)
for e in ev:
    if e.get("task_id"): by_task[e["task_id"]].append(e)
gaps = []
dups = 0; prog_after_cog = []
for tid, es in by_task.items():
    es.sort(key=lambda e: ts(e["t"]))
    tt = [ts(e["t"]) for e in es if e["type"] not in ("task_start", "task_end", "progress", "stuck")]
    gaps.extend(np.diff(tt))
    seen = set()
    for e in es:
        k = (e["type"], e.get("target", {}).get("label_hash"), round(ts(e["t"]), 1))
        if k in seen: dups += 1
        seen.add(k)
gaps = np.array(gaps)
out["app_event_interarrival_s_quantiles"] = [round(float(x), 2) for x in np.quantile(gaps, [.01, .25, .5, .75, .99, 1.0])]
out["app_event_interarrival_p99_over_median"] = round(float(np.quantile(gaps, .99) / np.median(gaps)), 2)
out["app_duplicate_events"] = dups; out["app_events"] = len(ev)
out["app_task_marker_share"] = round(sum(1 for e in ev if e["type"] in ("task_start", "task_end")) / len(ev), 3)
out["app_events_with_task_id_share"] = round(sum(1 for e in ev if e.get("task_id")) / len(ev), 3)

# ------------------------------------------------------------ personas
pers = {}
for slug in ("nine-to-five", "night-owl", "shift-worker", "irregular"):
    t = json.loads((ROOT / slug / "truth.json").read_text())
    pers[slug] = {"tasks": t["counts"]["tasks"], "stuck_eps": t["counts"]["stuck_episodes"], "s0": t["skill"]["s0"], "alpha": t["skill"]["alpha"], "n0": t["skill"]["n0"],
                  "skill_first": t["skill"]["by_day"][0], "skill_last": t["skill"]["by_day"][-1], "events": t["counts"]["events"]}
out["personas"] = pers
# progress determinism: progress time vs cog end, and share of stuck cogs
t = json.loads((ROOT / "nine-to-five/truth.json").read_text())
stuck_dur = [s["duration_s"] for s in t["stuck_episodes"]]
out["persona_stuck_duration_s_quantiles"] = [round(float(x), 1) for x in np.quantile(stuck_dur, [0, .25, .5, .75, .99, 1])]
out["persona_stuck_duration_log_sd"] = round(float(np.std(np.log(stuck_dur))), 3)
out["persona_stuck_labelled_share"] = round(sum(1 for s in t["stuck_episodes"] if s["labelled"]) / len(t["stuck_episodes"]), 3)
rt = collections.Counter()
for r in t["routines"]:
    for i in r["instances"]:
        rt[(r["name"], i["n_cogs"])] += 1
out["persona_routine_instance_len_distinct"] = {r["name"]: sorted({i["n_cogs"] for i in r["instances"]})[:12] for r in t["routines"]}

# ------------------------------------------------------------ hazard label construction
sys.path.insert(0, "/Users/suhaan/Desktop/hacktheburgh/services/engine")
from understudy_engine.hazard.data import load_persona_episodes
from understudy_engine.hazard.features import build_bins
eps, planted, info = load_persona_episodes(None)
tab = build_bins(eps)
y = tab.y.astype(int)
lab = np.zeros(tab.n, int)
for q, spells in planted.items():
    rows = tab.rows_of([q])
    tt = tab.t[rows]
    for t0, t1 in spells:
        lab[rows[(tt + tab.horizon_s > t0) & (tt < t1)]] = 1
out["hazard_bins"] = int(tab.n); out["hazard_y_rate"] = round(float(y.mean()), 3)
out["hazard_share_of_y1_bins_inside_planted_spell"] = round(float(((y == 1) & (lab == 1)).sum() / max(1, (y == 1).sum())), 3)
out["hazard_share_planted_bins_with_y1"] = round(float(((y == 1) & (lab == 1)).sum() / max(1, (lab == 1).sum())), 3)
# progress after productive cogs
n_prog = sum(len(e.progress_t) for e in eps)
out["episodes"] = len(eps); out["progress_events"] = n_prog
print(json.dumps(out, indent=1, default=str))
