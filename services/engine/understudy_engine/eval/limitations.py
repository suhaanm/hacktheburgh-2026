"""The limitations register (EVL-4): a first-class list assembled from the sections, not written around them.

Sources, in this order:
  1. every section's own ``limitations`` entries (owners write these in plain words);
  2. a section's ``caveats`` strings stay with the section (and in report.md); only a caveat that opens with an all-caps
     keyword such as CIRCULARITY is lifted into the register, as medium;
  3. entries computed here from the numbers (a weak or null result is added whether or not an owner wrote it down);
  4. a contract section that did not run (pending, not_run, failed) is itself a high-severity entry;
  5. the static list of things no experiment in this repo can fix.
Each entry is ``{id, text, severity: low|medium|high, source}``; duplicates by id are merged (sources joined).
"""
from __future__ import annotations

import re
from typing import Any

from ..store.paths import repo_root
from .adapters import SECTIONS

OWNER = {s.name: s.owner for s in SECTIONS}
SEV_RANK = {"high": 0, "medium": 1, "low": 2}
SIM_PHRASE = "simulated participants (language model), not people"
UMBRELLA = "eval-synthetic"
FOLD_INTO_UMBRELLA = {"ana-synthetic-origin", "presence-synthetic", "routines-synthetic"}
ABSORB = {"ana-claims-synthetic": "eval-claims-simulated", "ana-study-power": "eval-study-power-assumptions"}      # an owner entry that says the same thing as a static one
CORE_SECTIONS = ("deficit_recovery", "null_placebo", "hazard", "ope", "routing", "ski_rental", "presence", "routines", "agent_claims", "agent_runs", "redteam", "study")


def _pct(x: float | None, nd: int = 0) -> str:
    return "n/a" if x is None else f"{100 * x:.{nd}f}%"


def _ci(ci, nd: int = 1) -> str:
    return "n/a" if not ci or ci[0] is None else f"{ci[0]:.{nd}f} to {ci[1]:.{nd}f}"


def _oracle_text() -> str:
    base = ("The entitlement figures the agent is scored against come from a simplified internal rule set, not the law. ")
    try:
        text = (repo_root() / "docs" / "SPIKES.md").read_text(encoding="utf-8")
        m = re.search(r"agree within 1 pound on only (\d+) of (\d+)", text)
    except OSError:
        m = None
    if m:
        return base + (f"It agrees with PolicyEngine UK within 1 pound on only {m.group(1)} of {m.group(2)} generated households, "
                       "so passing our oracle is not the same as getting the entitlement right.")
    return base + "It was cross-checked against PolicyEngine UK and the two disagree on many generated households (docs/SPIKES.md, S4)."


def _study_n(sections: dict[str, Any] | None) -> tuple[int, bool]:
    """(n, ran): the n the study actually has, else the planned four."""
    st = (sections or {}).get("study")
    if isinstance(st, dict) and "status" not in st and isinstance(st.get("n"), int):
        return st["n"], True
    return 4, False


def static_entries(sections: dict[str, Any] | None = None) -> list[dict[str, str]]:
    n, ran = _study_n(sections)
    return [
        {"id": UMBRELLA, "severity": "high", "source": "engine-eval",
         "text": ("Almost every result in this report comes from synthetic apprentices, synthetic personas or simulators we wrote; each section "
                  "carries a synthetic badge. They show that the methods recover the structure we planted, not that real workers behave this way.")},
        {"id": "eval-study-n4", "severity": "high", "source": "engine-eval",
         "text": (f"The live study has n = {n}, all teammates, none of them benefits processors" + ("" if ran else " (planned; it has not been run)") +
                  ". Intervals are wide and the result is a case study. The headline measure is unassisted performance on a later matched "
                  "task, reported separately from assisted speed.")},
        {"id": "eval-thin-real-data", "severity": "high", "source": "engine-eval",
         "text": ("Real data is thin: the only real signal is the team's own machine timestamps (times only, collected with consent). "
                  "There are no real benefits-processor traces, so nothing here has been validated on real casework.")},
        {"id": "eval-oracle", "severity": "high", "source": "agent-core: docs/SPIKES.md S4", "text": _oracle_text()},
        {"id": "eval-sandbox-sites", "severity": "medium", "source": "agent-core",
         "text": ("The three calculators are sandbox sites we built, each with planted quirks, and each computes one Universal-Credit-shaped "
                  "entitlement. They say nothing about how real calculators behave or what their terms and bot protection allow.")},
        {"id": "eval-claims-simulated", "severity": "medium", "source": "engine-analytics", 
         "text": ("Agent-claim calibration uses simulated runs until real agent runs exist. A low predicted risk of a false claim never replaces "
                  "the code check, which decides success.")},
        {"id": "eval-offhours-s2", "severity": "medium", "source": "agent-core: docs/SPIKES.md S2",
         "text": ("The off-hours live run depends on the conditions spike S2 passed under: macOS Accessibility and Screen Recording granted, an "
                  "unlocked screen, a harmless app, the owner present. The presence forecast and the start-or-wait rule are evaluated on "
                  "synthetic personas; the live demo may fall back to a simulated clock.")},
    ]


