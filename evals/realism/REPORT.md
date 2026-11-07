# Realism and generator-mismatch evaluation (REALISM track)

*origin: **synthetic, realism-calibrated** · fast mode: no · v1 included: yes · intervals: 95% person-cluster bootstrap, B = 1000*

Written by `python -m understudy_engine.personas_v2.evaluate` under the pre-registration in `evals/realism/PLAN.md` (frozen before any analytic ran on v2 data). No number is typed by hand. **These data are synthetic. Marginals sit inside cited ranges where a constant was found; that does not show the data match real people, and the generators were written by the same team as the analytics.**

Generator: params SHA-256 `23a71289f6c4795ce412592b0eb0edf598a2573b00428303e594e98b4b8b4ddc`, generator SHA-256 `ae32e7be05ce2002820f3185dd7935e29c074ccca66461f3644a9c82ae87f242` (the values in PLAN.md are `23a71289f6c4795ce412592b0eb0edf598a2573b00428303e594e98b4b8b4ddc` and `ae32e7be05ce2002820f3185dd7935e29c074ccca66461f3644a9c82ae87f242`: **they match**).

Sizes: K = 3 replicates per (family, role); workweeks 40 people x 14 days; cohort 48 people x 8 cases (genome uses the first 2 cases per person); roles: benefits-processor, data-analyst, programmer. Elapsed 21.1 s.

## 1. Marginal checks: is each family within published ranges?

The claim is only ever *within the cited range*. 'Constant status' says how well the range was verified: `secondary` (read from a search summary; the primary was not opened), `assumption` (a wide range we assumed; not called published), `qualitative` (sign only). Counts are datasets (role x family x replicate) inside the range.

| Check | What | Range | Inside | Outside | Median [min, max] | Constant status |
|---|---|---|---|---|---|---|
| M1 | share of people whose effective KLM keystroke time K is inside 0.12 to 1.2 s | 0.99 to 1 | 9 | 0 | 1.0 [1.0, 1.0] | secondary |
| M2a | mean pointing time P (Fitts, mean ID 2.89 bits), s | 0.4 to 1.8 | 9 | 0 | 0.7961 [0.5612, 1.0657] | secondary |
| M2b | mean ISO throughput of the pointing times, bits/s | 2.5 to 6 | 9 | 0 | 3.63 [2.7118, 5.1498] | secondary |
| M2c | Fitts slope b, s per bit | 0.08 to 0.2 | 9 | 0 | 0.1542 [0.1221, 0.1968] | secondary |
| M2d | Hick-Hyman slope, s per bit (range is our assumption) | 0.05 to 0.3 | 9 | 0 | 0.199 [0.0595, 0.2978] | assumption |
| M3 | pause durations: p99 over median (leptokurtic, mixture of lognormals) | 5 to 400 | 20 | 3 | 18.2211 [2.8566, 80.2676] | secondary |
| M4 | Kolmogorov-Smirnov distance of expert log dwell residuals to a normal (lognormal body) | 0 to 0.15 | 27 | 0 | 0.0322 [0.0168, 0.0657] | secondary |
| M5a | share of people whose learning exponent is inside 0.1 to 1.0 (power law or exponential curve) | 0.9 to 1 | 25 | 2 | 1.0 [0.8542, 1.0] | secondary |
| M5b | median over low-tenure people of (median of last 3 cases) / (median of first 2 cases): learning is visible | 0.3 to 0.98 | 21 | 1 | 0.7921 [0.5378, 0.9806] | secondary |
| M5c | (informational) median fitted slope of log time on log practice among novices | 0.1 to 1 | 0 | 0 | 0.2859 [-0.0857, 0.6401] | secondary |
| M6 | interruptions per hour of task time | 0.5 to 6 | 27 | 0 | 1.6987 [0.6021, 3.1976] | secondary |
| M7 | coefficient of variation of inter-event times within a case | 1.1 to 20 | 27 | 0 | 5.2514 [2.0531, 12.2159] | secondary |
| M8 | share of people whose slip probability per step is inside 0.04 to 6.5 percent (cited range across field types) | 0.9 to 1 | 23 | 4 | 1.0 [0.8125, 1.0] | secondary |
| M9 | between-person SD of log speed | 0.1 to 0.35 | 27 | 0 | 0.1952 [0.1295, 0.2905] | secondary |
| M10 | correlation across people of slowness with slip probability (faster people slip less: positive) | 0 to 1 | 26 | 1 | 0.3044 [-0.1271, 0.46] | qualitative |
| M11 | mean fatigue slope per hour | 0 to 0.15 | 27 | 0 | 0.0434 [0.0008, 0.1192] | qualitative |
| M12a | share of events that look like double fires (same person, type and label within 0.4 s) | 0 to 0.25 | 27 | 0 | 0.0613 [0.0159, 0.1534] | secondary |
| M12b | share of cases with no task_end marker | 0 to 0.12 | 27 | 0 | 0.0391 [0.0, 0.0703] | secondary |
| M13a | base rate of the hazard label (no progress in the next 60 s) | 0.02 to 0.8 | 0 | 0 | 0.3346 [0.1888, 0.5299] | secondary |
| M13b | share of label-1 bins that fall inside a hidden stuck episode (v1: 0.25) | 0.02 to 0.98 | 27 | 0 | 0.2063 [0.0206, 0.5935] | secondary |
| M13c | share of bins inside a hidden stuck episode that are label 1 | 0.02 to 0.98 | 27 | 0 | 0.5577 [0.3927, 0.7043] | secondary |
| M13d | share of hidden stuck episodes that still contain a progress event | 0.02 to 0.98 | 27 | 0 | 0.2458 [0.04, 0.4753] | secondary |
| S1 | material deficit occurrences per novice case | 0.1 to 2.5 | 24 | 3 | 0.2176 [0.0685, 2.0039] | assumption |
| S2 | material deficit occurrences per expert case (experts are not clean) | 0 to 0.8 | 27 | 0 | 0.0329 [0.0, 0.7578] | assumption |
| S3 | share of people with no material deficit in any case | 0.03 to 0.9 | 25 | 2 | 0.5208 [0.0, 0.7708] | assumption |
| S4 | hidden stuck episodes per case | 0.1 to 2 | 24 | 3 | 0.5078 [0.0651, 2.1641] | assumption |
| S5 | share of novice cases faster than the expert median (the labels overlap) | 0.01 to 0.45 | 27 | 0 | 0.1875 [0.0216, 0.3843] | assumption |
| S6a | median expert case duration, s | 300 to 1000 | 27 | 0 | 382.075 [267.015, 718.9] | assumption |
| S6b | novice over expert median duration | 1.1 to 2.2 | 26 | 1 | 1.3893 [1.0989, 2.0097] | assumption |

Per family (inside / outside, datasets):

| Check | markov | latent_skill | process_trace |
|---|---|---|---|
| M1 | 0 / 0 (n/a 9) | 0 / 0 (n/a 9) | 9 / 0 |
| M2a | 0 / 0 (n/a 9) | 0 / 0 (n/a 9) | 9 / 0 |
| M2b | 0 / 0 (n/a 9) | 0 / 0 (n/a 9) | 9 / 0 |
| M2c | 0 / 0 (n/a 9) | 0 / 0 (n/a 9) | 9 / 0 |
| M2d | 0 / 0 (n/a 9) | 0 / 0 (n/a 9) | 9 / 0 |
| M3 | 2 / 3 (n/a 4) | 9 / 0 | 9 / 0 |
| M4 | 9 / 0 | 9 / 0 | 9 / 0 |
| M5a | 8 / 1 | 8 / 1 | 9 / 0 |
| M5b | 6 / 1 (n/a 2) | 8 / 0 (n/a 1) | 7 / 0 (n/a 2) |
| M5c | 0 / 0 (n/a 9) | 0 / 0 (n/a 9) | 0 / 0 (n/a 9) |
| M6 | 9 / 0 | 9 / 0 | 9 / 0 |
| M7 | 9 / 0 | 9 / 0 | 9 / 0 |
| M8 | 8 / 1 | 8 / 1 | 7 / 2 |
| M9 | 9 / 0 | 9 / 0 | 9 / 0 |
| M10 | 9 / 0 | 9 / 0 | 8 / 1 |
| M11 | 9 / 0 | 9 / 0 | 9 / 0 |
| M12a | 9 / 0 | 9 / 0 | 9 / 0 |
| M12b | 9 / 0 | 9 / 0 | 9 / 0 |
| M13a | 0 / 0 (n/a 9) | 0 / 0 (n/a 9) | 0 / 0 (n/a 9) |
| M13b | 9 / 0 | 9 / 0 | 9 / 0 |
| M13c | 9 / 0 | 9 / 0 | 9 / 0 |
| M13d | 9 / 0 | 9 / 0 | 9 / 0 |
| S1 | 8 / 1 | 8 / 1 | 8 / 1 |
| S2 | 9 / 0 | 9 / 0 | 9 / 0 |
| S3 | 8 / 1 | 9 / 0 | 8 / 1 |
| S4 | 7 / 2 | 9 / 0 | 8 / 1 |
| S5 | 9 / 0 | 9 / 0 | 9 / 0 |
| S6a | 9 / 0 | 9 / 0 | 9 / 0 |
| S6b | 9 / 0 | 9 / 0 | 8 / 1 |

