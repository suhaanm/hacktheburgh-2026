"""REPORT.md from the assembled section. Every number is read from the section; prose is generated from the numbers.

A hand-written interpretation is added to the file separately (``evals/realism/INTERPRETATION.md`` is appended by the author
after reading the matrix) and is labelled as such: it is never mixed into the generated tables.
"""
from __future__ import annotations

from typing import Any

FAMS = ("markov", "latent_skill", "process_trace")
ALL = ("v1",) + FAMS


def f(e: dict | None, nd: int = 3, pct: bool = False) -> str:
    if not e or e.get("est") is None:
        return "n/a"
    k = 100 if pct else 1
    ci = e.get("ci") or [None, None]
    sfx = "%" if pct else ""
    if ci[0] is None:
        return f"{e['est'] * k:.{nd}f}{sfx}"
    return f"{e['est'] * k:.{nd}f}{sfx} [{ci[0] * k:.{nd}f}, {ci[1] * k:.{nd}f}]"


def _fmt_delta(d: dict | None, nd: int = 3) -> str:
    if not d:
        return ""
    ci = d["ci"]
    if ci[0] is None:
        return f"{d['est']:+.{nd}f}"
    v = d["verdict"]
    if v == "inconclusive" and ci[0] > 0:
        v = "inconclusive (better than the diagonal; the rule is unchanged)"
    return f"{d['est']:+.{nd}f} [{ci[0]:+.{nd}f}, {ci[1]:+.{nd}f}] {v}"


def _matrix(cells: dict, rows_axis: tuple, cols_axis: tuple, getter, prefix: str = "") -> list[str]:
    head = "| fit on \\ test on | " + " | ".join(cols_axis) + " |"
    out = [head, "|---|" + "---|" * len(cols_axis)]
    for X in rows_axis:
        row = [f"**{X}**"]
        for Y in cols_axis:
            c = cells.get(f"{prefix}{X}->{Y}")
            row.append(getter(c) if c else "n/a")
        out.append("| " + " | ".join(row) + " |")
    return out


def _axes(cells: dict, prefix: str = "") -> tuple[tuple, tuple]:
    present = {k[len(prefix):] for k in cells if k.startswith(prefix)}
    xs = tuple(a for a in ALL if any(p.startswith(a + "->") for p in present))
    ys = tuple(a for a in ALL if any(p.endswith("->" + a) for p in present))
    return xs, ys


def _tally(cells: dict, metric: str, prefix: str = "") -> dict[str, int]:
    t = {"degrades": 0, "transfers": 0, "inconclusive": 0}
    for k, c in cells.items():
        if not k.startswith(prefix):
            continue
        d = (c.get("delta_vs_diagonal") or {}).get(metric)
        if d:
            t[d["verdict"]] += 1
    return t


def _pairs(cells: dict, metric: str, prefix: str = "") -> list[tuple[str, str, str]]:
    out = []
    for k, c in cells.items():
        if not k.startswith(prefix):
            continue
        d = (c.get("delta_vs_diagonal") or {}).get(metric)
        if d:
            X, Y = k[len(prefix):].split("->")
            out.append((X, Y, d["verdict"]))
    return out


