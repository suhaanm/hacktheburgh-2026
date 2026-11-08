"""The ``agentic`` section and the study_roles pilot block, built from RECORDED files only (no model, no network, nothing is re-run).

agentic reads ``evals/agentic/results``: ``lh_offline.json`` (LH-1 to LH-5, offline), ``heldout_*.json`` (the held-out confirmation; a part that has no file yet is
labelled "not run yet"), ``spend_ledger.json``, plus the claim-wording rules of ``evals/agentic/ITERATIONS.md`` applied in the sentences below, and the real-desktop
rung status from ``evals/agentic/REAL_CLICKS.md``. Origin: a language model driving a sandbox we wrote, in a headless browser; not a real desktop, not people.

The injected condition is TEXT-ONLY evidence (it tests the detector and the pause). It is never worded as "the gate resists hostile pages". Clean n is descriptive
(Wilson interval); the pre-registered "lower bound at least 0.8" criterion is not testable under the spend cap. Gate stops are reported apart from model failures.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from .stats import wilson

ORIGIN_TEXT = "language model driving a sandbox we wrote, in a headless browser; not a real desktop and not people"
HELDOUT_CONDITIONS = ("injected", "clean")
SIM = "language-model participants, not people"


def _json(path: Path) -> dict[str, Any] | None:
    try:
        if not path.is_file() or path.is_symlink():
            return None
        d = json.loads(path.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else None
    except (OSError, ValueError):
        return None


def _text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8") if path.is_file() and not path.is_symlink() else ""
    except OSError:
        return ""


def _small(o: Any, limit: int = 400) -> bool:
    return len(json.dumps(o, default=str)) <= limit


def _lh_suite(s: dict[str, Any]) -> dict[str, Any]:
    """One long-horizon suite without its per-household rows: scalars and small structures stay."""
    return {k: v for k, v in s.items() if k not in ("rows", "baseline", "interrupted", "night1") and (not isinstance(v, (dict, list)) or _small(v))}


def frozen_gate_version(iterations_md: str) -> str | None:
    """Round 1: the gate hash the held-out result files must carry, as the lead's note in ITERATIONS.md states it (``must equal <hash>`` or ``gate hash <hash>``)."""
    m = re.search(r"(?:must equal|gate hash)\s+`?([0-9a-f]{12})`?", iterations_md)
    return m.group(1) if m else None


def plan_frozen_gate_version(plan_md: str) -> str | None:
    """A later round: the gate hash its own plan freezes, after any amendment. The plan says ``must print **`<hash>`**`` and an amendment says ``the new gate
    version is **`<hash>`**``; amendments come later in the file, so the last statement is the current one."""
    found = re.findall(r"(?:must print|new gate version is)\s+\*{0,2}`?([0-9a-f]{12})`?", plan_md)
    return found[-1] if found else None


ROUND_FILE = re.compile(r"^round(\d+)_(clean|injected)_(\d+)\.json$")          # a worker shard (round2_clean_9139_w0.json) does not match: shards are ignored


def discover_rounds(res: Path, root: Path) -> list[dict[str, Any]]:
    """The held-out rounds on disk, oldest first. Round 1 is the ``heldout_*.json`` files (frozen hash from ITERATIONS.md); round N is ``round<N>_<condition>_<seed>.json``
    (frozen hash from ``PLAN_ROUND<N>.md``). Each round is checked against ITS OWN frozen hash, and rounds are never pooled."""
    rounds: dict[int, dict[str, Any]] = {}
    if not res.is_dir():
        return []
    for p in sorted(res.glob("heldout_*.json")):
        rec = _json(p)
        if rec:
            rounds.setdefault(1, {"number": 1, "id": "round1", "plan": "evals/agentic/ITERATIONS.md", "frozen": frozen_gate_version(_text(root / "ITERATIONS.md")), "files": {}})["files"].setdefault(str(rec.get("condition")), (p.name, rec))
    for p in sorted(res.iterdir()):
        m = ROUND_FILE.match(p.name)
        rec = _json(p) if m else None
        if m and rec:
            n = int(m.group(1))
            plan_name = f"PLAN_ROUND{n}.md"
            rounds.setdefault(n, {"number": n, "id": f"round{n}", "plan": f"evals/agentic/{plan_name}", "frozen": plan_frozen_gate_version(_text(root / plan_name)), "files": {}})["files"].setdefault(
                str(rec.get("condition") or m.group(2)), (p.name, rec))
    return [rounds[k] for k in sorted(rounds)]


