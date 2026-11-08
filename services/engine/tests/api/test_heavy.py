"""Single-flight, the short result cache and the limit of two computing heavy reads (api/heavy.py)."""
from __future__ import annotations

import asyncio
import threading
import time

import httpx
import pytest
from fastapi import FastAPI, HTTPException, Request

from understudy_engine.api.heavy import HEAVY_PREFIXES, HeavyGetMiddleware, is_heavy, settings_from_env

class Clock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


def build(*, ttl: float = 10.0, limit: int = 2, clock=None, sleep: float = 0.05, busy: float = 0.0, signature=lambda: ()):
    calls: dict[str, int] = {}
    live = {"now": 0, "max": 0}
    lock = threading.Lock()
    app = FastAPI()

    def bump(name: str) -> int:
        with lock:
            calls[name] = calls.get(name, 0) + 1
            return calls[name]

    def work() -> None:
        with lock:
            live["now"] += 1
            live["max"] = max(live["max"], live["now"])
        try:
            if busy:
                end = time.perf_counter() + busy
                while time.perf_counter() < end:        # CPU bound: holds the GIL like the real handlers did
                    pass
            else:
                time.sleep(sleep)
        finally:
            with lock:
                live["now"] -= 1

    @app.get("/briefing")
    def briefing(n: int = 0):
        work()
        return {"n": n, "call": bump(f"briefing{n}")}

    @app.get("/routines")
    def routines():
        work()
        return {"call": bump("routines")}

    @app.get("/hitlist")
    def hitlist():
        if bump("hitlist") == 1:
            raise HTTPException(500, "first call fails")
        return {"ok": True}

    @app.get("/coach/state")
    def coach_state():
        bump("coach_state")
        raise HTTPException(404, "unknown")

    @app.get("/insights/admin/overview")
    def admin(request: Request):
        work()
        return {"role": request.headers.get("x-understudy-role", ""), "call": bump("admin")}

    @app.get("/health")
    def health():
        bump("health")
        return {"ok": True}

    @app.get("/queue")
    def queue():
        return {"call": bump("queue")}

    @app.post("/memory/forget")
    def forget():
        return {"forgot": True}

    mw = {}

    def factory(inner, **kw):
        mw["m"] = HeavyGetMiddleware(inner, **kw)
        return mw["m"]

    kw = {"ttl": ttl, "limit": limit, "signature": signature}
    if clock is not None:
        kw["clock"] = clock
    wrapped = factory(app, **kw)
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=wrapped), base_url="http://test")
    return client, calls, live, mw["m"]


def tag(r: httpx.Response) -> str | None:
    return r.headers.get("x-understudy-cache")


def test_which_routes_are_heavy():
    assert is_heavy("GET", "/coach/state") and is_heavy("GET", "/graph/work") and is_heavy("GET", "/insights/admin/firm")
    assert is_heavy("GET", "/hitlist/firm") and is_heavy("GET", "/calendar/week") and is_heavy("GET", "/genome/t_x")
    for cheap in ("/health", "/kill", "/identity", "/queue", "/attention/next", "/attention/settings", "/memory", "/profile", "/connections", "/packs", "/memory/proposals"):
        assert not is_heavy("GET", cheap), cheap
    assert not is_heavy("POST", "/briefing/x/fire") and not is_heavy("GET", "/briefingx")
    assert "/coach/state" in HEAVY_PREFIXES


async def test_cached_answer_equals_uncached():
    cached, calls_c, _, _ = build(ttl=10.0)
    plain, calls_p, _, _ = build(ttl=0.0)
    a = await cached.get("/briefing?n=3")
    b = await cached.get("/briefing?n=3")
    u1, u2 = await plain.get("/briefing?n=3"), await plain.get("/briefing?n=3")
    assert (tag(a), tag(b)) == ("miss", "hit")
    assert a.status_code == b.status_code == 200
    assert a.content == b.content == u1.content            # the second call is the first call's bytes, and the handler's own bytes
    assert calls_c["briefing3"] == 1
    assert calls_p["briefing3"] == 2 and u2.json()["call"] == 2        # without the cache the handler runs each time


async def test_eight_concurrent_calls_run_the_handler_once():
    c, calls, live, mw = build(ttl=0.0, sleep=0.2)             # single-flight even with the result cache off
    rs = await asyncio.gather(*[c.get("/routines") for _ in range(8)])
    assert calls["routines"] == 1
    assert {r.content for r in rs} == {rs[0].content}
    assert sorted(tag(r) for r in rs) == ["miss"] + ["shared"] * 7
    assert mw.stats["computed"] == 1


async def test_different_queries_are_different_flights():
    c, calls, _, _ = build(ttl=10.0)
    await asyncio.gather(c.get("/briefing?n=1"), c.get("/briefing?n=2"), c.get("/briefing?n=1"))
    assert calls == {"briefing1": 1, "briefing2": 1}


