"""Render PLAN.md from PLAN.md.tmpl with the live parameter table and hash. Usage: freeze_plan.py DRAFT|FROZEN"""
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root / "services" / "engine"))
from understudy_engine.personas_v2 import params, version  # noqa: E402

status = sys.argv[1] if len(sys.argv) > 1 else "DRAFT"
t = (root / "evals/realism/PLAN.md.tmpl").read_text()
t = t.replace("__PARAM_TABLE__", params.render_table()).replace("__PARAMS_SHA__", params.params_sha256()).replace("__STATUS__", status).replace("__CODE_SHA__", version.generator_sha256())
(root / "evals/realism/PLAN.md").write_text(t)
print(status, params.params_sha256(), version.generator_sha256(), len(params.PARAMS), "rows")