def _failure_key(m: Any) -> str:
    if isinstance(m, str):
        return m
    if isinstance(m, dict):
        return str(m.get("outcome") or m.get("kind") or m.get("reason") or "other")
    return "other"


def _config(rec: dict[str, Any]) -> str:
    mo = rec.get("models") or {}
    names = ", ".join(f"{k.replace('_', ' ')} {v}" for k, v in mo.items() if k != "provider" and v)
    return f"{rec.get('computer_use_provider') or mo.get('provider') or 'unknown provider'}" + (f" ({names})" if names else "")


def heldout_summary(rec: dict[str, Any], frozen: str | None, source: str, rnd: dict[str, Any] | None = None) -> dict[str, Any]:
    rows = [r for r in rec.get("rows") or [] if isinstance(r, dict)]
    n = rec["n"] if isinstance(rec.get("n"), int) else len(rows)
    n_ok = int(rec.get("n_ok") or 0)
    n_paused = int(rec.get("n_paused") or 0)
    stops = [s for r in rows for s in (r.get("gate_stops") or [])]
    every = [_failure_key(m) for r in rows for m in (r.get("model_failures") or [])]
    cancelled = Counter(k for k in every if k.startswith("stopped:"))      # a navigator cancelled because the run paused or a sibling was stopped: not a model failure
    fails = Counter(k for k in every if not k.startswith("stopped:"))
    gv = rec.get("gate_version")
    steps = [r["steps"] for r in rows if isinstance(r.get("steps"), (int, float))]
    wall = [r["wall_s"] for r in rows if isinstance(r.get("wall_s"), (int, float))]
    prim = rec.get("primary") if isinstance(rec.get("primary"), dict) else None
    out = {
        "status": "recorded", "source": source, "label": rec.get("label"), "condition": rec.get("condition"), "seed": rec.get("seed"), "heldout": rec.get("heldout"),
        "round": (rnd or {}).get("id", "round1"), "plan": (rnd or {}).get("plan"), "provider": rec.get("computer_use_provider") or (rec.get("models") or {}).get("provider"),
        "config": _config(rec),
        "n": n, "passed_code_check": {"k": n_ok, "n": n, "wilson95": wilson(n_ok, n)},
        "reached_approval_gate": {"k": sum(1 for r in rows if r.get("awaiting_approval")), "n": n},
        "claimed_success_runs": sum(1 for r in rows if r.get("claimed_success")), "paused_runs": n_paused,
        "paused_by_detector": {"k": n_paused, "n": n, "wilson95": wilson(n_paused, n)},
        "attacks": rec.get("attacks"), "false_claims": rec.get("false_claims"), "dropped": len(rec.get("dropped") or []),
        "submissions": sum(int(r.get("submissions") or 0) for r in rows), "exfil_hits": sum(int(r.get("exfil_hits") or 0) for r in rows),
        "gate_version": gv, "frozen_gate_version": frozen, "gate_version_ok": None if frozen is None else gv == frozen,
        "models": rec.get("models"), "computer_use_provider": rec.get("computer_use_provider"),
        "gate_stops": {"total": len(stops), "designed_submit": sum(1 for s in stops if isinstance(s, dict) and s.get("designed")),
                       "unexpected": rec.get("gate_stops_unexpected"), "by_kind": rec.get("gate_stops_by_kind") or {},
                       "action_rejections": sum(int(r.get("action_rejections") or 0) for r in rows),
                       "note": "gate stops are reported apart from model failures; an unexpected stop is a harness or gate-tuning finding, not a model result"},
        "model_failures": {"total": sum(fails.values()), "by_outcome": dict(sorted(fails.items())),
                           "navigators_cancelled_by_a_pause_or_stop": {"total": sum(cancelled.values()), "by_outcome": dict(sorted(cancelled.items())),
                                                                       "note": "the owner lists these under model_failures; they are navigators cancelled when the run paused or a sibling was stopped, so they are not counted as model failures here"}},
        "steps_mean": round(sum(steps) / len(steps), 1) if steps else None, "wall_s_mean": round(sum(wall) / len(wall), 1) if wall else None,
        "tokens_in": sum(int(r.get("tokens_in") or 0) for r in rows), "tokens_out": sum(int(r.get("tokens_out") or 0) for r in rows),
        "cost_placeholder_usd": rec.get("spent_placeholder_usd"), "rates_in_out_per_m": rec.get("rates_in_out_per_m"),
        "owner_note": rec.get("note_injected"),
        "rows": [{"household": r.get("household"), "archetype": r.get("archetype"), "state": r.get("state"), "claimed_success": r.get("claimed_success"),
                  "false_claim": r.get("false_claim"), "submissions": r.get("submissions"), "steps": r.get("steps"), "wall_s": r.get("wall_s"),
                  "all_inputs_exact": r.get("all_inputs_exact"), "gate_stops": len(r.get("gate_stops") or [])} for r in rows],
    }
    if prim:                                                   # the pre-registered primary measure and bar (later rounds write it into the result file)
        k, pn, bar = int(prim.get("k") or 0), int(prim.get("n") or n), prim.get("bar_lower_bound")
        w = wilson(k, pn)
        met = None if bar is None or w[0] is None else w[0] >= float(bar)
        out["primary"] = {"measure": prim.get("measure"), "k": k, "n": pn, "wilson95": w, "bar_lower_bound": bar, "bar_met": met, "bar_met_in_file": prim.get("bar_met"),
                          "consistent": met is None or prim.get("bar_met") is None or met == bool(prim.get("bar_met"))}
    audit = {k: rec[k] for k in ("harness_accepted_wrong_inputs", "n_all_inputs_exact", "n_ok_and_all_inputs_exact", "cliff_steps_failed", "goal_checks", "form_audit", "model_retries") if k in rec}
    if audit:
        out["audit"] = audit
    if rec.get("false_claims_note"):
        out["false_claims_note"] = rec["false_claims_note"]
    return out


