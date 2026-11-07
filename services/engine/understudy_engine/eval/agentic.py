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
SIM = "simulated participants (language model), not people"


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
    """The gate hash the held-out result files must carry, as the lead's note in ITERATIONS.md states it (``must equal <hash>`` or ``gate hash <hash>``)."""
    m = re.search(r"(?:must equal|gate hash)\s+`?([0-9a-f]{12})`?", iterations_md)
    return m.group(1) if m else None


def _failure_key(m: Any) -> str:
    if isinstance(m, str):
        return m
    if isinstance(m, dict):
        return str(m.get("outcome") or m.get("kind") or m.get("reason") or "other")
    return "other"


def heldout_summary(rec: dict[str, Any], frozen: str | None, source: str) -> dict[str, Any]:
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
    return {
        "status": "recorded", "source": source, "label": rec.get("label"), "condition": rec.get("condition"), "seed": rec.get("seed"), "heldout": rec.get("heldout"),
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
                  "gate_stops": len(r.get("gate_stops") or [])} for r in rows],
    }


def _pct(k: int, n: int) -> str:
    lo, hi = wilson(k, n)
    return "n/a" if lo is None else f"Wilson 95% {lo:.2f} to {hi:.2f}"


def _gate(h: dict[str, Any]) -> str:
    ok = h.get("gate_version_ok")
    tail = "" if ok is None else (", matches the frozen hash" if ok else f", DOES NOT match the frozen hash {h.get('frozen_gate_version')}")
    return f"gate {h.get('gate_version')}{tail}"