Checks outside their range are listed, not hidden. M5c is informational: the fitted slope understates the learning exponent because the fit includes the asymptote and most novices have tenure above the 8 cases observed. M10 is a sign check: with 40 people the sample correlation is noisy when the general-factor loading is small.

### Label decoupling in the workweek data (M13): the hazard label is not the hidden stuck state

| Check | What | Median [min, max] over datasets |
|---|---|---|
| M13a | base rate of the hazard label (no progress in the next 60 s) | 0.3877 [0.2312, 0.6229] |
| M13b | share of label-1 bins that fall inside a hidden stuck episode (v1: 0.25) | 0.1683 [0.0256, 0.58] |
| M13c | share of bins inside a hidden stuck episode that are label 1 | 0.5746 [0.3779, 0.742] |
| M13d | share of hidden stuck episodes that still contain a progress event | 0.1652 [0.0413, 0.3416] |

v1 for comparison: 25% of label-1 bins lie inside a planted stuck spell (`DIAGNOSIS.md`).

## 2. Stuck hazard under generator mismatch

H1 = gain over the time-since-progress baseline, `LL_tsp - LL_full` per bin (nats; person-weighted mean over test people; positive = the model helps). Rows: the family the model and alarm rule were fitted on (training replicate k). Columns: the family tested (an independent replicate; the diagonal is a new draw of the same family, except v1, whose diagonal is leave-one-persona-out over its four personas). Interval: person-cluster bootstrap over the test people. Each cell is paired with the diagonal on the same test people; verdicts follow the pre-registered rule (margin 0.01 nats).

### benefits-processor

**H1, gain over time-since-progress (nats per bin)**

| fit on \ test on | v1 | markov | latent_skill | process_trace |
|---|---|---|---|---|
| **v1** | 0.071 [0.055, 0.083] | -0.488 [-0.559, -0.421] | -0.432 [-0.487, -0.382] | -0.532 [-0.598, -0.468] |
| **markov** | 0.014 [0.012, 0.017] | 0.008 [0.004, 0.011] | 0.010 [0.007, 0.013] | 0.008 [0.004, 0.011] |
| **latent_skill** | 0.035 [0.028, 0.039] | 0.000 [-0.003, 0.004] | 0.015 [0.012, 0.018] | -0.000 [-0.004, 0.003] |
| **process_trace** | 0.018 [0.015, 0.020] | 0.013 [0.009, 0.016] | 0.006 [0.004, 0.008] | 0.012 [0.010, 0.015] |

**Degradation: delta H1 against the diagonal (off-diagonal minus diagonal), with the pre-registered verdict**

| fit on \ test on | v1 | markov | latent_skill | process_trace |
|---|---|---|---|---|
| **v1** | diagonal | -0.495 [-0.569, -0.427] degrades | -0.447 [-0.503, -0.398] degrades | -0.544 [-0.611, -0.479] degrades |
| **markov** | -0.058 [-0.068, -0.043] degrades | diagonal | -0.004 [-0.008, -0.001] inconclusive | -0.005 [-0.007, -0.002] inconclusive |
| **latent_skill** | -0.037 [-0.045, -0.027] degrades | -0.007 [-0.010, -0.004] inconclusive | diagonal | -0.012 [-0.015, -0.010] degrades |
| **process_trace** | -0.054 [-0.064, -0.040] degrades | +0.005 [+0.003, +0.007] inconclusive (better than the diagonal; the rule is unchanged) | -0.009 [-0.012, -0.006] inconclusive | diagonal |

**False alarms per non-stuck hour at the transferred alarm rule (budget 1.0)**

| fit on \ test on | v1 | markov | latent_skill | process_trace |
|---|---|---|---|---|
| **v1** | 1.28 [0.89, 1.52] | 3.93 [3.59, 4.25] OVER | 4.16 [3.80, 4.48] OVER | 1.68 [1.57, 1.80] OVER |
| **markov** | 0.07 [0.01, 0.11] | 1.17 [1.02, 1.33] OVER | 1.27 [1.11, 1.44] OVER | 1.02 [0.93, 1.12] |
| **latent_skill** | 0.21 [0.17, 0.27] | 1.06 [0.94, 1.18] | 0.97 [0.85, 1.10] | 0.42 [0.37, 0.48] |
| **process_trace** | 0.16 [0.10, 0.24] | 1.60 [1.39, 1.81] OVER | 2.12 [1.79, 2.42] OVER | 1.09 [0.96, 1.22] |

**Detection rate (share of stuck events with an alarm)**

| fit on \ test on | v1 | markov | latent_skill | process_trace |
|---|---|---|---|---|
| **v1** | 0.33 [0.26, 0.41] | 0.22 [0.20, 0.24] | 0.27 [0.25, 0.29] | 0.13 [0.12, 0.14] |
| **markov** | 0.08 [0.06, 0.10] | 0.39 [0.36, 0.42] | 0.54 [0.49, 0.58] | 0.34 [0.31, 0.37] |
| **latent_skill** | 0.23 [0.19, 0.32] | 0.46 [0.43, 0.49] | 0.61 [0.56, 0.65] | 0.32 [0.29, 0.35] |
| **process_trace** | 0.20 [0.17, 0.25] | 0.49 [0.46, 0.52] | 0.63 [0.58, 0.67] | 0.42 [0.39, 0.45] |

**Log loss of the full model, time-since-progress baseline and base rate (test families on the diagonal)**

| Test family | label rate | full | time since progress | base rate | bins | no skill? |
|---|---|---|---|---|---|---|
| v1 | 0.201 [0.178, 0.222] | 0.431 [0.408, 0.453] | 0.502 [0.473, 0.530] | 0.503 [0.473, 0.531] | 7376 | no |
| markov | 0.411 [0.388, 0.436] | 0.645 [0.628, 0.661] | 0.652 [0.638, 0.666] | 0.688 [0.680, 0.698] | 146789 | no |
| latent_skill | 0.339 [0.316, 0.363] | 0.569 [0.550, 0.589] | 0.584 [0.565, 0.603] | 0.662 [0.650, 0.676] | 253886 | no |
| process_trace | 0.381 [0.359, 0.403] | 0.592 [0.578, 0.606] | 0.604 [0.591, 0.617] | 0.681 [0.670, 0.693] | 238770 | no |

Verdicts over the off-diagonal cells: 7 degrade, 0 transfer, 5 inconclusive. Cells where the gain over time-since-progress is not clearly positive (no skill): latent_skill->markov, v1->markov, v1->latent_skill, latent_skill->process_trace, v1->process_trace.

### data-analyst

**H1, gain over time-since-progress (nats per bin)**

| fit on \ test on | markov | latent_skill | process_trace |
|---|---|---|---|
| **markov** | 0.006 [0.005, 0.007] | 0.010 [0.009, 0.012] | 0.009 [0.006, 0.011] |
| **latent_skill** | 0.000 [-0.003, 0.003] | 0.009 [0.006, 0.013] | -0.002 [-0.005, 0.001] |
| **process_trace** | -0.000 [-0.003, 0.002] | -0.002 [-0.005, 0.001] | 0.009 [0.007, 0.011] |