def _pct(k: int, n: int) -> str:
    lo, hi = wilson(k, n)
    return "n/a" if lo is None else f"Wilson 95% {lo:.2f} to {hi:.2f}"


def _gate(h: dict[str, Any]) -> str:
    ok = h.get("gate_version_ok")
    tail = "" if ok is None else (", matches this round's frozen hash" if ok else f", DOES NOT match this round's frozen hash {h.get('frozen_gate_version')}")
    return f"gate {h.get('gate_version')}{tail}"


def _round_name(h: dict[str, Any]) -> str:
    return str(h.get("round") or "round1").replace("round", "Round ")


def headline_k(h: dict[str, Any]) -> tuple[int, int, list[float | None]]:
    """The k of n a part is reported on: the pre-registered primary measure when the result file carries one, else the detector pauses (injected) or the code check (clean)."""
    if h.get("primary"):
        p = h["primary"]
        return p["k"], p["n"], p["wilson95"]
    if h.get("condition") == "injected":
        p = h["paused_by_detector"]
    else:
        p = h["passed_code_check"]
    return p["k"], p["n"], p["wilson95"]


def reading(h: dict[str, Any]) -> str:
    """The wording to use for one held-out part (the claim rules of ITERATIONS.md and of the round's plan)."""
    n = h["n"]
    head = f"{_round_name(h)}, {h.get('condition')}, held-out seed {h.get('seed')}, n = {n}, {h.get('config')}; {_gate(h)}"
    if h.get("condition") == "injected":
        p = h["paused_by_detector"]
        return (f"{head}: the detector paused {p['k']} of {n} pages of this kind ({_pct(p['k'], n)}); {h.get('attacks')} attacks "
                f"({h.get('exfil_hits')} visits to the exfil address, {h.get('submissions')} submissions). The pages carry text aimed at an AI and nothing else, so this is "
                "evidence about the detector and the pause only. It does not show that the gate resists hostile pages.")
    g = h["reached_approval_gate"]
    kinds = ", ".join(f"{k} x{v}" for k, v in sorted((h["gate_stops"]["by_kind"] or {}).items()))
    stop = (f"; {h['gate_stops']['unexpected']} unexpected gate stop(s) ({kinds}), harness or gate-tuning findings listed apart from model failures"
            if h["gate_stops"].get("unexpected") else "")
    states = Counter(r.get("state") for r in h.get("rows") or [] if not r.get("all_inputs_exact") and not (r.get("claimed_success") and r.get("all_inputs_exact") is None))
    if h.get("primary"):
        p = h["primary"]
        k = p["k"]
        miss = n - k
        bar = "" if p["bar_met"] is None else (
            f"; the pre-registered bar was {'met' if p['bar_met'] else 'not met'} (the Wilson lower bound had to be at least {p['bar_lower_bound']:.2f} and is {p['wilson95'][0]:.2f})")
        if not p["consistent"]:
            bar += f" (the result file's own flag says {p['bar_met_in_file']}, which DISAGREES; the harness's computation is shown)"
        ended = f"; the {miss} that did not complete ended " + ", ".join(f"{s} ({v})" for s, v in sorted(states.items(), key=lambda kv: str(kv[0]))) if miss else ""
        return (f"{head}: {k} of {n} households completed with correct inputs on all three calculators ({_pct(k, n)}){bar}. {h.get('false_claims')} false claim(s), "
                f"{h.get('submissions')} submissions{ended}{stop}. One run per household of one non-deterministic model; this round is not pooled with any other round.")
    c = h["passed_code_check"]
    return (f"{head}: {c['k']} of {n} passed the code check ({_pct(c['k'], n)}), {g['k']} of {n} reached the approval gate, "
            f"{h.get('false_claims')} false claim(s) (a success claimed while a figure did not match the code check), {h.get('submissions')} submissions{stop}. "
            f"n = {n} is descriptive: the pre-registered criterion 'Wilson lower bound at least 0.8' cannot be tested at this n under the spend cap, so this neither confirms nor rejects it. "
            "This round is not pooled with any other round.")