def _entry(id_: str, text: str, severity: str, source: str) -> dict[str, str]:
    return {"id": id_, "text": text, "severity": severity, "source": source}


def _num(x: Any) -> float | None:
    return float(x) if isinstance(x, (int, float)) and not isinstance(x, bool) else None


def computed_entries(sections: dict[str, Any]) -> list[dict[str, str]]:
    """Weak or null results, read off the numbers."""
    out: list[dict[str, str]] = []

    def ok(name: str) -> dict[str, Any] | None:
        s = sections.get(name)
        return s if isinstance(s, dict) and "status" not in s else None

    dr = ok("deficit_recovery")
    if dr:
        ov = dr.get("overall") or {}
        weak = []
        for r in dr.get("rows", []):
            if (r.get("recall") is not None and r["recall"] < 0.8) or (r.get("precision") is not None and r["precision"] < 0.8):
                weak.append(f"{r['deficit']} (precision {_pct(r.get('precision'))}, recall {_pct(r.get('recall'))})")
        biased = []
        for r in dr.get("rows", []):
            bci = r.get("bias_ci") or [None, None]
            if bci[0] is not None and (bci[0] > 0 or bci[1] < 0):
                biased.append(f"{r['deficit']} ({r['bias_s']:+.1f} s, interval {_ci(bci)})")
        if weak:
            out.append(_entry("eval-deficit-weak", "Deficit detection is weaker for: " + "; ".join(weak) +
                              f". Overall precision {_pct(ov.get('precision'))}, recall {_pct(ov.get('recall'))} over {ov.get('pairs')} case-deficit pairs.",
                              "medium", "engine-eval:deficit_recovery"))
        if biased:
            out.append(_entry("eval-deficit-bias", "The recovered price differs from the planted price, with an interval that excludes zero, for: " +
                              "; ".join(biased) + ". The alignment names a block of extra steps by its content, so a deficit that shares steps with another is mis-priced.",
                              "medium", "engine-eval:deficit_recovery"))
    npb = ok("null_placebo")
    if npb:
        pl, nl, real = npb.get("placebo", {}), npb.get("null", {}), npb.get("real", {})
        pci = pl.get("ci") or [None, None]
        if pci[0] is not None and not (pci[0] <= 0 <= pci[1]):
            out.append(_entry("eval-placebo-nonzero", f"The expert-versus-expert placebo is not centred on zero: {pl.get('gap_s'):+.1f} s (interval {_ci(pci)}). "
                              "The procedure finds a small gap even where none is planted.", "medium", "engine-eval:null_placebo"))
        rg, ng = _num(real.get("gap_s")), _num(nl.get("gap_s"))
        if rg and ng is not None and abs(ng) > 0.1 * abs(rg):
            out.append(_entry("eval-null-offset", f"The shuffled-label null averages {ng:+.1f} s (interval {_ci(nl.get('ci'))}), about {abs(ng) / abs(rg):.0%} of the real "
                              f"gap of {rg:.1f} s. Matching each case to its nearest reference is not symmetric, so the null is not exactly zero; "
                              "the real gap sits above the null interval, which is the comparison that counts.", "low", "engine-eval:null_placebo"))
    hz = ok("hazard")
    if hz:
        m, tsp, br = hz.get("model") or {}, (hz.get("baselines") or {}).get("time_since_progress") or {}, (hz.get("baselines") or {}).get("base_rate") or {}
        if all(isinstance(x.get("log_loss"), (int, float)) for x in (m, tsp, br)) and not (m["log_loss"] < tsp["log_loss"] and m["log_loss"] < br["log_loss"]):
            out.append(_entry("eval-hazard-not-better", "The stuck hazard does not beat both baselines on held-out log loss.", "high", "engine-eval:hazard"))
        if hz.get("false_alarms_within_budget") is False:
            out.append(_entry("eval-hazard-alarm-budget", f"On held-out people the false-alarm rate is {hz.get('false_alarms_per_hour'):.2f} an hour, over the "
                              f"{hz.get('budget_false_alarms_per_hour')} an hour budget chosen on the training people.", "medium", "engine-eval:hazard"))
    rt = ok("routing")
    if rt and rt.get("bound_held") is False:
        out.append(_entry("eval-routing-bound-failed", "The routing error bound did not hold on the held-out cases.", "high", "engine-eval:routing"))
    op = ok("ope")
    if op:
        tv = _num(op.get("true_value"))
        reps = ((op.get("replications") or {}).get("by_target") or {}).get(op.get("headline_target"), {})
        n_rep = (op.get("replications") or {}).get("n_replications")
        miss, low_cov = [], []
        key = {"ips": "ips", "snips": "snips", "dr": "dr"}
        for e in op.get("estimators", []):
            if e.get("name") in key and tv is not None and e.get("ci") and e["ci"][0] is not None and not (e["ci"][0] <= tv <= e["ci"][1]):
                miss.append(e["name"].upper())
        for name in key:
            cov = _num((reps.get(name) or {}).get("ci_coverage"))
            if cov is not None and cov < 0.9:
                low_cov.append(f"{name.upper()} {_pct(cov)}")
        if miss or low_cov:
            parts = []
            if miss:
                parts.append(f"In the detailed run the interval of {', '.join(miss)} does not contain the true value {tv:.3f}.")
            if reps and n_rep:
                cov_txt = ", ".join(f"{n.upper()} {_pct(_num((reps.get(n) or {}).get('ci_coverage')))}" for n in key if n in reps)
                parts.append(f"Over {n_rep} independent replications the intervals covered the truth: {cov_txt}"
                             f" (naive {_pct(_num((reps.get('naive_on_policy') or {}).get('ci_coverage')))}); nominal is 95%.")
            out.append(_entry("eval-ope-coverage", " ".join(parts), "medium" if low_cov else "low", "engine-eval:ope"))
    ar = ok("agent_runs")
    if ar:
        c, rb, live = ar.get("clean") or {}, ar.get("robust"), ar.get("live")
        lo = (c.get("wilson") or [None])[0]
        out.append(_entry("eval-agent-runs-clean-path",
                          f"The clean-path result ({c.get('pass')} of {c.get('n')} households, 95% lower bound {_pct(lo)}) is the compiled path on the sandbox it was "
                          "written against, so a full pass is expected and says little. The discriminating evidence is the robust and injected runs. "
                          "Twenty households cannot rule out a pass rate well below 100%.", "medium", "engine-eval:agent_runs"))
        if rb:
            inj = rb.get("injected") or []
            t2 = sum(x.get("used_tier2", 0) for x in inj)
            if inj:
                kinds = "; ".join(f"{x['injection']} ({x['pass']} of {x['n']} passed)" for x in inj)
                out.append(_entry("eval-agent-runs-injected",
                                  f"Failure injection covers {len(inj)} patterns only: {kinds}. {t2} of {rb.get('n')} households needed the tier-2 browser agent. "
                                  f"{rb.get('pass')} of {rb.get('n')} passed (95% lower bound {_pct((rb.get('wilson') or [None])[0])}). Other failure kinds (a changed flow, "
                                  "a wrong page, a slow site) were not injected.", "medium", "engine-eval:agent_runs"))
            else:
                out.append(_entry("eval-agent-runs-injected", f"Failure injection ran ({rb.get('pass')} of {rb.get('n')} passed) but the injection plan could not be read "
                                  f"back, so the report cannot say which failures were injected. {rb.get('injected_note') or ''}".strip(), "medium", "engine-eval:agent_runs"))
        else:
            out.append(_entry("eval-agent-runs-no-robust", "No failure-injection run is in this report, so the agent runs show only the clean compiled path.", "high", "engine-eval:agent_runs"))
        disc = ar.get("discrepancies_flagged") or {}
        if disc.get("n"):
            out.append(_entry("eval-agent-runs-discrepancies",
                              f"{disc['n']} of {disc.get('of')} households are planted discrepancies between the sandbox calculators (quirks we wrote). A pass on them "
                              "means the discrepancy was flagged, not that an entitlement was worked out, and the oracle is a simplified rule set, not the law.", "low", "engine-eval:agent_runs"))
        if live:
            out.append(_entry("eval-agent-live-small-n",
                              f"The real-model block has n = {live.get('n')} runs ({live.get('pass')} passed, 95% interval {_ci(live.get('wilson'), 2)}), "
                              f"cost estimate {live.get('cost_usd_est')} USD. Too few to estimate a pass rate; it shows the pipeline works with a live model.", "medium", "engine-eval:agent_runs"))
        else:
            out.append(_entry("eval-agent-live-absent", "Every agent run in this report uses the deterministic mock model on sandbox sites; no real-model run is included"
                              + (f" ({ar['live_error']})." if ar.get("live_error") else "."), "medium", "engine-eval:agent_runs"))
        if (ar.get("false_claims") or 0) > 0:
            out.append(_entry("eval-agent-runs-false-claims", f"The agent made {ar['false_claims']} false success claim(s) across these runs; the code check caught them.", "high", "engine-eval:agent_runs"))
    rl = ok("redteam_live")
    if rl:
        on = next((r for r in rl.get("rows", []) if r.get("ablation") == "all_on"), None)
        if rl.get("reading"):
            out.append(_entry("eval-redteam-live-reading", f"Real-model red team ({rl.get('label')}): {rl['reading']} The attacks were written by the team that wrote the "
                              "defences, and a result is true of one model version on one day.", "high", "engine-eval:redteam_live"))
        if on:
            fp, hn = (on.get("false_pause_rate"), on.get("false_pause_hard_negatives") or {})
            out.append(_entry("eval-redteam-live-in-sample",
                              f"The live false-pause result ({(on.get('n_clean_runs') or 0) and round((fp or 0) * (on.get('n_clean_runs') or 0))} of {on.get('n_clean_runs')} clean runs, "
                              f"{hn.get('k')} of {hn.get('n')} on hard negatives) is in-sample: the layer-7 (goal-drift) scope was changed while building on this same catalog, "
                              "so it is not a held-out rate.", "medium", "engine-eval:redteam_live"))
            if (on.get("attack_success") or 0) > 0:
                out.append(_entry("eval-redteam-live-attacks-succeed", f"With the real model, attacks still succeeded {_pct(on['attack_success'], 1)} of the time with every layer on "
                                  f"(interval {_ci(on.get('attack_ci'), 3)}).", "high", "engine-eval:redteam_live"))
    if ok("study_sim"):
        sim = SIM_PHRASE[0].upper() + SIM_PHRASE[1:]
        src = "engine-eval:study_sim"
        out += [
            _entry("eval-study-sim-not-human", f"{sim}. A language model plays each participant, so nothing in this section says how people behave. "
                   "The live study (n = 4 teammates) is the only human evidence and is reported separately; this section never feeds it.", "high", src),
            _entry("eval-study-sim-planted-by-us", f"{sim}. The coach prompts and the sandbox calculators were written by us, so the simulation checks that the "
                   "pipeline runs end to end under our own assumptions. It does not show that coaching works on anyone.", "high", src),
            _entry("eval-study-sim-learning-proxy", f"{sim}. Learning between blocks is a note carried in the model's prompt, a proxy. It is not memory, practice or "
                   "skill, so a simulated 'improvement' says little about a human one.", "high", src),
            _entry("eval-study-sim-timing", f"{sim}. Times in this section are model response times or scripted numbers, not human reading, thinking or typing, "
                   "so no timing result here is a human timing.", "high", src),
        ]
    if ok("study_power"):
        out.append(_entry("eval-study-power-assumptions", "The power analysis only shows what the n = 4 design could detect under our own assumptions (effect size, "
                          "carryover, order effect, how noisy the measure is). It is a property of the design, not a result about people, and not evidence that an effect exists.",
                          "high", "engine-eval:study_power"))
    rd = ok("redteam")
    if rd:
        on = next((r for r in rd.get("rows", []) if r.get("ablation") == "all_on"), None)
        if on and (on.get("attack_success") or 0) > 0:
            out.append(_entry("eval-redteam-attacks-succeed", f"Attacks still succeed {_pct(on['attack_success'], 1)} of the time with every layer on (interval {_ci(on.get('attack_ci'), 3)}).",
                              "high", "engine-eval:redteam"))
    for name in CORE_SECTIONS:
        s = sections.get(name)
        if isinstance(s, dict) and s.get("status") in ("pending", "not_run", "failed"):
            out.append(_entry(f"eval-{name}-{s['status']}", f"Section '{name}' has no numbers: {s.get('reason')}.", "high", f"engine-eval:{name}"))
    return out