async def test_any_write_invalidates_everything():
    c, calls, _, _ = build(ttl=10.0)
    await c.get("/briefing?n=1")
    await c.get("/routines")
    assert tag(await c.get("/routines")) == "hit"
    assert (await c.post("/memory/forget")).status_code == 200
    r = await c.get("/routines")
    assert tag(r) == "miss" and r.json()["call"] == 2
    assert (await c.get("/briefing?n=1")).json()["call"] == 2


async def test_a_computation_that_started_before_a_write_is_not_stored():
    c, calls, _, mw = build(ttl=10.0, sleep=0.3)
    slow = asyncio.create_task(c.get("/routines"))
    await asyncio.sleep(0.05)
    await c.post("/memory/forget")                              # the write lands while the read is computing
    await slow
    r = await c.get("/routines")
    assert tag(r) == "miss" and calls["routines"] == 2            # the pre-write answer was never cached


async def test_ttl_expires_with_a_fake_clock():
    clock = Clock()
    c, calls, _, _ = build(ttl=10.0, clock=clock)
    await c.get("/routines")
    clock.t += 9.0
    assert tag(await c.get("/routines")) == "hit"
    clock.t += 1.5
    r = await c.get("/routines")
    assert tag(r) == "miss" and r.json()["call"] == 2


async def test_errors_are_never_cached():
    c, calls, _, _ = build(ttl=10.0)
    first, second = await c.get("/hitlist"), await c.get("/hitlist")
    assert first.status_code == 500 and second.status_code == 200 and calls["hitlist"] == 2
    n1, n2 = await c.get("/coach/state"), await c.get("/coach/state")
    assert n1.status_code == n2.status_code == 404 and calls["coach_state"] == 2
    assert tag(await c.get("/hitlist")) == "hit"                  # but the good answer is kept


async def test_no_cache_header_and_refresh_force_a_fresh_computation():
    c, calls, _, _ = build(ttl=10.0)
    await c.get("/routines")
    r = await c.get("/routines", headers={"Cache-Control": "no-cache"})
    assert tag(r) == "miss" and r.json()["call"] == 2
    again = await c.get("/routines")
    assert tag(again) == "hit" and again.json()["call"] == 2        # the forced answer replaced the cached one
    assert (await c.get("/briefing?refresh=1")).json()["call"] == 1


async def test_admin_and_worker_answers_are_never_mixed():
    c, calls, _, _ = build(ttl=10.0)
    w = await c.get("/insights/admin/overview")
    a = await c.get("/insights/admin/overview", headers={"x-understudy-role": "admin"})
    assert w.json()["role"] == "" and a.json()["role"] == "admin" and calls["admin"] == 2
    a2 = await c.get("/insights/admin/overview", headers={"x-understudy-role": "admin"})
    assert tag(a2) == "hit" and a2.json()["role"] == "admin"
    other_actor = await c.get("/insights/admin/overview", headers={"x-understudy-role": "admin", "x-understudy-actor": "agent"})
    assert tag(other_actor) == "miss"


async def test_a_change_of_the_workers_memory_files_changes_the_key():
    sig = {"v": (1,)}
    c, calls, _, _ = build(ttl=10.0, signature=lambda: sig["v"])
    await c.get("/routines")
    assert tag(await c.get("/routines")) == "hit"
    sig["v"] = (2,)                                              # a role switch rewrote memory_state.json
    assert tag(await c.get("/routines")) == "miss"


async def test_a_read_that_writes_the_memory_files_is_still_cached():
    """GET /routines merges what it found into routines_state.json, which moves the files' signature during the computation: the answer is stored under the key
    the NEXT request will compute, so the second call is a hit and not a recomputation for ever."""
    sig = {"v": 0}
    c, calls, _, mw = build(ttl=10.0, signature=lambda: (sig["v"],))
    app_inner = mw.app

    async def writes_a_file(scope, receive, send):                  # the handler's side effect: the signature moves while it computes
        sig["v"] += 1
        await app_inner(scope, receive, send)

    mw.app = writes_a_file
    first, second, third = await c.get("/routines"), await c.get("/routines"), await c.get("/routines")
    assert (tag(first), tag(second), tag(third)) == ("miss", "hit", "hit") and calls["routines"] == 1


async def test_cheap_routes_bypass_the_layer():
    c, calls, _, mw = build(ttl=10.0)
    r1, r2 = await c.get("/health"), await c.get("/health")
    assert tag(r1) is None and tag(r2) is None and calls["health"] == 2
    await c.get("/queue"), await c.get("/queue")
    assert calls["queue"] == 2 and mw.stats["computed"] == 0


