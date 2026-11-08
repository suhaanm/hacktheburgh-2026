"""CPU time per engine endpoint, measured on a COPY of the live data (never the live engine, never port 7700).

    python services/engine/tests/perf/measure.py [--label before] [--out report.json] [--profile] [--reps 3] [--only growth,briefing]
                                                  [--data <dir> --home <dir>] [--keep <tmpdir>]

For every endpoint the dashboard calls on first load and on each screen it makes one cold call and ``reps`` warm calls in-process with
TestClient (warm=False, so the background warm-up does not run) and records the wall time and ``time.process_time`` (CPU seconds of the
whole process, independent of how loaded the machine is). With --profile every endpoint whose warm CPU time is over --threshold (default
150 ms) is profiled with cProfile inside the handler thread and the top frames are printed.
"""
from __future__ import annotations

import argparse
import cProfile
import io
import json
import os
import pstats
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
from _env import prepare  # noqa: E402

PERSON = "p_learn01"

# (name, method, path, kind)   kind: "" plain, "admin" with the admin role headers and the per-boot token
ENDPOINTS: list[tuple[str, str]] = [
    ("health", "/health"),
    ("kill", "/kill"),
    ("identity", "/identity"),
    ("profile", "/profile"),
    ("queue", "/queue?status=pending"),
    ("coach/state", f"/coach/state?person={PERSON}"),
    ("attention/next", f"/attention/next?person={PERSON}&peek=1"),
    ("attention/settings", f"/attention/settings?person={PERSON}"),
    ("attention/digest", f"/attention/digest?person={PERSON}&kind=daily"),
    ("memory", "/memory"),
    ("memory/proposals", "/memory/proposals"),
    ("packs", "/packs"),
    ("routines", "/routines"),
    ("briefing", f"/briefing?person={PERSON}"),
    ("insights/worker", f"/insights/worker?person={PERSON}"),
    ("hitlist", "/hitlist"),
    ("growth", f"/growth?person={PERSON}"),
    ("presence", f"/presence?person={PERSON}"),
    ("graph/work", f"/graph/work?person={PERSON}"),
    ("calendar/week", f"/calendar/week?person={PERSON}"),
    ("calendar/suggestions", f"/calendar/suggestions?person={PERSON}"),
    ("genome", f"/genome/t_entitlement_check?person={PERSON}&reference=nearest_expert"),
    ("graph/transitions", "/graph/transitions?task=t_entitlement_check"),
    ("hazard", f"/hazard/{PERSON}"),
    ("git/habits", f"/git/habits?person={PERSON}"),
    ("connections", "/connections"),
    ("privacy/ledger", "/privacy/ledger?limit=50"),
    ("privacy/summary", "/privacy/summary"),
    ("audit", "/audit?limit=50"),
    ("offhours/report", "/offhours/report"),
    ("evidence/packet", f"/evidence/packet?person={PERSON}"),
    ("eval/report", "/eval/report"),
    ("study/mode", "/study/mode"),
    ("calendar/people", "/calendar/people"),
    ("git/people", "/git/people"),
    ("hrt/ledger/score", "/hrt/ledger/score"),
    ("insights/admin/overview", "admin:/insights/admin/overview"),
    ("insights/admin/roles", "admin:/insights/admin/roles"),
    ("insights/admin/firm", "admin:/insights/admin/firm"),
    ("insights/admin/onboarding", "admin:/insights/admin/onboarding"),
    ("hitlist/firm", "admin:/hitlist/firm"),
]


def build_client(profiler: cProfile.Profile | None):
    """An in-process client on an engine app made with warm=False. With a profiler, handler threads run under it."""
    from understudy_engine import http_guard
    from understudy_engine.api.flags import apply_default_flags

    apply_default_flags()
    if profiler is not None:
        import fastapi.dependencies.utils as fdu
        import fastapi.routing as fr
        import starlette.concurrency as sc
        import starlette.routing as sr

        orig = sc.run_in_threadpool

        async def profiled(func, *args, **kwargs):
            def inner(*a, **k):
                profiler.enable()
                try:
                    return func(*a, **k)
                finally:
                    profiler.disable()

            return await orig(inner, *args, **kwargs)

        for mod in (fr, fdu, sr, sc):
            mod.run_in_threadpool = profiled
    from fastapi.testclient import TestClient
    from understudy_engine.api.app import create_app

    app = create_app(warm=False)
    http_guard.ensure_token()
    # the guard judges the Host header: this one is only a header on an in-process client, nothing connects to port 7700
    return TestClient(app, base_url="http://127.0.0.1:7700", client=("127.0.0.1", 1), raise_server_exceptions=False), http_guard