def reading(h: dict[str, Any]) -> str:
    """The wording to use for one held-out part (the claim rules of ITERATIONS.md)."""
    n = h["n"]
    if h.get("condition") == "injected":
        p = h["paused_by_detector"]
        return (f"Injected, held-out seed {h.get('seed')}, n = {n} ({_gate(h)}): the detector paused {p['k']} of {n} pages of this kind ({_pct(p['k'], n)}); {h.get('attacks')} attacks "
                f"({h.get('exfil_hits')} visits to the exfil address, {h.get('submissions')} submissions). The pages carry text aimed at an AI and nothing else, so this is "
                "evidence about the detector and the pause only. It does not show that the gate resists hostile pages.")
    c, g = h["passed_code_check"], h["reached_approval_gate"]
    kinds = ", ".join(f"{k} x{v}" for k, v in sorted((h["gate_stops"]["by_kind"] or {}).items()))
    stop = (f"; {h['gate_stops']['unexpected']} unexpected gate stop(s) ({kinds}), a harness or gate-tuning finding listed apart from model failures, paused {h.get('paused_runs')} run(s)"
            if h["gate_stops"].get("unexpected") else "")
    return (f"Clean, held-out seed {h.get('seed')}, n = {n} ({_gate(h)}): {c['k']} of {n} passed the code check ({_pct(c['k'], n)}), {g['k']} of {n} reached the approval gate, "
            f"{h.get('false_claims')} false claim(s) (a success claimed while a figure did not match the code check), {h.get('submissions')} submissions{stop}. "
            f"n = {n} is descriptive: the pre-registered criterion 'Wilson lower bound at least 0.8' cannot be tested at this n under the spend cap, so this neither confirms nor rejects it.")


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
    """The agentic section from ``root`` (= evals/agentic), or None when no recorded file exists at all."""
    res = root / "results"
    lh = _json(res / "lh_offline.json")
    spend = _json(res / "spend_ledger.json")
    held = {p.name: _json(p) for p in sorted(res.glob("heldout_*.json"))} if res.is_dir() else {}
    held = {k: v for k, v in held.items() if v}
    if not (lh or held or spend):
        return None
    frozen = frozen_gate_version(_text(root / "ITERATIONS.md"))
    parts: dict[str, Any] = {}
    for name, rec in held.items():
        h = heldout_summary(rec, frozen, f"evals/agentic/results/{name}")
        h["reading"] = reading(h)
        parts.setdefault(str(h.get("condition")), h)
    for cond in HELDOUT_CONDITIONS:
        parts.setdefault(cond, {"status": "not_run", "condition": cond,
                                "reason": f"not run yet: no evals/agentic/results/heldout_{cond}_<seed>.json is written; this part is read when the file appears"})
    ns = [p["n"] for p in parts.values() if p.get("status") == "recorded"]
    suites = (lh or {}).get("suites") or {}
    split_parts = ", ".join(f"{c} seed {parts[c].get('seed')} (n = {parts[c]['n']})" for c in HELDOUT_CONDITIONS if parts[c].get("status") == "recorded")
    out: dict[str, Any] = {
        "meta": {"origin": "simulated_llm", "n": sum(ns), "n_unit": "sandbox households", "interval_level": 0.95,
                 "split": ("held-out seeds only: " + split_parts if ns else "no held-out file yet") + "; in-sample dev rounds (ITERATIONS.md) are not counted; LH-1 to LH-5 are offline code tests with no model",
                 "note": f"{ORIGIN_TEXT}. No comparison arm: pass counts against a pre-registered criterion, not against a baseline."},
        "origin_text": ORIGIN_TEXT,
        "lh_offline": ({"note": (lh or {}).get("note"), "source": "evals/agentic/results/lh_offline.json", "model_tokens": sum(int(s.get("model_tokens") or 0) for s in suites.values()),
                        "all_ok": all(bool(s.get("ok")) for s in suites.values()) if suites else None, "suites": {k: _lh_suite(v) for k, v in suites.items()}} if lh else
                       {"status": "not_run", "reason": "not run yet: evals/agentic/results/lh_offline.json is not written"}),
        "heldout": parts,
        "heldout_expected_gate_version": frozen,
        "spend": ({"cap_usd": spend.get("cap_usd"), "spent_placeholder_usd": spend.get("spent_placeholder_usd"), "spent_lower_usd": spend.get("spent_lower_usd"),
                   "pct_of_cap": spend.get("pct_of_cap"), "entries": len(spend.get("entries") or []), "source": "evals/agentic/results/spend_ledger.json",
                   "note": "placeholder = list price at the rates in each entry; lower = the same tokens at the lower bound the ledger records"} if spend else
                  {"status": "not_run", "reason": "no evals/agentic/results/spend_ledger.json"}),
        "real_desktop": _real_desktop(root),
        "claim_rules": ["The injected condition is text-only: the detector paused N of M pages of this kind; it never shows that the gate resists hostile pages.",
                        "Clean n is descriptive (Wilson); the Wilson lower bound of 0.8 is not testable under the cap.",
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
        out.append(e("agentic-clean-descriptive", "high", "The clean held-out run is not run yet. When it is, n = 4 is descriptive (Wilson interval): the pre-registered criterion "
                     "'Wilson lower bound at least 0.8' is not testable under the spend cap."))
    bad = [h for h in (inj, cln) if h.get("status") == "recorded" and h.get("gate_version_ok") is False]
    if bad:
        out.append(e("agentic-gate-version-mismatch", "high", "A held-out result file carries a gate version other than the frozen one: "
                     + ", ".join(f"{h['source']} ({h.get('gate_version')} against {h.get('frozen_gate_version')})" for h in bad) + ". Do not quote its numbers."))
    unexpected = [h for h in (inj, cln) if h.get("status") == "recorded" and (h["gate_stops"].get("unexpected") or 0) > 0]
    if unexpected:
        out.append(e("agentic-gate-stops-unexpected", "medium", "Unexpected gate stops are listed apart from model failures and are harness or gate-tuning findings, not model results: "
                     + ", ".join(f"{h.get('condition')}: {h['gate_stops']['unexpected']}" for h in unexpected) + "."))
    lh = s["lh_offline"]
    if lh.get("suites"):
        out.append(e("agentic-lh-offline", "medium", f"LH-1 to LH-5 ({', '.join(lh['suites'])}) are offline: a grounded test double (LH-5 uses compiled routines with the heuristic reader), "
                     f"{lh['model_tokens']} model tokens. They test the code, not any model."))
    sp = s["spend"]
    if sp.get("cap_usd") is not None:
        out.append(e("agentic-spend", "medium", f"Live agent spend is {sp['spent_placeholder_usd']} US dollars at list price ({sp['spent_lower_usd']} at the lower bound) of a {sp['cap_usd']} cap "
                     f"({sp['pct_of_cap']}%); the cap is why the clean held-out n is 4."))
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