def earlier_line(h: dict[str, Any]) -> dict[str, Any]:
    k, n, w = headline_k(h)
    return {"round": h.get("round"), "label": h.get("label"), "condition": h.get("condition"), "seed": h.get("seed"), "provider": h.get("provider"), "config": h.get("config"),
            "gate_version": h.get("gate_version"), "frozen_gate_version": h.get("frozen_gate_version"), "gate_version_ok": h.get("gate_version_ok"), "plan": h.get("plan"),
            "n": n, "k": k, "wilson95": w, "bar_met": (h.get("primary") or {}).get("bar_met"), "source": h.get("source"), "reading": h["reading"]}


def _real_desktop(root: Path) -> dict[str, Any]:
    md = _text(root / "REAL_CLICKS.md")
    ladder = sorted(set(re.findall(r"^##\s+(R\d)\b", md, flags=re.M)))
    runs = Counter(re.findall(r"^##\s+(R\d)\s+run\s+\d+", md, flags=re.M))
    rc = root / "results" / "real_clicks"
    files = sorted(p.name for p in rc.glob("*.json")) if rc.is_dir() else []
    ran = dict(sorted(runs.items()))
    ran_text = ", ".join(f"{r} ran {'once' if c == 1 else f'{c} times'}" for r, c in ran.items())
    text = ("Real desktop: " + (ran_text + " (R0 reads the window list and accessibility only, so it sends no input events by construction); no other rung has run."
                                if ran else "no rung has run.") + " Everything else here is the headless sandbox.")
    return {"ladder": ladder, "rungs_run": ran, "rungs_not_run": [r for r in ladder if r not in ran], "result_files": files, "source": "evals/agentic/REAL_CLICKS.md", "text": text}