**Degradation: delta H1 against the diagonal (off-diagonal minus diagonal), with the pre-registered verdict**

| fit on \ test on | markov | latent_skill | process_trace |
|---|---|---|---|
| **markov** | diagonal | +0.001 [-0.001, +0.003] transfers | -0.000 [-0.002, +0.001] transfers |
| **latent_skill** | -0.006 [-0.008, -0.004] inconclusive | diagonal | -0.011 [-0.014, -0.009] degrades |
| **process_trace** | -0.007 [-0.009, -0.005] inconclusive | -0.011 [-0.015, -0.008] degrades | diagonal |

**False alarms per non-stuck hour at the transferred alarm rule (budget 1.0)**

| fit on \ test on | markov | latent_skill | process_trace |
|---|---|---|---|
| **markov** | 0.92 [0.80, 1.04] | 1.28 [1.08, 1.50] OVER | 0.85 [0.77, 0.93] |
| **latent_skill** | 0.66 [0.56, 0.76] | 0.97 [0.80, 1.15] | 0.41 [0.38, 0.45] |
| **process_trace** | 1.26 [1.11, 1.43] OVER | 2.15 [1.90, 2.41] OVER | 0.89 [0.79, 1.00] |

**Detection rate (share of stuck events with an alarm)**

| fit on \ test on | markov | latent_skill | process_trace |
|---|---|---|---|
| **markov** | 0.30 [0.28, 0.32] | 0.42 [0.38, 0.47] | 0.32 [0.29, 0.35] |
| **latent_skill** | 0.27 [0.25, 0.30] | 0.42 [0.37, 0.47] | 0.27 [0.26, 0.28] |
| **process_trace** | 0.35 [0.33, 0.37] | 0.48 [0.43, 0.52] | 0.36 [0.34, 0.39] |

**Log loss of the full model, time-since-progress baseline and base rate (test families on the diagonal)**

| Test family | label rate | full | time since progress | base rate | bins | no skill? |
|---|---|---|---|---|---|---|
| markov | 0.354 [0.333, 0.376] | 0.635 [0.621, 0.649] | 0.641 [0.627, 0.654] | 0.668 [0.656, 0.680] | 189447 | no |
| latent_skill | 0.320 [0.293, 0.345] | 0.590 [0.560, 0.621] | 0.600 [0.571, 0.628] | 0.670 [0.644, 0.697] | 217228 | no |
| process_trace | 0.418 [0.400, 0.437] | 0.638 [0.629, 0.648] | 0.648 [0.639, 0.656] | 0.684 [0.677, 0.690] | 221515 | no |

Verdicts over the off-diagonal cells: 2 degrade, 2 transfer, 2 inconclusive. Cells where the gain over time-since-progress is not clearly positive (no skill): latent_skill->markov, process_trace->markov, process_trace->latent_skill, latent_skill->process_trace.

### programmer

**H1, gain over time-since-progress (nats per bin)**

| fit on \ test on | markov | latent_skill | process_trace |
|---|---|---|---|
| **markov** | 0.002 [-0.000, 0.004] | 0.013 [0.011, 0.016] | -0.004 [-0.006, -0.002] |
| **latent_skill** | 0.006 [0.003, 0.008] | 0.013 [0.011, 0.016] | 0.001 [-0.001, 0.003] |
| **process_trace** | 0.006 [0.005, 0.008] | 0.015 [0.013, 0.018] | 0.004 [0.003, 0.005] |

**Degradation: delta H1 against the diagonal (off-diagonal minus diagonal), with the pre-registered verdict**

| fit on \ test on | markov | latent_skill | process_trace |
|---|---|---|---|
| **markov** | diagonal | +0.000 [-0.001, +0.002] transfers | -0.008 [-0.010, -0.006] inconclusive |
| **latent_skill** | +0.004 [+0.002, +0.006] inconclusive (better than the diagonal; the rule is unchanged) | diagonal | -0.003 [-0.004, -0.001] inconclusive |
| **process_trace** | +0.004 [+0.003, +0.006] inconclusive (better than the diagonal; the rule is unchanged) | +0.002 [-0.000, +0.004] transfers | diagonal |

**False alarms per non-stuck hour at the transferred alarm rule (budget 1.0)**

| fit on \ test on | markov | latent_skill | process_trace |
|---|---|---|---|
| **markov** | 1.22 [1.04, 1.39] OVER | 1.32 [1.18, 1.47] OVER | 1.12 [0.96, 1.28] |
| **latent_skill** | 0.86 [0.71, 1.01] | 1.34 [1.12, 1.60] OVER | 0.48 [0.43, 0.53] |
| **process_trace** | 1.21 [1.07, 1.35] OVER | 1.97 [1.71, 2.27] OVER | 1.36 [1.19, 1.53] OVER |

**Detection rate (share of stuck events with an alarm)**

| fit on \ test on | markov | latent_skill | process_trace |
|---|---|---|---|
| **markov** | 0.38 [0.36, 0.40] | 0.57 [0.53, 0.60] | 0.33 [0.32, 0.35] |
| **latent_skill** | 0.25 [0.24, 0.27] | 0.45 [0.41, 0.48] | 0.23 [0.22, 0.25] |
| **process_trace** | 0.43 [0.41, 0.45] | 0.61 [0.58, 0.64] | 0.42 [0.41, 0.44] |

**Log loss of the full model, time-since-progress baseline and base rate (test families on the diagonal)**

| Test family | label rate | full | time since progress | base rate | bins | no skill? |
|---|---|---|---|---|---|---|
| markov | 0.365 [0.346, 0.383] | 0.615 [0.599, 0.631] | 0.617 [0.602, 0.632] | 0.658 [0.648, 0.668] | 160846 | YES |
| latent_skill | 0.443 [0.417, 0.472] | 0.615 [0.602, 0.627] | 0.628 [0.616, 0.640] | 0.749 [0.734, 0.765] | 277273 | no |
| process_trace | 0.386 [0.364, 0.406] | 0.656 [0.643, 0.670] | 0.660 [0.647, 0.674] | 0.680 [0.669, 0.692] | 228860 | no |

Verdicts over the off-diagonal cells: 0 degrade, 2 transfer, 4 inconclusive. Cells where the gain over time-since-progress is not clearly positive (no skill): markov->markov, markov->process_trace, latent_skill->process_trace.

### Leave-one-person-out diagnostics (the public `evaluate_hazard`, benefits processor, replicate 0; v1 = its four personas)