def _sim_text(section: str, text: str) -> str:
    """Every register text that comes from the simulated study says what it is."""
    if section == "study_sim" and SIM_PHRASE not in text.lower():
        return f"{SIM_PHRASE[0].upper() + SIM_PHRASE[1:]}: {text}"
    return text


def _norm(t: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", t.lower()).strip()[:70]


def assemble(sections: dict[str, Any]) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    by_id: dict[str, dict[str, str]] = {}
    seen_text: set[str] = set()

    def add(e: dict[str, str]) -> None:
        if e["id"] in by_id:
            have = by_id[e["id"]]
            if e["source"] not in have["source"].split("; "):
                have["source"] += "; " + e["source"]
            return
        entries.append(e)
        by_id[e["id"]] = e
        seen_text.add(_norm(e["text"]))

    for e in static_entries(sections):
        add(e)
    umbrella = by_id[UMBRELLA]
    folded: list[str] = []
    deferred: list[tuple[str, str, str, str]] = []
    for name, s in sections.items():
        if not isinstance(s, dict) or "status" in s:
            continue
        owner = OWNER.get(name, "engine-eval")
        for lim in s.get("limitations") or []:
            sev = lim.get("severity") if lim.get("severity") in SEV_RANK else "medium"
            if lim["id"] in FOLD_INTO_UMBRELLA:
                folded.append(f"{owner}:{name}")
                continue
            text = _sim_text(name, str(lim["text"]))
            if lim["id"] in ABSORB:
                deferred.append((ABSORB[lim["id"]], text, sev, f"{owner}:{name}"))      # merged after the computed entries exist
                continue
            add(_entry(str(lim["id"]), text, sev, f"{owner}:{name}"))
    for e in computed_entries(sections):
        add(e)
    for target, text, sev, source in deferred:
        add(_entry(target, text, sev, source))          # merges into the entry that says the same thing; kept only if there is none
    for name, s in sections.items():
        if not isinstance(s, dict) or "status" in s:
            continue
        owner = OWNER.get(name, "engine-eval")
        for k, c in enumerate(s.get("caveats") or []):
            head = c.strip().split(":", 1)[0]
            if not (":" in c and head.isupper() and head.isalpha()):
                continue
            if _norm(c) in seen_text:
                continue
            add(_entry(f"{name}-{head.lower()}", _sim_text(name, c.strip()), "medium", f"{owner}:{name} caveat"))
    if folded:
        umbrella["source"] += "; also stated by " + ", ".join(sorted(set(folded)))
    order = {e["id"]: i for i, e in enumerate(entries)}
    entries.sort(key=lambda e: (SEV_RANK.get(e["severity"], 3), order[e["id"]]))
    return entries