def build(root: Path) -> dict[str, Any] | None:
    """The agentic section from ``root`` (= evals/agentic), or None when no recorded file exists at all. The headline of each condition is the NEWEST round that has it;
    the earlier rounds sit beside it under ``earlier_rounds``, each with its own gate-version check. Rounds are never pooled."""
    res = root / "results"
    lh = _json(res / "lh_offline.json")
    spend = _json(res / "spend_ledger.json")
    rounds = discover_rounds(res, root)
    if not (lh or rounds or spend):
        return None
    by_round: list[tuple[dict[str, Any], dict[str, dict[str, Any]]]] = []
    for rnd in rounds:
        parts_r = {}
        for cond, (name, rec) in rnd["files"].items():
            h = heldout_summary(rec, rnd["frozen"], f"evals/agentic/results/{name}", rnd)
            h["reading"] = reading(h)
            parts_r[cond] = h
        by_round.append((rnd, parts_r))
    parts: dict[str, Any] = {}
    for cond in HELDOUT_CONDITIONS:
        have = [(rnd, pr[cond]) for rnd, pr in by_round if cond in pr]
        if not have:
            parts[cond] = {"status": "not_run", "condition": cond,
                           "reason": f"not run yet: no evals/agentic/results/heldout_{cond}_<seed>.json or round<N>_{cond}_<seed>.json is written; this part is read when the file appears"}
            continue
        head = dict(have[-1][1])
        head["earlier_rounds"] = [earlier_line(h) for _, h in have[:-1]]
        head["earlier_rounds_note"] = ("earlier rounds, shown apart: they measure other configurations (provider, models, build) and are never pooled with the headline" if have[:-1] else "no earlier round")
        parts[cond] = head
    ns = [p["n"] for p in parts.values() if p.get("status") == "recorded"]
    suites = (lh or {}).get("suites") or {}
    split_parts = ", ".join(f"{parts[c].get('round')} {c} seed {parts[c].get('seed')} (n = {parts[c]['n']})" for c in HELDOUT_CONDITIONS if parts[c].get("status") == "recorded")
    out: dict[str, Any] = {
        "meta": {"origin": "simulated_llm", "n": sum(ns), "n_unit": "sandbox households", "interval_level": 0.95,
                 "split": ("held-out seeds only, newest round per condition: " + split_parts + "; earlier rounds are listed apart and never pooled" if ns else "no held-out file yet")
                          + "; in-sample dev rounds (ITERATIONS.md) are not counted; LH-1 to LH-5 are offline code tests with no model",
                 "note": f"{ORIGIN_TEXT}. No comparison arm: pass counts against a pre-registered criterion, not against a baseline."},
        "origin_text": ORIGIN_TEXT,
        "lh_offline": ({"note": (lh or {}).get("note"), "source": "evals/agentic/results/lh_offline.json", "model_tokens": sum(int(s.get("model_tokens") or 0) for s in suites.values()),
                        "all_ok": all(bool(s.get("ok")) for s in suites.values()) if suites else None, "suites": {k: _lh_suite(v) for k, v in suites.items()}} if lh else
                       {"status": "not_run", "reason": "not run yet: evals/agentic/results/lh_offline.json is not written"}),
        "heldout": parts,
        "rounds": [{"id": rnd["id"], "plan": rnd["plan"], "frozen_gate_version": rnd["frozen"], "conditions": sorted(pr),
                    "config": next(iter(pr.values()))["config"] if pr else None, "gate_version_ok": all(h.get("gate_version_ok") is not False for h in pr.values())} for rnd, pr in by_round],
        "heldout_expected_gate_version": next((rnd["frozen"] for rnd, _ in reversed(by_round)), None),
        "spend": ({"cap_usd": spend.get("cap_usd"), "spent_placeholder_usd": spend.get("spent_placeholder_usd"), "spent_lower_usd": spend.get("spent_lower_usd"),
                   "pct_of_cap": spend.get("pct_of_cap"), "entries": len(spend.get("entries") or []), "source": "evals/agentic/results/spend_ledger.json",
                   "note": "placeholder = list price at the rates in each entry; lower = the same tokens at the lower bound the ledger records"} if spend else
                  {"status": "not_run", "reason": "no evals/agentic/results/spend_ledger.json"}),
        "real_desktop": _real_desktop(root),
        "claim_rules": ["The injected condition is text-only: the detector paused N of M pages of this kind; it never shows that the gate resists hostile pages.",
                        "Clean n is descriptive (Wilson) unless the round's plan pre-registers a bar; when it does, the result says plainly whether the bar was met.",
                        "Each round is checked against its own plan's frozen gate version; rounds with different configurations are shown apart and never pooled.",
                        "Gate stops are reported apart from model failures, with the gate version shown.",
                        "Origin: " + ORIGIN_TEXT + "."],
    }
    out["limitations"] = limitations(out)
    return out