Nested leave-one-person-out with the alarm rule chosen on the training people only, as the shipped evaluation does. Intervals here resample episodes (the function's own), not people.

| Family | people | bins | label rate | log loss full | time since progress | base rate | gain over time since progress | false alarms / h | detection | within budget |
|---|---|---|---|---|---|---|---|---|---|---|
| v1 | 4 | 7376 | 0.2057 | 0.436 | 0.509 | 0.509 | 0.072 [0.064, 0.080] | 1.21 [0.97, 1.49] | 0.33 [0.28, 0.39] | False |
| markov | 16 | 16965 | 0.3511 | 0.498 | 0.522 | 0.656 | 0.024 [0.019, 0.029] | 0.90 [0.70, 1.09] | 0.52 [0.48, 0.56] | True |
| latent_skill | 16 | 61669 | 0.4653 | 0.582 | 0.605 | 0.694 | 0.023 [0.021, 0.025] | 1.00 [0.89, 1.13] | 0.70 [0.69, 0.71] | True |
| process_trace | 16 | 43423 | 0.4933 | 0.567 | 0.598 | 0.696 | 0.031 [0.026, 0.035] | 0.98 [0.84, 1.14] | 0.35 [0.33, 0.37] | True |

## 3. Genome deficit recovery under mismatch (benefits processor)

Present = the deficit cost the person at least 5 s on that case; absent = it never occurred; indeterminate (excluded) otherwise. The method aligns each novice case to the nearest expert of the *fitting* family and attributes seconds to deficit cog families; a deficit is detected when the attribution reaches `X_d` (the 95th percentile of what the same procedure attributes between two experts of the fitting family, at least 1 s). G1 pools over deficits.

### benefits-processor

**G1 precision**

| fit on \ test on | v1 | markov | latent_skill | process_trace |
|---|---|---|---|---|
| **v1** | 92.11% [84.62, 98.70] | 46.93% [40.48, 53.12] | 33.01% [26.22, 40.31] | 55.99% [49.47, 62.36] |
| **markov** | 78.57% [54.55, 95.24] | 67.35% [61.09, 73.26] | 52.94% [45.45, 60.48] | 63.52% [56.27, 70.43] |
| **latent_skill** | 100.00% [100.00, 100.00] | 59.42% [52.46, 65.70] | 48.20% [40.39, 55.69] | 67.57% [61.07, 73.97] |
| **process_trace** | 100.00% [100.00, 100.00] | 57.58% [50.00, 64.76] | 50.70% [43.68, 57.22] | 70.95% [62.27, 78.79] |

**G1 precision: delta against the diagonal with verdict (margin 0.10)**

| fit on \ test on | v1 | markov | latent_skill | process_trace |
|---|---|---|---|---|
| **v1** | diagonal | -0.20 [-0.25, -0.16] degrades | -0.15 [-0.20, -0.11] degrades | -0.15 [-0.20, -0.09] degrades |
| **markov** | -0.14 [-0.32, -0.00] degrades | diagonal | +0.05 [+0.00, +0.10] inconclusive (better than the diagonal; the rule is unchanged) | -0.07 [-0.13, -0.02] inconclusive |
| **latent_skill** | +0.08 [+0.01, +0.15] inconclusive (better than the diagonal; the rule is unchanged) | -0.08 [-0.13, -0.03] inconclusive | diagonal | -0.03 [-0.09, +0.03] transfers |
| **process_trace** | +0.08 [+0.01, +0.15] inconclusive (better than the diagonal; the rule is unchanged) | -0.10 [-0.14, -0.05] inconclusive | +0.03 [-0.03, +0.08] transfers | diagonal |

**G1 recall**

| fit on \ test on | v1 | markov | latent_skill | process_trace |
|---|---|---|---|---|
| **v1** | 94.59% [88.63, 100.00] | 95.45% [92.91, 97.85] | 87.26% [81.76, 92.00] | 89.74% [86.69, 92.70] |
| **markov** | 9.91% [6.37, 12.63] | 62.50% [55.05, 68.82] | 63.06% [54.19, 70.90] | 51.32% [45.93, 56.43] |
| **latent_skill** | 42.34% [32.11, 52.09] | 77.65% [72.51, 82.69] | 68.15% [60.38, 76.26] | 66.23% [61.57, 70.44] |
| **process_trace** | 33.33% [25.61, 42.78] | 64.77% [57.97, 70.97] | 69.43% [62.66, 75.51] | 49.34% [43.16, 55.56] |

**G1 recall: delta against the diagonal with verdict (margin 0.10)**

| fit on \ test on | v1 | markov | latent_skill | process_trace |
|---|---|---|---|---|
| **v1** | diagonal | +0.33 [+0.27, +0.40] inconclusive (better than the diagonal; the rule is unchanged) | +0.19 [+0.12, +0.27] inconclusive (better than the diagonal; the rule is unchanged) | +0.40 [+0.34, +0.47] inconclusive (better than the diagonal; the rule is unchanged) |
| **markov** | -0.85 [-0.93, -0.77] degrades | diagonal | -0.05 [-0.14, +0.03] transfers | +0.02 [-0.05, +0.09] transfers |
| **latent_skill** | -0.52 [-0.65, -0.42] degrades | +0.15 [+0.08, +0.23] inconclusive (better than the diagonal; the rule is unchanged) | diagonal | +0.17 [+0.11, +0.24] inconclusive (better than the diagonal; the rule is unchanged) |
| **process_trace** | -0.61 [-0.70, -0.53] degrades | +0.02 [-0.05, +0.10] transfers | +0.01 [-0.06, +0.09] transfers | diagonal |

**Diagonal cells, per deficit** (bias = recovered minus true price, seconds, among present pairs; false attribution = seconds the method puts on a deficit that never occurred)

| Family | deficit | present pairs | precision | recall | bias (s) |
|---|---|---|---|---|---|
| v1 | skipped_check_cliff | 14 | 100.00% [100.00, 100.00] | 100.00% [100.00, 100.00] | -2.2 [-10.6, 5.5] |
| v1 | repeated_read_result | 14 | 70.00% [40.00, 94.12] | 100.00% [100.00, 100.00] | 13.5 [4.7, 23.0] |
| v1 | search_loop | 18 | 100.00% [100.00, 100.00] | 100.00% [100.00, 100.00] | 0.0 [-0.0, 0.0] |
| v1 | copy_error | 14 | 100.00% [100.00, 100.00] | 71.43% [33.33, 100.00] | -14.0 [-31.8, 1.0] |
| v1 | idle_before_enter | 14 | 100.00% [100.00, 100.00] | 100.00% [100.00, 100.00] | 0.0 [-0.0, 0.0] |
| markov | skipped_check_cliff | 43 | 72.97% [56.25, 87.80] | 62.79% [48.00, 77.28] | -53.9 [-95.5, -7.6] |
| markov | repeated_read_result | 98 | 78.38% [68.67, 87.06] | 59.18% [47.06, 70.52] | 54.0 [29.8, 80.1] |
| markov | search_loop | 58 | 75.86% [63.26, 86.96] | 75.86% [65.45, 85.71] | -8.1 [-70.7, 70.6] |
| markov | copy_error | 19 | 54.55% [31.82, 76.20] | 63.16% [38.46, 86.67] | -162.9 [-198.6, -122.6] |
| markov | idle_before_enter | 46 | 44.44% [28.56, 59.19] | 52.17% [36.36, 67.31] | 373.4 [227.0, 531.5] |
| latent_skill | skipped_check_cliff | 23 | 36.84% [22.50, 52.94] | 60.87% [42.11, 80.00] | 8.7 [-55.2, 76.4] |
| latent_skill | repeated_read_result | 51 | 58.73% [44.26, 72.13] | 72.55% [57.77, 85.42] | 6.3 [-30.8, 39.6] |
| latent_skill | search_loop | 34 | 57.14% [45.00, 69.57] | 82.35% [69.57, 93.55] | -98.9 [-260.9, 43.8] |
| latent_skill | copy_error | 18 | 33.33% [12.49, 55.56] | 44.44% [21.73, 65.01] | -133.7 [-169.7, -104.0] |
| latent_skill | idle_before_enter | 31 | 41.67% [29.16, 54.90] | 64.52% [48.00, 81.49] | 346.4 [185.9, 549.5] |
| process_trace | skipped_check_cliff | 57 | 74.07% [54.55, 91.18] | 35.09% [22.00, 48.35] | 18.8 [-5.2, 46.1] |
| process_trace | repeated_read_result | 111 | 80.56% [70.31, 90.16] | 52.25% [41.67, 64.29] | 48.7 [33.6, 64.7] |
| process_trace | search_loop | 59 | 100.00% [100.00, 100.00] | 71.19% [58.93, 83.34] | -48.1 [-72.5, -24.3] |
| process_trace | copy_error | 15 | 16.00% [4.16, 33.33] | 26.67% [7.14, 52.94] | -88.2 [-115.5, -55.2] |
| process_trace | idle_before_enter | 60 | 56.82% [39.99, 73.34] | 41.67% [28.17, 54.24] | 253.2 [113.7, 426.2] |

| Family (diagonal) | present pairs | absent pairs | indeterminate | false attribution (s per absent pair) | mean gap to nearest expert (s per case) |
|---|---|---|---|---|---|
| v1 | 74 | 86 | 0 | 1.09 [0.23, 2.04] | 229.6 [194.8, 273.4] |
| markov | 264 | 595 | 51 | 55.66 [43.59, 68.93] | 723.3 [581.9, 869.4] |
| latent_skill | 157 | 736 | 27 | 58.61 [43.81, 74.69] | 786.4 [642.3, 945.5] |
| process_trace | 302 | 538 | 30 | 45.67 [28.41, 72.75] | 536.1 [427.6, 668.4] |

Placebo (expert against nearest other expert) and the share of expert cases carrying a material deficit (reference contamination), per training dataset:

| Dataset | contamination | max placebo attribution per deficit (s) | thresholds X_d (s) |
|---|---|---|---|
| markov:0 | 0.2778 | {'skipped_check_cliff': 238.93, 'repeated_read_result': 205.4, 'search_loop': 370.2, 'copy_error': 96.1, 'idle_before_enter': 475.05} | {'skipped_check_cliff': 74.88, 'repeated_read_result': 113.88, 'search_loop': 139.92, 'copy_error': 10.34, 'idle_before_enter': 230.4} |
| markov:1 | 0.1667 | {'skipped_check_cliff': 104.09, 'repeated_read_result': 133.45, 'search_loop': 125.92, 'copy_error': 64.48, 'idle_before_enter': 2425.4} | {'skipped_check_cliff': 69.18, 'repeated_read_result': 76.69, 'search_loop': 74.56, 'copy_error': 1.0, 'idle_before_enter': 544.14} |
| markov:2 | 0.3235 | {'skipped_check_cliff': 45.87, 'repeated_read_result': 107.99, 'search_loop': 119.32, 'copy_error': 0.0, 'idle_before_enter': 142.86} | {'skipped_check_cliff': 7.52, 'repeated_read_result': 81.96, 'search_loop': 110.36, 'copy_error': 1.0, 'idle_before_enter': 137.32} |
| latent_skill:0 | 0.0789 | {'skipped_check_cliff': 107.99, 'repeated_read_result': 99.12, 'search_loop': 958.41, 'copy_error': 72.47, 'idle_before_enter': 788.88} | {'skipped_check_cliff': 76.12, 'repeated_read_result': 78.05, 'search_loop': 1.0, 'copy_error': 5.31, 'idle_before_enter': 329.64} |
| latent_skill:1 | 0.0 | {'skipped_check_cliff': 68.52, 'repeated_read_result': 33.51, 'search_loop': 20.31, 'copy_error': 41.35, 'idle_before_enter': 1272.86} | {'skipped_check_cliff': 19.31, 'repeated_read_result': 31.5, 'search_loop': 1.0, 'copy_error': 1.0, 'idle_before_enter': 281.87} |
| latent_skill:2 | 0.0357 | {'skipped_check_cliff': 120.12, 'repeated_read_result': 70.73, 'search_loop': 0.0, 'copy_error': 38.06, 'idle_before_enter': 183.92} | {'skipped_check_cliff': 98.59, 'repeated_read_result': 53.31, 'search_loop': 1.0, 'copy_error': 1.0, 'idle_before_enter': 174.8} |
| process_trace:0 | 0.2083 | {'skipped_check_cliff': 161.27, 'repeated_read_result': 133.62, 'search_loop': 104.11, 'copy_error': 104.96, 'idle_before_enter': 1195.34} | {'skipped_check_cliff': 123.62, 'repeated_read_result': 58.17, 'search_loop': 1.0, 'copy_error': 52.87, 'idle_before_enter': 217.19} |
| process_trace:1 | 0.1176 | {'skipped_check_cliff': 193.49, 'repeated_read_result': 125.73, 'search_loop': 0.0, 'copy_error': 64.61, 'idle_before_enter': 2993.76} | {'skipped_check_cliff': 103.04, 'repeated_read_result': 101.12, 'search_loop': 1.0, 'copy_error': 32.26, 'idle_before_enter': 246.12} |
| process_trace:2 | 0.5312 | {'skipped_check_cliff': 193.43, 'repeated_read_result': 134.94, 'search_loop': 289.88, 'copy_error': 0.0, 'idle_before_enter': 387.15} | {'skipped_check_cliff': 126.36, 'repeated_read_result': 105.32, 'search_loop': 79.03, 'copy_error': 1.0, 'idle_before_enter': 69.74} |
| v1:0 | 0.0 | {'skipped_check_cliff': 0.0, 'repeated_read_result': 0.0, 'search_loop': 0.0, 'copy_error': 0.0, 'idle_before_enter': 0.0} | {'skipped_check_cliff': 1.0, 'repeated_read_result': 1.0, 'search_loop': 1.0, 'copy_error': 1.0, 'idle_before_enter': 1.0} |

Verdicts over the off-diagonal cells: precision 4 degrade, 2 transfer, 6 inconclusive; recall 3 degrade, 4 transfer, 5 inconclusive.

## 4. Routine finder under mismatch

R1 = cluster precision of the raw finder (true clusters over clusters returned), R2 = recall of detectable planted routines, R3 = precision over proposals after the value gate (shipped config). 'fitted' = the cut height chosen on the fitting family's people; 'shipped' = the fixed 0.35 (no fitting).

### benefits-processor

Tuned cut heights (grid value with the best pooled F1 on the training people): {'markov:0': 0.5, 'markov:1': 0.5, 'markov:2': 0.5, 'latent_skill:0': 0.4, 'latent_skill:1': 0.4, 'latent_skill:2': 0.4, 'process_trace:0': 0.25, 'process_trace:1': 0.2, 'process_trace:2': 0.35, 'v1:0': 0.2}

**R1 cluster precision (fitted)**

| fit on \ test on | v1 | markov | latent_skill | process_trace |
|---|---|---|---|---|
| **v1** | 93.33% [83.33, 100.00] | 100.00% [100.00, 100.00] | 99.63% [98.76, 100.00] | 63.48% [59.89, 67.41] |
| **markov** | 4.25% [2.59, 11.11] | 71.06% [66.93, 75.31] | 47.69% [41.89, 53.53] | 23.85% [21.49, 26.18] |
| **latent_skill** | 12.09% [6.73, 42.86] | 96.00% [93.30, 98.00] | 88.58% [85.34, 91.55] | 38.44% [35.08, 41.43] |
| **process_trace** | 43.62% [25.56, 81.03] | 97.69% [95.24, 100.00] | 93.58% [90.86, 96.17] | 49.68% [46.64, 53.10] |

**R2 recall (fitted)**

| fit on \ test on | v1 | markov | latent_skill | process_trace |
|---|---|---|---|---|
| **v1** | 100.00% [100.00, 100.00] | 16.42% [11.83, 21.15] | 42.99% [36.04, 50.00] | 65.45% [59.31, 71.90] |
| **markov** | 100.00% [100.00, 100.00] | 82.48% [77.08, 87.50] | 84.39% [79.03, 89.57] | 96.68% [94.80, 98.37] |
| **latent_skill** | 100.00% [100.00, 100.00] | 56.57% [49.63, 64.21] | 72.61% [65.04, 79.60] | 95.02% [91.27, 97.99] |
| **process_trace** | 100.00% [100.00, 100.00] | 31.02% [25.27, 37.08] | 53.50% [45.70, 61.29] | 78.74% [73.02, 84.41] |

**Delta against the diagonal with verdict (margin 0.10), fitted**

r1_precision:

| fit on \ test on | v1 | markov | latent_skill | process_trace |
|---|---|---|---|---|
| **v1** | diagonal | +0.29 [+0.25, +0.33] inconclusive (better than the diagonal; the rule is unchanged) | +0.11 [+0.08, +0.14] inconclusive (better than the diagonal; the rule is unchanged) | +0.14 [+0.11, +0.16] inconclusive (better than the diagonal; the rule is unchanged) |
| **markov** | -0.89 [-0.97, -0.78] degrades | diagonal | -0.41 [-0.45, -0.37] degrades | -0.26 [-0.29, -0.23] degrades |
| **latent_skill** | -0.81 [-0.93, -0.56] degrades | +0.25 [+0.20, +0.29] inconclusive (better than the diagonal; the rule is unchanged) | diagonal | -0.11 [-0.14, -0.09] degrades |
| **process_trace** | -0.50 [-0.74, -0.13] degrades | +0.27 [+0.22, +0.31] inconclusive (better than the diagonal; the rule is unchanged) | +0.05 [+0.03, +0.07] inconclusive (better than the diagonal; the rule is unchanged) | diagonal |

r2_recall:

| fit on \ test on | v1 | markov | latent_skill | process_trace |
|---|---|---|---|---|
| **v1** | diagonal | -0.66 [-0.71, -0.61] degrades | -0.30 [-0.35, -0.24] degrades | -0.13 [-0.18, -0.09] degrades |
| **markov** | +0.00 [+0.00, +0.00] transfers | diagonal | +0.12 [+0.07, +0.17] inconclusive (better than the diagonal; the rule is unchanged) | +0.18 [+0.13, +0.24] inconclusive (better than the diagonal; the rule is unchanged) |
| **latent_skill** | +0.00 [+0.00, +0.00] transfers | -0.26 [-0.31, -0.20] degrades | diagonal | +0.16 [+0.12, +0.21] inconclusive (better than the diagonal; the rule is unchanged) |
| **process_trace** | +0.00 [+0.00, +0.00] transfers | -0.51 [-0.58, -0.45] degrades | -0.19 [-0.24, -0.14] degrades | diagonal |

**R1 cluster precision (shipped)**

| fit on \ test on | v1 | markov | latent_skill | process_trace |
|---|---|---|---|---|
| **v1** | 21.82% [12.00, 61.90] | 96.60% [94.05, 98.66] | 93.21% [90.74, 95.58] | 44.30% [41.02, 47.42] |
| **markov** | 21.82% [12.00, 61.90] | 96.60% [94.05, 98.66] | 93.21% [90.74, 95.58] | 44.30% [41.02, 47.42] |
| **latent_skill** | 21.82% [12.00, 61.90] | 96.60% [94.05, 98.66] | 93.21% [90.74, 95.58] | 44.30% [41.02, 47.42] |
| **process_trace** | 21.82% [12.00, 61.90] | 96.60% [94.05, 98.66] | 93.21% [90.74, 95.58] | 44.30% [41.02, 47.42] |

**R2 recall (shipped)**

| fit on \ test on | v1 | markov | latent_skill | process_trace |
|---|---|---|---|---|
| **v1** | 100.00% [100.00, 100.00] | 44.53% [38.30, 50.95] | 66.24% [58.31, 73.90] | 92.36% [88.16, 95.92] |
| **markov** | 100.00% [100.00, 100.00] | 44.53% [38.30, 50.95] | 66.24% [58.31, 73.90] | 92.36% [88.16, 95.92] |
| **latent_skill** | 100.00% [100.00, 100.00] | 44.53% [38.30, 50.95] | 66.24% [58.31, 73.90] | 92.36% [88.16, 95.92] |
| **process_trace** | 100.00% [100.00, 100.00] | 44.53% [38.30, 50.95] | 66.24% [58.31, 73.90] | 92.36% [88.16, 95.92] |

**R3 proposal precision after the value gate (shipped config)**

| fit on \ test on | v1 | markov | latent_skill | process_trace |
|---|---|---|---|---|
| **v1** | 100.00% [100.00, 100.00] (1.5 per person) | 100.00% [100.00, 100.00] (0.3 per person) | 100.00% [100.00, 100.00] (0.8 per person) | 74.26% [68.59, 80.09] (1.7 per person) |
| **markov** | 100.00% [100.00, 100.00] (1.5 per person) | 100.00% [100.00, 100.00] (0.3 per person) | 100.00% [100.00, 100.00] (0.8 per person) | 74.26% [68.59, 80.09] (1.7 per person) |
| **latent_skill** | 100.00% [100.00, 100.00] (1.5 per person) | 100.00% [100.00, 100.00] (0.3 per person) | 100.00% [100.00, 100.00] (0.8 per person) | 74.26% [68.59, 80.09] (1.7 per person) |
| **process_trace** | 100.00% [100.00, 100.00] (1.5 per person) | 100.00% [100.00, 100.00] (0.3 per person) | 100.00% [100.00, 100.00] (0.8 per person) | 74.26% [68.59, 80.09] (1.7 per person) |

Verdicts over the fitted off-diagonal cells: R1 6 degrade, 0 transfer, 6 inconclusive; R2 6 degrade, 3 transfer, 3 inconclusive.

### data-analyst

Tuned cut heights (grid value with the best pooled F1 on the training people): {'markov:0': 0.5, 'markov:1': 0.4, 'markov:2': 0.35, 'latent_skill:0': 0.3, 'latent_skill:1': 0.35, 'latent_skill:2': 0.4, 'process_trace:0': 0.35, 'process_trace:1': 0.4, 'process_trace:2': 0.35}

**R1 cluster precision (fitted)**

| fit on \ test on | markov | latent_skill | process_trace |
|---|---|---|---|
| **markov** | 69.54% [63.95, 76.19] | 75.00% [68.74, 81.32] | 87.91% [84.25, 91.22] |
| **latent_skill** | 95.99% [93.44, 98.17] | 96.95% [95.30, 98.32] | 95.17% [93.44, 96.76] |
| **process_trace** | 92.68% [89.60, 95.62] | 97.24% [96.18, 98.24] | 96.08% [94.63, 97.24] |

**R2 recall (fitted)**

| fit on \ test on | markov | latent_skill | process_trace |
|---|---|---|---|
| **markov** | 70.59% [62.82, 78.01] | 95.90% [92.88, 98.33] | 95.68% [93.08, 98.06] |
| **latent_skill** | 55.88% [48.09, 63.97] | 90.78% [87.07, 94.34] | 85.38% [80.45, 90.46] |
| **process_trace** | 60.78% [52.81, 68.95] | 92.83% [89.38, 96.04] | 89.37% [85.08, 93.43] |

**Delta against the diagonal with verdict (margin 0.10), fitted**

r1_precision:

| fit on \ test on | markov | latent_skill | process_trace |
|---|---|---|---|
| **markov** | diagonal | -0.22 [-0.28, -0.16] degrades | -0.08 [-0.12, -0.05] inconclusive |
| **latent_skill** | +0.26 [+0.20, +0.32] inconclusive (better than the diagonal; the rule is unchanged) | diagonal | -0.01 [-0.02, +0.01] transfers |
| **process_trace** | +0.23 [+0.17, +0.28] inconclusive (better than the diagonal; the rule is unchanged) | +0.00 [-0.01, +0.02] transfers | diagonal |

r2_recall:

| fit on \ test on | markov | latent_skill | process_trace |
|---|---|---|---|
| **markov** | diagonal | +0.05 [+0.02, +0.08] inconclusive (better than the diagonal; the rule is unchanged) | +0.06 [+0.03, +0.10] inconclusive (better than the diagonal; the rule is unchanged) |
| **latent_skill** | -0.15 [-0.21, -0.09] degrades | diagonal | -0.04 [-0.06, -0.02] inconclusive |
| **process_trace** | -0.10 [-0.14, -0.06] inconclusive | +0.02 [+0.00, +0.04] transfers | diagonal |

**R1 cluster precision (shipped)**

| fit on \ test on | markov | latent_skill | process_trace |
|---|---|---|---|
| **markov** | 94.88% [92.29, 97.15] | 97.40% [96.35, 98.37] | 97.62% [96.49, 98.51] |
| **latent_skill** | 94.88% [92.29, 97.15] | 97.40% [96.35, 98.37] | 97.62% [96.49, 98.51] |
| **process_trace** | 94.88% [92.29, 97.15] | 97.40% [96.35, 98.37] | 97.62% [96.49, 98.51] |

**R2 recall (shipped)**

| fit on \ test on | markov | latent_skill | process_trace |
|---|---|---|---|
| **markov** | 59.80% [51.96, 67.44] | 91.81% [88.09, 95.26] | 89.37% [85.08, 93.43] |
| **latent_skill** | 59.80% [51.96, 67.44] | 91.81% [88.09, 95.26] | 89.37% [85.08, 93.43] |
| **process_trace** | 59.80% [51.96, 67.44] | 91.81% [88.09, 95.26] | 89.37% [85.08, 93.43] |

**R3 proposal precision after the value gate (shipped config)**

| fit on \ test on | markov | latent_skill | process_trace |
|---|---|---|---|
| **markov** | 100.00% [100.00, 100.00] (0.5 per person) | 100.00% [100.00, 100.00] (1.9 per person) | 100.00% [100.00, 100.00] (1.8 per person) |
| **latent_skill** | 100.00% [100.00, 100.00] (0.5 per person) | 100.00% [100.00, 100.00] (1.9 per person) | 100.00% [100.00, 100.00] (1.8 per person) |
| **process_trace** | 100.00% [100.00, 100.00] (0.5 per person) | 100.00% [100.00, 100.00] (1.9 per person) | 100.00% [100.00, 100.00] (1.8 per person) |

Verdicts over the fitted off-diagonal cells: R1 1 degrade, 2 transfer, 3 inconclusive; R2 1 degrade, 1 transfer, 4 inconclusive.

### programmer

Tuned cut heights (grid value with the best pooled F1 on the training people): {'markov:0': 0.5, 'markov:1': 0.4, 'markov:2': 0.35, 'latent_skill:0': 0.35, 'latent_skill:1': 0.4, 'latent_skill:2': 0.4, 'process_trace:0': 0.4, 'process_trace:1': 0.3, 'process_trace:2': 0.2}

**R1 cluster precision (fitted)**

| fit on \ test on | markov | latent_skill | process_trace |
|---|---|---|---|
| **markov** | 78.83% [72.41, 84.74] | 75.09% [69.06, 82.10] | 57.47% [51.51, 63.97] |
| **latent_skill** | 95.80% [93.92, 97.58] | 95.68% [93.85, 97.36] | 77.93% [73.95, 82.05] |
| **process_trace** | 96.87% [94.75, 98.58] | 95.32% [93.38, 97.16] | 88.65% [85.21, 91.86] |

**R2 recall (fitted)**

| fit on \ test on | markov | latent_skill | process_trace |
|---|---|---|---|
| **markov** | 76.38% [70.19, 82.76] | 90.91% [86.69, 94.97] | 92.13% [87.22, 96.36] |
| **latent_skill** | 76.05% [69.59, 82.17] | 84.85% [79.04, 90.41] | 92.46% [88.50, 95.96] |
| **process_trace** | 62.14% [54.45, 70.14] | 77.44% [71.01, 83.27] | 78.69% [72.11, 85.19] |

**Delta against the diagonal with verdict (margin 0.10), fitted**

r1_precision:

| fit on \ test on | markov | latent_skill | process_trace |
|---|---|---|---|
| **markov** | diagonal | -0.21 [-0.26, -0.14] degrades | -0.31 [-0.35, -0.27] degrades |
| **latent_skill** | +0.17 [+0.11, +0.23] inconclusive (better than the diagonal; the rule is unchanged) | diagonal | -0.11 [-0.16, -0.06] degrades |
| **process_trace** | +0.18 [+0.13, +0.23] inconclusive (better than the diagonal; the rule is unchanged) | -0.00 [-0.02, +0.01] transfers | diagonal |

r2_recall:

| fit on \ test on | markov | latent_skill | process_trace |
|---|---|---|---|
| **markov** | diagonal | +0.06 [+0.02, +0.10] inconclusive (better than the diagonal; the rule is unchanged) | +0.13 [+0.09, +0.18] inconclusive (better than the diagonal; the rule is unchanged) |
| **latent_skill** | -0.00 [-0.05, +0.04] transfers | diagonal | +0.14 [+0.09, +0.19] inconclusive (better than the diagonal; the rule is unchanged) |
| **process_trace** | -0.14 [-0.19, -0.10] degrades | -0.07 [-0.12, -0.03] inconclusive | diagonal |

**R1 cluster precision (shipped)**

| fit on \ test on | markov | latent_skill | process_trace |
|---|---|---|---|
| **markov** | 97.05% [95.61, 98.45] | 96.63% [94.97, 98.06] | 87.79% [85.14, 90.38] |
| **latent_skill** | 97.05% [95.61, 98.45] | 96.63% [94.97, 98.06] | 87.79% [85.14, 90.38] |
| **process_trace** | 97.05% [95.61, 98.45] | 96.63% [94.97, 98.06] | 87.79% [85.14, 90.38] |

**R2 recall (shipped)**

| fit on \ test on | markov | latent_skill | process_trace |
|---|---|---|---|
| **markov** | 70.87% [63.69, 77.74] | 83.16% [76.82, 89.35] | 89.51% [84.44, 94.10] |
| **latent_skill** | 70.87% [63.69, 77.74] | 83.16% [76.82, 89.35] | 89.51% [84.44, 94.10] |
| **process_trace** | 70.87% [63.69, 77.74] | 83.16% [76.82, 89.35] | 89.51% [84.44, 94.10] |

**R3 proposal precision after the value gate (shipped config)**

| fit on \ test on | markov | latent_skill | process_trace |
|---|---|---|---|
| **markov** | 100.00% [100.00, 100.00] (1.0 per person) | 100.00% [100.00, 100.00] (1.7 per person) | 100.00% [100.00, 100.00] (2.1 per person) |
| **latent_skill** | 100.00% [100.00, 100.00] (1.0 per person) | 100.00% [100.00, 100.00] (1.7 per person) | 100.00% [100.00, 100.00] (2.1 per person) |
| **process_trace** | 100.00% [100.00, 100.00] (1.0 per person) | 100.00% [100.00, 100.00] (1.7 per person) | 100.00% [100.00, 100.00] (2.1 per person) |

Verdicts over the fitted off-diagonal cells: R1 3 degrade, 1 transfer, 2 inconclusive; R2 1 degrade, 1 transfer, 4 inconclusive.

## 5. The five pre-registered expectations next to what was found

**1. The hazard's gain over time-since-progress is smaller on every v2 family than on v1, and stays positive on most v2 families.**
  Leave-one-person-out (public function): v1 gain 0.072 [0.064, 0.080]; markov 0.024 [0.019, 0.029]; latent_skill 0.023 [0.021, 0.025]; process_trace 0.031 [0.026, 0.035].
  Found: v1 diagonal H1 0.071 [0.055, 0.083]; v2 diagonals markov 0.008 [0.004, 0.011]; latent_skill 0.015 [0.012, 0.018]; process_trace 0.012 [0.010, 0.015]. Smaller than v1 on 3 of 3 families (markov, latent_skill, process_trace); clearly positive (interval above 0) on 3 of 3 (markov, latent_skill, process_trace).

**2. Cross-family hazard gains are smaller than the diagonal in most cells, and the transferred alarm rule overshoots the false-alarm budget in more cells than the diagonal does.**
  benefits-processor: delta H1 below zero in 11 of 12 off-diagonal cells; false-alarm interval entirely above the 1.0 budget in 6 of 12 off-diagonal cells versus 1 of 4 diagonal cells.
  data-analyst: delta H1 below zero in 5 of 6 off-diagonal cells; false-alarm interval entirely above the 1.0 budget in 3 of 6 off-diagonal cells versus 0 of 3 diagonal cells.
  programmer: delta H1 below zero in 2 of 6 off-diagonal cells; false-alarm interval entirely above the 1.0 budget in 3 of 6 off-diagonal cells versus 3 of 3 diagonal cells.

**3. Genome recall for the named deficits falls well below v1's 95 percent (guess 0.4 to 0.8), and precision falls because legitimate verification re-reads look like repeated reads.**
  v1 diagonal: precision 92.11% [84.62, 98.70], recall 94.59% [88.63, 100.00], false attribution 1.09 [0.23, 2.04] s per absent pair.
  markov diagonal: precision 67.35% [61.09, 73.26], recall 62.50% [55.05, 68.82], false attribution 55.66 [43.59, 68.93] s per absent pair.
  latent_skill diagonal: precision 48.20% [40.39, 55.69], recall 68.15% [60.38, 76.26], false attribution 58.61 [43.81, 74.69] s per absent pair.
  process_trace diagonal: precision 70.95% [62.27, 78.79], recall 49.34% [43.16, 55.56], false attribution 45.67 [28.41, 72.75] s per absent pair.

**4. Routine finder cluster precision stays low (v1: 22 percent) and recall falls below v1's 100 percent (drift, interleaving, split episodes).**
  v1 (shipped config, diagonal): R1 21.82% [12.00, 61.90], R2 100.00% [100.00, 100.00], R3 100.00% [100.00, 100.00].
  markov (shipped config, diagonal): R1 96.60% [94.05, 98.66], R2 44.53% [38.30, 50.95], R3 100.00% [100.00, 100.00].
  latent_skill (shipped config, diagonal): R1 93.21% [90.74, 95.58], R2 66.24% [58.31, 73.90], R3 100.00% [100.00, 100.00].
  process_trace (shipped config, diagonal): R1 44.30% [41.02, 47.42], R2 92.36% [88.16, 95.92], R3 74.26% [68.59, 80.09].

**5. The largest degradations involve process_trace as either side.**
  Among v2-to-v2 off-diagonal verdicts: 10 of 44 involving process_trace degrade, 5 of 22 between markov and latent_skill degrade.

## 6. Deviations from the pre-registered plan

* Hazard leave-one-person-out diagnostics (the public `evaluate_hazard`) were run for the benefits role only, on the first 16 people of replicate 0 of each family and on v1's four personas, because the nested leave-one-out costs people squared fits per variant; the plan said each family and role. The matrix itself (train on replicate k, test on replicate k + 1) covers every role.
* The genome uses the first 2 cases per person (as planned) and runs for the benefits role only (as planned: the named-deficit labels are benefits-specific).
* Routine proposals after the value gate (R3) are scored at the shipped finder config only; the finder cut height is fitted for R1 and R2.
* v1 as the training family has a single fit; it is tested on every replicate of each v2 family. v1 as the test family has four personas (hazard, routines) or 16 novices and 8 experts (genome); its diagonal is leave-one-persona-out (hazard, routines) or the apprentices' own expert-novice split (genome), because no independent v1 draw exists.
* Interpretation rule additions: when a delta interval lies entirely on the beneficial side but outside the margin, the pre-registered rule says inconclusive; the tables add '(better than the diagonal)' beside it for readability without changing the verdict.
* Fast mode (`evaluate_realism(fast=True)`) uses K = 2 replicates of 14 people (the plan said one replicate, which cannot give an independent test replicate), benefits role only, no v1, serial by default; it is a smoke-level section with the same metrics, not the matrix.
* The first full run was stopped after about 35 minutes (it had computed no analytic) so that the matrix could be rerun with a dataset cache and blocks written to disk as they finish, as the lead asked; generators and analyses were unchanged. The rerun saved every block and then stopped at the final assembly step because of a bug of mine (an accidentally deleted function); the report was assembled with `--resume` from the saved blocks and cached datasets.
* The thin role packs (data analyst, programmer) were extended by another track after the generators were frozen; v2 emits the original seven pack cogs per thin role, so it does not exercise the new cogs.
* The `markov` family draws hesitation pauses only through freezes and quiet stalls, so its pause-tail check (M3) is outside the cited range in 3 of the 5 datasets where it can be measured; the family was not changed after the freeze.
* No generator parameter, range or code was changed after PLAN.md was frozen (the report prints the two hashes and flags a mismatch).

## 7. Limitations and honesty

* **realism-synthetic** (high): Every number here comes from generators we wrote. The v2 families have marginals inside cited ranges, but nothing shows they match real people; the live study (n = 4) and an optional labelled pilot are the only evidence about real people.
* **realism-shared-parts** (medium): The three v2 families share the person hierarchy, the interruption process, the event emitter and noise model, the role vocabulary and the task grammar's valid paths. A family with less shared code would be a stronger test.
* **realism-label-circularity** (medium): The hazard label is a point process driven by hidden stuck episodes, not an emission table, but both behaviour and label come from the same hidden state: the circularity is reduced, not removed.
* **realism-citations** (medium): Published ranges were read from search-result summaries; primary papers were not opened. Hick-Hyman slope, circadian amplitude and warm-up are unverified wide assumptions.
* **realism-calibration** (low): Deficit prevalence and stuck-episode rates were calibrated once to structural plausibility targets (S1 to S6) before any analytic was run; the families still differ a lot in prevalence.

### Citation status of the constants the generators use

| Constant | Status | Range | Source |
|---|---|---|---|
| klm_keystroke_s | secondary | 0.12 to 1.2 | Card, Moran & Newell (1980) CACM 23(7) and the 1983 book; tiers and the 0.12 to 1.2 s range as given in Kieras's KLM tutorial |
| klm_pointing_s | secondary | 0.4 to 1.8 | Card, Moran & Newell (1980/1983); 1.1 s is the standard value |
| klm_homing_s | secondary | 0.3 to 0.6 | Card, Moran & Newell (1980/1983); 0.4 s is the standard value |
| klm_mental_s | secondary | 0.9 to 2 | Card, Moran & Newell (1980/1983); 1.35 s is the standard value |
| fitts_mouse_slope_s_per_bit | secondary | 0.08 to 0.2 | Card, English & Burr (1978) mouse fit MT = 1.03 + 0.096 ID, as discussed in MacKenzie's pages (yorku.ca/mack/ijhcs2004.html) |
| fitts_mouse_throughput_bps | secondary | 2.5 to 6 | MacKenzie and colleagues (summarised on yorku.ca/mack); ISO throughput cluster at 4 to 5 bits/s |
| hick_hyman_slope_s_per_bit | assumption | 0.05 to 0.3 | Hick (1952); Hyman (1953); HCI review Seow (2005) Human-Computer Interaction 20(3) |
| power_law_exponent | secondary | 0.1 to 1 | Newell & Rosenbloom (1981) in Anderson (ed.) Cognitive Skills and Their Acquisition; Heathcote, Brown & Mewhort (2000) Psychonomic Bulletin & Review 7(2), who argue individual curves are exponential and the power law is an averaging artefact; R. B. Anderson (2001) simulation of the artefact |
| pause_lognormal_mixture | secondary | 5 to 400 | Almond, Deane, Quinlan, Wagner & Sydorenko (2012) ETS RR-12-23 'A preliminary analysis of keystroke log data from a timed writing task'; Guo et al. (2018) J. Educational Measurement |
| dwell_weibull_negative_aging | secondary | 0.3 to 1 | Liu, White & Dumais (2010) SIGIR, 'Understanding web browsing behaviors through Weibull analysis of dwell time' |
| burstiness_cv | secondary | 1.1 to 20 | Barabasi (2005) Nature 435:207 (heavy tails); Stouffer, Malmgren & Amaral (2005) arXiv physics/0510216, who argue a lognormal fits better than a power law |
| interruptions_per_hour | secondary | 0.5 to 6 | Gonzalez & Mark (2004) CHI 'Constant, constant, multi-tasking craziness' (about 11 minutes per working sphere, via a magazine summary); Mark, Gonzalez & Harris (2005) CHI |
| interruption_recovery_min | secondary | 0.25 to 30 | Mark, Gonzalez & Harris (2005); Altmann & Trafton (2002) Cognitive Science 26(1) for resumption lag growing with interruption length and demand; Mark, Gudith & Klocke (2008) CHI: people work faster after interruptions at a cost in stress |
| fatigue_slowdown_per_hour | qualitative | 0 to 0.15 | Mackworth (1948) vigilance decrement (qualitative: detection falls over the first 30 minutes then more slowly) |
| circadian_amplitude | assumption | 0 to 0.1 | none verified in this session (circadian and post-lunch dip literature was not found) |
| slip_rate_per_step | secondary | 0.0004 to 0.065 | a systematic review of clinical data entry reports single-entry error rates of 0.04 to 6.5 percent depending on field complexity (seen as a snippet only); vendor blogs quote 1 to 4 percent of fields and are not relied on |
| typing_population | qualitative | n/a | Dhakal, Feit, Kristensson & Oulasvirta (2018) CHI, 168,000 volunteers, 136 million keystrokes: eight typist clusters; faster typists make fewer errors |
| practice_forgetting | assumption | 0 to 0.3 | none verified |

`secondary` means the number was read from a search summary or a page that quotes the paper; the paper itself was not opened. `assumption` entries are not citations.

See `evals/realism/INTERPRETATION.md` for the hand-written reading of this matrix (written after the run; not part of the pre-registration) and `evals/realism/DIAGNOSIS.md` for why v1 was easy.