async def test_at_most_two_heavy_handlers_compute_at_once_and_health_stays_fast():
    c, calls, live, mw = build(ttl=0.0, limit=2, busy=0.15)
    heavy = [asyncio.create_task(c.get(f"/briefing?n={i}")) for i in range(8)]          # eight different keys: eight real computations
    await asyncio.sleep(0.05)
    t0 = time.perf_counter()
    h = await c.get("/health")
    took = time.perf_counter() - t0
    rs = await asyncio.gather(*heavy)
    assert h.status_code == 200 and took < 1.0, took
    assert all(r.status_code == 200 for r in rs) and len(calls) == 8 + 1
    assert live["max"] <= 2 and mw.stats["max_running"] <= 2


async def test_a_client_that_gives_up_does_not_cancel_the_work_or_start_another():
    c, calls, _, _ = build(ttl=10.0, sleep=0.3)
    gone = asyncio.create_task(c.get("/routines"))
    await asyncio.sleep(0.05)
    gone.cancel()
    with pytest.raises(asyncio.CancelledError):
        await gone
    r = await c.get("/routines")                                 # joins the computation the first client started
    assert r.status_code == 200 and calls["routines"] == 1 and tag(r) == "shared"
    assert tag(await c.get("/routines")) == "hit"


async def test_state_is_per_event_loop():
    """The in-process test client makes one loop per call: the per-loop semaphore and flight table must not leak across them."""
    c, calls, _, mw = build(ttl=0.0)

    def go() -> int:
        async def one():
            return (await c.get("/routines")).status_code
        return asyncio.run(one())

    codes = [await asyncio.to_thread(go) for _ in range(3)]
    assert codes == [200, 200, 200] and calls["routines"] == 3


def test_settings_default_and_pytest_cache_off(monkeypatch):
    monkeypatch.delenv("UNDERSTUDY_HEAVY_TTL", raising=False)
    assert settings_from_env()["ttl"] == 0.0 and settings_from_env()["limit"] == 2       # inside pytest the result cache is off by default
    monkeypatch.setenv("UNDERSTUDY_HEAVY_TTL", "7")
    monkeypatch.setenv("UNDERSTUDY_HEAVY_LIMIT", "3")
    assert settings_from_env() == {"ttl": 7.0, "limit": 3, "max_entries": 256}
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.delenv("UNDERSTUDY_HEAVY_TTL")
    assert settings_from_env()["ttl"] == 10.0


async def test_the_cache_is_bounded():
    c, calls, _, mw = build(ttl=100.0)
    mw.max_entries = 3
    for i in range(6):
        await c.get(f"/briefing?n={i}")
    assert len(mw._cache) == 3                                    # noqa: SLF001
    assert tag(await c.get("/briefing?n=5")) == "hit" and tag(await c.get("/briefing?n=0")) == "miss"


def test_warm_person_does_nothing_when_nobody_is_set_up_and_primes_the_caches_when_someone_is():
    import json
    from datetime import datetime, timedelta, timezone

    from understudy_engine import routes_handoff as rh
    from understudy_engine.api.app import warm_person
    from understudy_engine.memory import onboard
    from understudy_engine.memory.paths import data_dir

    assert warm_person() is False                                   # an empty data dir and no profile: nothing to prime, nothing raised
    onboard(rh._mem(), "benefits-processor", {}, "p_warm01")
    d = data_dir() / "real" / "p_warm01"
    d.mkdir(parents=True)
    t0 = datetime(2026, 11, 7, 9, 0, 0, tzinfo=timezone.utc)
    with (d / "2026-11-07.jsonl").open("w") as fh:
        for i in range(8):
            fh.write(json.dumps({"schema": 1, "id": f"ev{i:08d}", "t": (t0 + timedelta(seconds=5 * i)).strftime("%Y-%m-%dT%H:%M:%S.000Z"), "origin": "real", "actor": "human",
                                 "person": "p_warm01", "role": "benefits-processor", "source": "browser", "type": "click"}) + "\n")
    assert warm_person() is True
    src = rh._src()
    first = src.load("p_warm01")
    assert first is not None and src.load("p_warm01") is first       # primed: the next request reuses it


async def test_the_real_app_has_the_layer_and_keeps_health_out_of_it(monkeypatch, tmp_path):
    from understudy_engine.api.app import create_app

    monkeypatch.setenv("UNDERSTUDY_HEAVY_TTL", "10")
    monkeypatch.setenv("UNDERSTUDY_X_CALENDAR", "1")              # the calendar router is an extension: on for this app, so /calendar/people exists
    app = create_app(tmp_path, warm=False)
    assert any(m.cls is HeavyGetMiddleware for m in app.user_middleware)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, client=("127.0.0.1", 1)), base_url="http://127.0.0.1:7700") as c:
        h = await c.get("/health")
        assert h.status_code == 200 and tag(h) is None
        p1, p2 = await c.get("/calendar/people"), await c.get("/calendar/people")
        assert p1.status_code == 200 and (tag(p1), tag(p2)) == ("miss", "hit") and p1.content == p2.content