def write_report(sec: dict[str, Any]) -> str:
    cfg, gen, res = sec["config"], sec["generator"], sec["results"]
    L: list[str] = []
    add = L.append
    add("# Realism and generator-mismatch evaluation (REALISM track)")
    add("")
    add(f"*origin: **generated, realism-calibrated** · fast mode: {'yes (small n)' if cfg['fast'] else 'no'} · v1 included: {'yes' if cfg['with_v1'] else 'no'} · "
        f"intervals: 95% person-cluster bootstrap, B = {cfg['bootstrap_B']}*")
    add("")
    add("Written by `python -m understudy_engine.personas_v2.evaluate` under the pre-registration in `evals/realism/PLAN.md` (frozen before any analytic ran on v2 data). "
        "No number is typed by hand. **These data are generated. Marginals sit inside cited ranges where a constant was found; that does not show the data match real people, "
        "and the generators were written by the same team as the analytics.**")
    add("")
    add(f"Generator: params SHA-256 `{gen['params_sha256']}`, generator SHA-256 `{gen['generator_sha256']}` (the values in PLAN.md are "
        "`23a71289f6c4795ce412592b0eb0edf598a2573b00428303e594e98b4b8b4ddc` and `ae32e7be05ce2002820f3185dd7935e29c074ccca66461f3644a9c82ae87f242`: "
        + ("**they match**" if gen["params_sha256"].startswith("23a71289") and gen["generator_sha256"].startswith("ae32e7be") else "**MISMATCH: the generator changed after the plan was frozen; see Deviations**") + ").")
    add("")
    add(f"Sizes: K = {cfg['K']} replicates per (family, role); workweeks {cfg['n_workweek_people']} people x {cfg['workweek_days']} days; cohort {cfg['n_cohort_people']} people x {cfg['cases_per_person']} cases "
        f"(genome uses the first {cfg['genome_cases_per_person']} cases per person); roles: {', '.join(gen['roles'])}. Elapsed {res.get('elapsed_s')} s.")
    add("")

    # ------------------------------------------------------------------------------------------ marginals
    add("## 1. Marginal checks: is each family within published ranges?")
    add("")
    add("The claim is only ever *within the cited range*. 'Constant status' says how well the range was verified: `secondary` (read from a search summary; the primary was not opened), "
        "`assumption` (a wide range we assumed; not called published), `qualitative` (sign only). Counts are datasets (role x family x replicate) inside the range.")
    add("")
    add("| Check | What | Range | Inside | Outside | Median [min, max] | Constant status |")
    add("|---|---|---|---|---|---|---|")
    mg = res["marginals"]["cohort"]
    for cid in sorted(mg, key=lambda x: (x[0], int("".join(ch for ch in x[1:] if ch.isdigit()) or 0), x)):
        m = mg[cid]
        rg = "informational" if not m["range"] else f"{m['range'][0]:g} to {m['range'][1]:g}"
        add(f"| {cid} | {m['what']} | {rg} | {m['inside']} | {m['outside']} | {m['median']} [{m['min']}, {m['max']}] | {m['constant_status']} |")
    add("")
    add("Per family (inside / outside, datasets):")
    add("")
    add("| Check | " + " | ".join(FAMS) + " |")
    add("|---|" + "---|" * len(FAMS))
    for cid in sorted(mg, key=lambda x: (x[0], int("".join(ch for ch in x[1:] if ch.isdigit()) or 0), x)):
        cells = []
        for fam in FAMS:
            m = res["marginals"]["by_family"][fam].get(cid)
            cells.append(f"{m['inside']} / {m['outside']}" + (f" (n/a {m['not_applicable']})" if m and m["not_applicable"] else "") if m else "n/a")
        add(f"| {cid} | " + " | ".join(cells) + " |")
    add("")
    add("Checks outside their range are listed, not hidden. M5c is informational: the fitted slope understates the learning exponent because the fit includes the asymptote and most "
        "novices have tenure above the 8 cases observed. M10 is a sign check: with 40 people the sample correlation is noisy when the general-factor loading is small.")
    add("")
    add("### Label decoupling in the workweek data (M13): the hazard label is not the hidden stuck state")
    add("")
    add("| Check | What | Median [min, max] over datasets |")
    add("|---|---|---|")
    for cid, m in sorted(res["marginals"]["workweeks_label"].items()):
        add(f"| {cid} | {m['what']} | {m['median']} [{m['min']}, {m['max']}] |")
    add("")
    add("v1 for comparison: 25% of label-1 bins lie inside a planted stuck spell (`DIAGNOSIS.md`).")
    add("")

    # ------------------------------------------------------------------------------------------ hazard
    add("## 2. Stuck hazard under generator mismatch")
    add("")
    add("H1 = gain over the time-since-progress baseline, `LL_tsp - LL_full` per bin (nats; person-weighted mean over test people; positive = the model helps). "
        "Rows: the family the model and alarm rule were fitted on (training replicate k). Columns: the family tested (an independent replicate; the diagonal is a new draw of the same family, "
        "except v1, whose diagonal is leave-one-persona-out over its four personas). Interval: person-cluster bootstrap over the test people. "
        "Each cell is paired with the diagonal on the same test people; verdicts follow the pre-registered rule (margin 0.01 nats).")
    add("")
    for role, hz in res["hazard"].items():
        cells = hz["cells"]
        xs, ys = _axes(cells)
        add(f"### {role}")
        add("")
        add("**H1, gain over time-since-progress (nats per bin)**")
        add("")
        L.extend(_matrix(cells, xs, ys, lambda c: f(c["metrics"]["h1"], 3)))
        add("")
        add("**Degradation: delta H1 against the diagonal (off-diagonal minus diagonal), with the pre-registered verdict**")
        add("")
        L.extend(_matrix(cells, xs, ys, lambda c: _fmt_delta((c.get("delta_vs_diagonal") or {}).get("h1")) if c.get("delta_vs_diagonal") else "diagonal"))
        add("")
        add("**False alarms per non-stuck hour at the transferred alarm rule (budget 1.0)**")
        add("")
        L.extend(_matrix(cells, xs, ys, lambda c: f(c["metrics"]["fa_per_h"], 2) + (" OVER" if c.get("fa_over_budget") else "")))
        add("")
        add("**Detection rate (share of stuck events with an alarm)**")
        add("")
        L.extend(_matrix(cells, xs, ys, lambda c: f(c["metrics"]["detection"], 2)))
        add("")
        add("**Log loss of the full model, time-since-progress baseline and base rate (test families on the diagonal)**")
        add("")
        add("| Test family | label rate | full | time since progress | base rate | bins | no skill? |")
        add("|---|---|---|---|---|---|---|")
        for Y in ys:
            c = cells.get(f"{Y}->{Y}")
            if c:
                m = c["metrics"]
                add(f"| {Y} | {f(m['label_rate'], 3)} | {f(m['ll_full'], 3)} | {f(m['ll_tsp'], 3)} | {f(m['ll_base'], 3)} | {c['n_bins']} | {'YES' if c['no_skill'] else 'no'} |")
        add("")
        t = _tally(cells, "h1")
        no_skill = [k for k, c in cells.items() if c["no_skill"]]
        add(f"Verdicts over the off-diagonal cells: {t['degrades']} degrade, {t['transfers']} transfer, {t['inconclusive']} inconclusive. "
            f"Cells where the gain over time-since-progress is not clearly positive (no skill): {', '.join(no_skill) if no_skill else 'none'}.")
        add("")

    lp = res.get("lopo")
    if lp:
        add("### Leave-one-person-out diagnostics (the public `evaluate_hazard`, benefits processor, replicate 0; v1 = its four personas)")
        add("")
        add("Nested leave-one-person-out with the alarm rule chosen on the training people only, as the shipped evaluation does. Intervals here resample episodes (the function's own), not people.")
        add("")
        add("| Family | people | bins | label rate | log loss full | time since progress | base rate | gain over time since progress | false alarms / h | detection | within budget |")
        add("|---|---|---|---|---|---|---|---|---|---|---|")
        for fam in ("v1",) + FAMS:
            r = lp.get(fam)
            if r:
                add(f"| {fam} | {r['n_people']} | {r['n_bins']} | {r['label_rate']} | {f(r['ll_full'])} | {f(r['ll_tsp'])} | {f(r['ll_base'])} | {f(r['gain_over_tsp'])} | {f(r['fa_per_h'], 2)} | {f(r['detection'], 2)} | {r['within_budget']} |")
        add("")
    # ------------------------------------------------------------------------------------------ genome
    add("## 3. Genome deficit recovery under mismatch (benefits processor)")
    add("")
    add("Present = the deficit cost the person at least 5 s on that case; absent = it never occurred; indeterminate (excluded) otherwise. The method aligns each novice case to the "
        "nearest expert of the *fitting* family and attributes seconds to deficit cog families; a deficit is detected when the attribution reaches `X_d` (the 95th percentile of what the "
        "same procedure attributes between two experts of the fitting family, at least 1 s). G1 pools over deficits.")
    add("")
    for role, gm in res["genome"].items():
        cells = gm["cells"]
        xs, ys = _axes(cells)
        add(f"### {role}")
        add("")
        for metric, title in (("precision", "G1 precision"), ("recall", "G1 recall")):
            add(f"**{title}**")
            add("")
            L.extend(_matrix(cells, xs, ys, lambda c, metric=metric: f(c["metrics"][metric], 2, pct=True)))
            add("")
            add(f"**{title}: delta against the diagonal with verdict (margin 0.10)**")
            add("")
            L.extend(_matrix(cells, xs, ys, lambda c, metric=metric: _fmt_delta((c.get("delta_vs_diagonal") or {}).get(metric), 2) if c.get("delta_vs_diagonal") else "diagonal"))
            add("")
        add("**Diagonal cells, per deficit** (bias = recovered minus true price, seconds, among present pairs; false attribution = seconds the method puts on a deficit that never occurred)")
        add("")
        add("| Family | deficit | present pairs | precision | recall | bias (s) |")
        add("|---|---|---|---|---|---|")
        from .eval_genome import DEFICITS

        for Y in ys:
            c = cells.get(f"{Y}->{Y}")
            if not c:
                continue
            for d in DEFICITS:
                m = c["metrics"]
                add(f"| {Y} | {d} | {int(m[f'n_present:{d}']['est'] or 0)} | {f(m[f'precision:{d}'], 2, pct=True)} | {f(m[f'recall:{d}'], 2, pct=True)} | {f(m[f'bias_s:{d}'], 1)} |")
        add("")
        add("| Family (diagonal) | present pairs | absent pairs | indeterminate | false attribution (s per absent pair) | mean gap to nearest expert (s per case) |")
        add("|---|---|---|---|---|---|")
        for Y in ys:
            c = cells.get(f"{Y}->{Y}")
            if c:
                m = c["metrics"]
                add(f"| {Y} | {int(m['n_present']['est'])} | {int(m['n_absent']['est'])} | {int(m['n_indeterminate']['est'])} | {f(m['false_attr_s'], 2)} | {f(m['gap_s'], 1)} |")
        add("")
        add("Placebo (expert against nearest other expert) and the share of expert cases carrying a material deficit (reference contamination), per training dataset:")
        add("")
        add("| Dataset | contamination | max placebo attribution per deficit (s) | thresholds X_d (s) |")
        add("|---|---|---|---|")
        for k, v in gm["placebo"].items():
            add(f"| {k} | {v['expert_contamination']} | {v['max_attribution_s']} | {gm['thresholds_s'][k]} |")
        add("")
        tp, tr = _tally(cells, "precision"), _tally(cells, "recall")
        add(f"Verdicts over the off-diagonal cells: precision {tp['degrades']} degrade, {tp['transfers']} transfer, {tp['inconclusive']} inconclusive; "
            f"recall {tr['degrades']} degrade, {tr['transfers']} transfer, {tr['inconclusive']} inconclusive.")
        add("")

    # ------------------------------------------------------------------------------------------ routines
    add("## 4. Routine finder under mismatch")
    add("")
    add("R1 = cluster precision of the raw finder (true clusters over clusters returned), R2 = recall of detectable planted routines, R3 = precision over proposals after the value gate "
        "(shipped config). 'fitted' = the cut height chosen on the fitting family's people; 'shipped' = the fixed 0.35 (no fitting).")
    add("")
    for role, rt in res["routines"].items():
        cells = rt["cells"]
        add(f"### {role}")
        add("")
        add(f"Tuned cut heights (grid value with the best pooled F1 on the training people): {rt['tuned_threshold']}")
        add("")
        for mode in ("fitted", "shipped"):
            xs, ys = _axes(cells, f"{mode}:")
            for metric, title in (("r1_precision", "R1 cluster precision"), ("r2_recall", "R2 recall")):
                add(f"**{title} ({mode})**")
                add("")
                L.extend(_matrix(cells, xs, ys, lambda c, metric=metric: f(c["metrics"][metric], 2, pct=True), f"{mode}:"))
                add("")
            if mode == "fitted":
                add("**Delta against the diagonal with verdict (margin 0.10), fitted**")
                add("")
                for metric in ("r1_precision", "r2_recall"):
                    add(f"{metric}:")
                    add("")
                    L.extend(_matrix(cells, xs, ys, lambda c, metric=metric: _fmt_delta((c.get("delta_vs_diagonal") or {}).get(metric), 2) if c.get("delta_vs_diagonal") else "diagonal", "fitted:"))
                    add("")
        xs, ys = _axes(cells, "shipped:")
        add("**R3 proposal precision after the value gate (shipped config)**")
        add("")
        if cfg["proposals"]:
            L.extend(_matrix(cells, xs, ys, lambda c: (f(c["metrics"]["r3_proposal_precision"], 2, pct=True) + f" ({c['metrics']['proposals_per_person']['est']:.1f} per person)")
                             if c["metrics"]["proposals_per_person"]["est"] else "no proposals", "shipped:"))
        else:
            add("not run in fast mode")
        add("")
        t1, t2 = _tally(cells, "r1_precision", "fitted:"), _tally(cells, "r2_recall", "fitted:")
        add(f"Verdicts over the fitted off-diagonal cells: R1 {t1['degrades']} degrade, {t1['transfers']} transfer, {t1['inconclusive']} inconclusive; "
            f"R2 {t2['degrades']} degrade, {t2['transfers']} transfer, {t2['inconclusive']} inconclusive.")
        add("")

    # ------------------------------------------------------------------------------------------ expectations
    add("## 5. The five pre-registered expectations next to what was found")
    add("")
    L.extend(expectations(res))
    add("")
    add("## 6. Deviations from the pre-registered plan")
    add("")
    for d in sec.get("deviations", []):
        add(f"* {d}")
    add("")
    add("## 7. Limitations and honesty")
    add("")
    for l in sec["limitations"]:
        add(f"* **{l['id']}** ({l['severity']}): {l['text']}")
    add("")
    add("### Citation status of the constants the generators use")
    add("")
    add("| Constant | Status | Range | Source |")
    add("|---|---|---|---|")
    for k, v in sec["cited_constants"].items():
        rg = "n/a" if not v["range"] else f"{v['range'][0]:g} to {v['range'][1]:g}"
        add(f"| {k} | {v['status']} | {rg} | {v['source']} |")
    add("")
    add("`secondary` means the number was read from a search summary or a page that quotes the paper; the paper itself was not opened. `assumption` entries are not citations.")
    add("")
    add("See `evals/realism/INTERPRETATION.md` for the hand-written reading of this matrix (written after the run; not part of the pre-registration) and `evals/realism/DIAGNOSIS.md` for why v1 was easy.")
    return "\n".join(L) + "\n"


