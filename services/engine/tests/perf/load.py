"""Load check on a PRIVATE engine (port 17790 by default, never 7700) started on a copy of the live data.

    python services/engine/tests/perf/load.py [--port 17790] [--rounds 10] [--every 1.0] [--ttl 10] [--keep <tmpdir>]

Starts ``understudy serve`` the way the live stack does (warm-up included, so the first seconds are the worst case), then fires the Growth page's data
requests and the Home page's requests all at once, ``rounds`` times (one round every ``every`` seconds whether or not the last one has finished: a client
that gives up does not stop the server's work, so rounds overlap on a slow engine), while /health is polled every 100 ms from another thread.
Prints the /health latency percentiles and each route's. Exit status 1 when /health p95 is over 300 ms.
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(__file__))
from _env import ENGINE_DIR, prepare  # noqa: E402

import httpx  # noqa: E402

PERSON = "p_learn01"
GROWTH = [
    f"/calendar/week?person={PERSON}", f"/calendar/suggestions?person={PERSON}", f"/genome/t_entitlement_check?person={PERSON}&reference=nearest_expert",
    f"/git/habits?person={PERSON}", f"/graph/work?person={PERSON}", f"/presence?person={PERSON}", f"/growth?person={PERSON}",
]
HOME = [
    "/queue?status=pending", f"/coach/state?person={PERSON}", f"/attention/next?person={PERSON}&peek=1", "/kill", f"/briefing?person={PERSON}",
    f"/insights/worker?person={PERSON}", "/routines", "/hitlist", "/identity", f"/attention/settings?person={PERSON}", "/connections", "/profile",
]


def pct(xs: list[float], q: float) -> float:
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(q * (len(xs) - 1))))] if xs else float("nan")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=17790)
    ap.add_argument("--rounds", type=int, default=10)
    ap.add_argument("--every", type=float, default=1.0)
    ap.add_argument("--ttl", default="10", help="UNDERSTUDY_HEAVY_TTL of the private engine")
    ap.add_argument("--keep")
    ap.add_argument("--settle", type=float, default=0.0, help="seconds to wait after /health first answers before the load starts")
    a = ap.parse_args()
    if a.port in (7700, 7710):
        raise SystemExit("refusing: that is the live stack's port")

    ctx = prepare(tmp=a.keep)
    env = dict(os.environ, PYTHONPATH=str(ENGINE_DIR), ENGINE_PORT=str(a.port), UNDERSTUDY_ENGINE_LISTEN_PORT=str(a.port), AGENT_PORT="1",
               UNDERSTUDY_HEAVY_TTL=a.ttl, UNDERSTUDY_MOCK="0")
    env.pop("UNDERSTUDY_TEST_RELAXED_GUARD", None)               # production guard: the Host and peer rules of the live engine
    log = open(ctx.tmp / "engine.log", "w")
    proc = subprocess.Popen([sys.executable, "-c", f"from understudy_engine.cli import main; raise SystemExit(main(['serve','--port','{a.port}']))"],
                            cwd=str(ctx.tmp), env=env, stdout=log, stderr=subprocess.STDOUT)
    base = f"http://127.0.0.1:{a.port}"
    rc = 0
    try:
        t0 = time.time()
        while time.time() - t0 < 120:
            try:
                if httpx.get(base + "/health", timeout=2).status_code == 200:
                    break
            except Exception:
                time.sleep(0.3)
        else:
            raise SystemExit("the private engine did not start; see " + str(ctx.tmp / "engine.log"))
        print(f"engine up after {time.time() - t0:.1f} s on :{a.port} (warm-up still running in the background)", flush=True)
        time.sleep(a.settle)

        health: list[float] = []
        health_err = [0]
        stop = threading.Event()

        def poll_health() -> None:
            with httpx.Client(timeout=10) as c:
                while not stop.is_set():
                    s = time.perf_counter()
                    try:
                        c.get(base + "/health")
                        health.append(time.perf_counter() - s)
                    except Exception:
                        health_err[0] += 1
                    time.sleep(0.1)

        lat: dict[str, list[float]] = {}
        lock = threading.Lock()

        def one(path: str) -> None:
            s = time.perf_counter()
            try:
                with httpx.Client(timeout=60) as c:
                    r = c.get(base + path)
                    code = r.status_code
            except Exception as exc:
                code = type(exc).__name__
            with lock:
                lat.setdefault(path.split("?")[0], []).append(time.perf_counter() - s)
                if code not in (200, 404, 422):
                    lat.setdefault("!errors " + path.split("?")[0] + " " + str(code), []).append(1.0)

        hp = threading.Thread(target=poll_health, daemon=True)
        hp.start()
        pool = ThreadPoolExecutor(max_workers=64)
        futs = []
        w0 = time.perf_counter()
        for r in range(a.rounds):
            for p in GROWTH + HOME:
                futs.append(pool.submit(one, p))
            time.sleep(a.every)
        for f in futs:
            f.result()
        wall = time.perf_counter() - w0
        stop.set()
        hp.join()
        pool.shutdown()

        print(f"\n{a.rounds} rounds of {len(GROWTH) + len(HOME)} requests ({len(futs)} total), one round every {a.every} s; all answered after {wall:.1f} s")
        print(f"/health: n={len(health)} errors={health_err[0]}  p50={pct(health, .5)*1000:.0f} ms  p95={pct(health, .95)*1000:.0f} ms  p99={pct(health, .99)*1000:.0f} ms  max={max(health)*1000:.0f} ms")
        print(f"{'route':28s} {'n':>4s} {'p50 ms':>8s} {'p95 ms':>8s} {'max ms':>8s}")
        for k, v in sorted(lat.items(), key=lambda kv: -pct(kv[1], .95)):
            print(f"{k:28s} {len(v):4d} {pct(v, .5)*1000:8.0f} {pct(v, .95)*1000:8.0f} {max(v)*1000:8.0f}")
        p95 = pct(health, .95)
        print(f"\nRESULT: /health p95 {p95*1000:.0f} ms ({'OK' if p95 < 0.3 else 'TOO SLOW'}, limit 300 ms)")
        rc = 0 if p95 < 0.3 else 1
    finally:
        proc.terminate()
        try:
            proc.wait(10)
        except subprocess.TimeoutExpired:
            proc.kill()
        log.close()
        if not a.keep:
            ctx.cleanup()
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