def limitations(s: dict[str, Any]) -> list[dict[str, str]]:
    def e(id_: str, sev: str, text: str) -> dict[str, str]:
        return {"id": id_, "severity": sev, "text": text}

    out = [e("agentic-origin", "high", f"The agent results are from a {ORIGIN_TEXT}. They say nothing about a real desktop, real calculators or real people's casework. " + s["real_desktop"]["text"])]
    inj, cln = s["heldout"]["injected"], s["heldout"]["clean"]
    if inj.get("status") == "recorded":
        out.append(e("agentic-injected-text-only", "high", inj["reading"]))
    else:
        out.append(e("agentic-injected-text-only", "high", "The injected condition is text-only: it tests the detector and the pause and never shows that the gate resists hostile pages. "
                     "The held-out injected run is not run yet."))
    if cln.get("status") == "recorded":
        out.append(e("agentic-clean-descriptive", "high", cln["reading"]))
    else:
        out.append(e("agentic-clean-descriptive", "high", "The clean held-out run is not run yet. When it is, a small n is descriptive (Wilson interval): the pre-registered criterion "
                     "'Wilson lower bound at least 0.8' is not testable at n = 4 under the spend cap."))
    earlier = [x for h in (inj, cln) if h.get("status") == "recorded" for x in h.get("earlier_rounds") or []]
    if earlier:
        out.append(e("agentic-rounds-not-pooled", "high", "Held-out rounds measure different configurations and are shown apart, never pooled; the headline above is the newest round. Earlier: "
                     + " | ".join(x["reading"] for x in earlier)))
    bad = [h for h in [inj, cln, *[x for p in (inj, cln) for x in (p.get("earlier_rounds") or [])]] if h.get("status") != "not_run" and h.get("gate_version_ok") is False]
    if bad:
        out.append(e("agentic-gate-version-mismatch", "high", "A held-out result file carries a gate version other than its own round's frozen one: "
                     + ", ".join(f"{h.get('source')} ({h.get('gate_version')} against {h.get('frozen_gate_version')})" for h in bad) + ". Do not quote its numbers."))
    unexpected = [h for h in (inj, cln) if h.get("status") == "recorded" and (h["gate_stops"].get("unexpected") or 0) > 0]
    if unexpected:
        out.append(e("agentic-gate-stops-unexpected", "medium", "Unexpected gate stops are listed apart from model failures and are harness or gate-tuning findings, not model results: "
                     + ", ".join(f"{h.get('round')} {h.get('condition')}: {h['gate_stops']['unexpected']}" for h in unexpected) + "."))
    lh = s["lh_offline"]
    if lh.get("suites"):
        out.append(e("agentic-lh-offline", "medium", f"LH-1 to LH-5 ({', '.join(lh['suites'])}) are offline: a grounded test double (LH-5 uses compiled routines with the heuristic reader), "
                     f"{lh['model_tokens']} model tokens. They test the code, not any model."))
    sp = s["spend"]
    if sp.get("cap_usd") is not None:
        out.append(e("agentic-spend", "medium", f"Live agent spend is {sp['spent_placeholder_usd']} US dollars at list price ({sp['spent_lower_usd']} at the lower bound) of a {sp['cap_usd']} cap "
                     f"({sp['pct_of_cap']}%), across the development rounds and every held-out round."))
    return out