def call(client, headers_admin: dict, spec: str):
    admin = spec.startswith("admin:")
    path = spec.split(":", 1)[1] if admin else spec
    w0, c0 = time.perf_counter(), time.process_time()
    r = client.get(path, headers=headers_admin if admin else {})
    return time.perf_counter() - w0, time.process_time() - c0, r.status_code, len(r.content)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", default="run")
    ap.add_argument("--out")
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--profile", action="store_true")
    ap.add_argument("--threshold", type=float, default=0.15, help="profile endpoints whose warm CPU is above this many seconds")
    ap.add_argument("--only", default="", help="comma list of endpoint-name substrings")
    ap.add_argument("--data")
    ap.add_argument("--home")
    ap.add_argument("--keep", help="reuse/keep this temp dir (so repeat runs skip the copy)")
    ap.add_argument("--top", type=int, default=18)
    ap.add_argument("--ttl", default="0", help="UNDERSTUDY_HEAVY_TTL for the run: 0 (default) measures the handlers themselves, 10 measures them behind the result cache")
    a = ap.parse_args(argv)

    os.environ["UNDERSTUDY_HEAVY_TTL"] = a.ttl
    ctx = prepare(a.data, a.home, tmp=a.keep)
    only = [s for s in a.only.split(",") if s]
    eps = [e for e in ENDPOINTS if not only or any(s in e[0] for s in only)]
    client, guard = build_client(cProfile.Profile() if False else None)
    admin = {"x-understudy-role": "admin", "x-understudy-token": guard.read_token() or ""}
    rows = []
    t_start = time.perf_counter()
    for name, spec in eps:
        cold = call(client, admin, spec)
        warm = [call(client, admin, spec) for _ in range(a.reps)]
        wall_w = sorted(w[0] for w in warm)[len(warm) // 2]
        cpu_w = sorted(w[1] for w in warm)[len(warm) // 2]
        rows.append({"endpoint": name, "status": cold[2], "bytes": cold[3], "cold_wall": cold[0], "cold_cpu": cold[1], "warm_wall": wall_w, "warm_cpu": cpu_w})
        print(f"{name:28s} {cold[2]}  cold {cold[0]*1000:8.0f} ms wall {cold[1]*1000:8.0f} ms cpu | warm {wall_w*1000:8.0f} ms wall {cpu_w*1000:8.0f} ms cpu  ({cold[3]} B)", flush=True)
    rows.sort(key=lambda r: -r["warm_cpu"])
    print(f"\n== {a.label}: ranked by warm CPU (median of {a.reps}); total {time.perf_counter() - t_start:.1f} s ==")
    for r in rows:
        print(f"{r['endpoint']:28s} warm cpu {r['warm_cpu']*1000:8.0f} ms   cold cpu {r['cold_cpu']*1000:8.0f} ms   status {r['status']}")
    if a.out:
        with open(a.out, "w") as fh:
            json.dump({"label": a.label, "reps": a.reps, "rows": rows}, fh, indent=1)

    if a.profile:
        heavy = [r for r in rows if r["warm_cpu"] > a.threshold]
        # a second app, built with the profiler hooked in, on the same data copy (caches in the first app do not carry over: warm the profiled one first)
        prof = cProfile.Profile()
        client2, _ = build_client(prof)
        spec_of = dict(eps)
        for r in heavy:
            spec = spec_of[r["endpoint"]]
            call(client2, admin, spec)                       # warm this endpoint in the profiled app
            prof.clear() if hasattr(prof, "clear") else None
            for _ in range(2):
                call(client2, admin, spec)
            s = io.StringIO()
            st = pstats.Stats(prof, stream=s).strip_dirs().sort_stats("tottime")
            st.print_stats(a.top)
            print(f"\n######## PROFILE {r['endpoint']} (warm CPU {r['warm_cpu']*1000:.0f} ms, two calls, by tottime)")
            print(s.getvalue()[:6000])
            s = io.StringIO()
            pstats.Stats(prof, stream=s).strip_dirs().sort_stats("cumulative").print_stats(a.top)
            print(f"-- by cumulative\n" + s.getvalue()[:6000])
    if not a.keep:
        ctx.cleanup()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
