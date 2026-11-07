"""Print a short table of one finished block (hazard, routines or genome) from data/eval/realism_blocks. Usage: show_block.py hazard benefits-processor"""
import json
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[2]
name, role = sys.argv[1], sys.argv[2]
d = json.loads((root / "data" / "eval" / "realism_blocks" / f"{name}_{role}.json").read_text())["result"]["cells"]
ALL = ("v1", "markov", "latent_skill", "process_trace")


def fe(e, nd=3, pct=False):
    if not e or e.get("est") is None:
        return "n/a"
    k = 100 if pct else 1
    ci = e["ci"]
    return f"{e['est'] * k:.{nd}f}" + (f" [{ci[0] * k:.{nd}f},{ci[1] * k:.{nd}f}]" if ci[0] is not None else "")


def table(title, getter, prefix=""):
    xs = [a for a in ALL if any(k.startswith(f"{prefix}{a}->") for k in d)]
    ys = [a for a in ALL if any(k.endswith(f"->{a}") for k in d)]
    print(f"\n{title}\nfit\\test | " + " | ".join(ys))
    for x in xs:
        print(x + " | " + " | ".join(getter(d.get(f"{prefix}{x}->{y}")) if d.get(f"{prefix}{x}->{y}") else "n/a" for y in ys))


if name == "hazard":
    table("H1 gain over time-since-progress (nats/bin)", lambda c: fe(c["metrics"]["h1"]))
    table("verdict vs diagonal (H1)", lambda c: (c.get("delta_vs_diagonal") or {}).get("h1", {}).get("verdict", "diag"))
    table("false alarms per non-stuck hour (budget 1.0)", lambda c: fe(c["metrics"]["fa_per_h"], 2) + (" OVER" if c["fa_over_budget"] else ""))
    table("detection", lambda c: fe(c["metrics"]["detection"], 2))
elif name == "genome":
    table("G1 precision %", lambda c: fe(c["metrics"]["precision"], 0, True))
    table("G1 recall %", lambda c: fe(c["metrics"]["recall"], 0, True))
    table("verdict precision / recall", lambda c: "/".join((c.get("delta_vs_diagonal") or {}).get(m, {}).get("verdict", "diag") for m in ("precision", "recall")))
else:
    for mode in ("fitted", "shipped"):
        table(f"R1 cluster precision % ({mode})", lambda c: fe(c["metrics"]["r1_precision"], 0, True), f"{mode}:")
        table(f"R2 recall % ({mode})", lambda c: fe(c["metrics"]["r2_recall"], 0, True), f"{mode}:")
    table("R3 proposal precision % (shipped)", lambda c: fe(c["metrics"]["r3_proposal_precision"], 0, True), "shipped:")
