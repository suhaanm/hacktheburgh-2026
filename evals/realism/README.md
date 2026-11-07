# Realism track (REALISM): files and commands

All data here are **synthetic, realism-calibrated**. Nothing in this folder claims the generated data are human data.

| File | What |
|---|---|
| `DIAGNOSIS.md` | why the v1 data only show planted structure, with file and line references, measurements and citations (status of each) |
| `measure_v1.py` | the read-only measurements behind the diagnosis (`uv run --package understudy-engine python evals/realism/measure_v1.py`) |
| `PLAN.md`, `PLAN.md.tmpl`, `freeze_plan.py` | the pre-registration (metrics, generator ranges with SHA-256, interpretation rules, expectations), frozen before any analytic ran on v2 data; `freeze_plan.py` renders the plan from the live parameter table |
| `REPORT.md` | generated: marginal checks, the three analytics on v1 and each v2 family, the generator-mismatch matrix, the five expectations next to what was found, deviations, limitations |
| `INTERPRETATION.md` | written by hand after reading the matrix (plain English: what it shows, what it cannot show) |
| `../../data/eval/realism.json` | machine-readable section (the eval harness can read it); `realism_lopo.json` holds the leave-one-person-out diagnostics |

Code: `services/engine/understudy_engine/personas_v2/` (generators: `cohort.py`, `workweeks.py`, `families.py`, `ctx.py`, `emit.py`, `people.py`, `roles.py`, `core.py`, `params.py`, `cited.py`; evaluation: `evaluate.py`, `eval_hazard.py`, `eval_genome.py`, `eval_routines.py`, `evalkit.py`, `marginals.py`, `report.py`, `v1data.py`). Tests: `services/engine/tests/personas_v2/`.

Commands (heavy ones go through `scripts/heavy.sh`):

```
# generators and tests (light)
UNDERSTUDY_MOCK=1 uv run --package understudy-engine pytest services/engine/tests/personas_v2 -q

# the full matrix: writes evals/realism/REPORT.md and data/eval/realism.json (fork is fast from a clean CLI parent; the default start method is spawn, which is safe everywhere)
UNDERSTUDY_REALISM_FORK=1 UNDERSTUDY_MOCK=1 scripts/heavy.sh uv run --package understudy-engine python -m understudy_engine.personas_v2.evaluate --full --workers 3

# leave-one-person-out diagnostics, then re-render the report with them
UNDERSTUDY_MOCK=1 scripts/heavy.sh uv run --package understudy-engine python -m understudy_engine.personas_v2.evaluate --lopo --workers 1
UNDERSTUDY_MOCK=1 uv run --package understudy-engine python -m understudy_engine.personas_v2.evaluate --render

# the eval-harness section (small n, benefits role only, no v1)
python -c "from understudy_engine.personas_v2.evaluate import evaluate_realism; evaluate_realism(fast=True)"
```

Using the generators from another track:

```python
from understudy_engine.personas_v2 import generate_cohort, generate_workweeks
c = generate_cohort("process_trace", "benefits-processor", n_people=40, cases_per_person=8, seed=7)
c.episodes()          # core.Episode list through the role pack's cog mapping
c.truth["traces"]     # v1 apprentices truth shape, with material / price_s per deficit occurrence
w = generate_workweeks("markov", "programmer", n_people=40, n_days=14, seed=7)
```

Families: `markov`, `latent_skill`, `process_trace`. Roles: `benefits-processor`, `data-analyst`, `programmer`. A cohort is a pure function of its arguments; the generators mix the family index into every internal stream.