def _cell(res, analytic, role, key, metric="h1"):
    try:
        return res[analytic][role]["cells"][key]["metrics"][metric]
    except KeyError:
        return None


def expectations(res: dict[str, Any]) -> list[str]:
    out: list[str] = []
    role = "benefits-processor"
    # 1 hazard gain smaller on every v2 family than v1
    v1 = _cell(res, "hazard", role, "v1->v1")
    out.append("**1. The hazard's gain over time-since-progress is smaller on every v2 family than on v1, and stays positive on most v2 families.**")
    lp = res.get("lopo") or {}
    if lp.get("v1"):
        out.append(f"  Leave-one-person-out (public function): v1 gain {f(lp['v1']['gain_over_tsp'])}; " + "; ".join(f"{k} {f(lp[k]['gain_over_tsp'])}" for k in FAMS if k in lp) + ".")
    if v1:
        diag = {Y: _cell(res, "hazard", role, f"{Y}->{Y}") for Y in FAMS}
        smaller = [Y for Y, c in diag.items() if c and c["est"] < v1["est"]]
        pos = [Y for Y, c in diag.items() if c and c["ci"][0] is not None and c["ci"][0] > 0]
        out.append(f"  Found: v1 diagonal H1 {f(v1)}; v2 diagonals " + "; ".join(f"{Y} {f(c)}" for Y, c in diag.items() if c) +
                   f". Smaller than v1 on {len(smaller)} of 3 families ({', '.join(smaller) or 'none'}); clearly positive (interval above 0) on {len(pos)} of 3 ({', '.join(pos) or 'none'}).")
    else:
        out.append("  Not assessable in this run (v1 omitted).")
    # 2 cross-family gains smaller than diagonal; FA overshoot more often
    out.append("")
    out.append("**2. Cross-family hazard gains are smaller than the diagonal in most cells, and the transferred alarm rule overshoots the false-alarm budget in more cells than the diagonal does.**")
    for role_, hz in res["hazard"].items():
        cells = hz["cells"]
        off = [(k, c) for k, c in cells.items() if c.get("delta_vs_diagonal")]
        lower = sum(1 for k, c in off if c["delta_vs_diagonal"]["h1"]["est"] < 0)
        over_off = sum(1 for k, c in off if c["fa_over_budget"])
        diag = [c for k, c in cells.items() if not c.get("delta_vs_diagonal")]
        over_diag = sum(1 for c in diag if c["fa_over_budget"])
        out.append(f"  {role_}: delta H1 below zero in {lower} of {len(off)} off-diagonal cells; false-alarm interval entirely above the 1.0 budget in {over_off} of {len(off)} off-diagonal cells versus {over_diag} of {len(diag)} diagonal cells.")
    # 3 genome
    out.append("")
    out.append("**3. Genome recall for the named deficits falls well below v1's 95 percent (guess 0.4 to 0.8), and precision falls because legitimate verification re-reads look like repeated reads.**")
    gm = res["genome"].get(role)
    if gm:
        cells = gm["cells"]
        for Y in ALL:
            c = cells.get(f"{Y}->{Y}")
            if c:
                out.append(f"  {Y} diagonal: precision {f(c['metrics']['precision'], 2, True)}, recall {f(c['metrics']['recall'], 2, True)}, false attribution {f(c['metrics']['false_attr_s'], 2)} s per absent pair.")
    else:
        out.append("  Not assessed.")
    # 4 routines
    out.append("")
    out.append("**4. Routine finder cluster precision stays low (v1: 22 percent) and recall falls below v1's 100 percent (drift, interleaving, split episodes).**")
    rt = res["routines"].get(role)
    if rt:
        for Y in ALL:
            c = rt["cells"].get(f"shipped:{Y}->{Y}")
            if c:
                out.append(f"  {Y} (shipped config, diagonal): R1 {f(c['metrics']['r1_precision'], 2, True)}, R2 {f(c['metrics']['r2_recall'], 2, True)}, R3 {f(c['metrics']['r3_proposal_precision'], 2, True)}.")
    # 5 process_trace involvement
    out.append("")
    out.append("**5. The largest degradations involve process_trace as either side.**")
    tally: dict[str, int] = {"with_pt": 0, "without_pt": 0}
    tot = {"with_pt": 0, "without_pt": 0}
    for analytic, metrics, prefix in (("hazard", ("h1",), ""), ("genome", ("precision", "recall"), ""), ("routines", ("r1_precision", "r2_recall"), "fitted:")):
        for role_, d in res[analytic].items():
            for metric in metrics:
                for X, Y, v in _pairs(d["cells"], metric, prefix):
                    if "v1" in (X, Y) or X == Y:
                        continue
                    key = "with_pt" if "process_trace" in (X, Y) else "without_pt"
                    tot[key] += 1
                    if v == "degrades":
                        tally[key] += 1
    out.append(f"  Among v2-to-v2 off-diagonal verdicts: {tally['with_pt']} of {tot['with_pt']} involving process_trace degrade, {tally['without_pt']} of {tot['without_pt']} between markov and latent_skill degrade.")
    return out