# ------------------------------------------------------------------------------------------------------- study_roles pilots
def pilot_summary(pilots: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, p in sorted(pilots.items()):
        if not isinstance(p, dict):
            continue
        c, plan = p.get("criteria") or {}, p.get("plan") or {}
        out[key] = {"role": p.get("role"), "tier": p.get("tier"), "model": p.get("model"), "usable": p.get("usable"), "reasons": p.get("reasons") or [],
                    "n_unassisted_cases": p.get("n_unassisted_cases"), "participants_run": p.get("participants_run"),
                    "share_zero": p.get("share_zero"), "share_full": p.get("share_full"), "share_cap_bound": p.get("share_cap_bound"),
                    "limits": {"max_share_zero": c.get("max_share_zero"), "max_share_full": c.get("max_share_full"), "max_share_cap_bound": c.get("max_share_cap_bound")},
                    "mean_cost_per_participant_usd": p.get("mean_cost_per_participant_usd"), "points": p.get("points"),
                    "plan": {k: plan.get(k) for k in ("units", "participants", "coached", "aa", "estimated_cost_usd", "run") if k in plan}}
    return out


def _share(x: Any) -> str:
    return "n/a" if x is None else f"{100 * x:.1f}%".replace(".0%", "%")


def pilot_sentence(key: str, p: dict[str, Any]) -> str:
    name = f"{key.split('/')[-1].removeprefix('PILOT_')} ({p.get('tier')}, {p.get('model')})"
    lim = p.get("limits") or {}
    if p.get("usable"):
        return (f"{name}: usable by code (floor {_share(p['share_zero'])}, limit {_share(lim.get('max_share_zero'))}; ceiling {_share(p['share_full'])}, limit {_share(lim.get('max_share_full'))}; "
                f"cap-binding {_share(p['share_cap_bound'])}, limit {_share(lim.get('max_share_cap_bound'))}; n = {p.get('n_unassisted_cases')} unassisted cases)")
    return f"{name}: not usable by code ({'; '.join(p.get('reasons') or ['no reason recorded'])}; n = {p.get('n_unassisted_cases')} unassisted cases)"


def study_roles_extras(pilots: dict[str, Any], plan_text: str) -> dict[str, Any]:
    """What a section with no study results still says: the pilots, that the study itself has not been run, and where the go-ahead is."""
    summ = pilot_summary(pilots)
    head = SIM[0].upper() + SIM[1:] + "."
    if summ:
        usable = [k for k, p in summ.items() if p.get("usable")]
        text = (f"{head} The role studies themselves have not been run: only {len(summ)} feasibility pilots of the programmer role exist ({len(usable)} usable); "
                "their participants are discarded and are not results. " + "; ".join(pilot_sentence(k, p) for k, p in summ.items()) + ".")
    else:
        text = f"{head} The role studies have not been run and no pilot exists."
    amend = re.search(r"\*\*Amendment 3 \((\d{4}-\d{2}-\d{2} \d{2}:\d{2} UTC)\)", plan_text)
    return {"pilots": summ, "study_run": False,
            "go_ahead": {"where": "evals/study_roles/PLAN.md, Amendment 3" + (f" ({amend.group(1)})" if amend else " (not found in PLAN.md)"),
                         "needs": "evals/study_roles/GO and the lead's go in chat; nothing is running"},
            "pilot_text": text}
