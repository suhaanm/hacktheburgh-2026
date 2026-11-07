"""Run the bake-off jobs: resumable, cached, budget-guarded. One thread per contender (so each contender's calls are sequential and
its latencies are not inflated by its own parallelism); the three contenders run side by side.

A job is (kind, contender, case). Its cache key is built from the model id, API, prompt hash and image hash, so a resumed run only
makes the calls that are missing. When the budget guard stops the run, every job not yet made is recorded as a dropped cell.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from . import cache as cachemod
from .budget import Budget
from .contenders import Contender, Out

KINDS = ("point_desc", "point_step", "glance", "verify")


@dataclass
class Job:
    kind: str
    case_id: str
    image_file: str
    image_sha: str
    desc: str = ""
    step: str = ""
    check: str = "page_shows_result"
    rep: int = 0
    group: str = ""

    def prompt_text(self) -> str:
        """What identifies the prompt in the cache key (the description, step id or check id; the template is versioned by KIND)."""
        return f"{self.kind}|{self.desc}|{self.step}|{self.check}|v1"


def key_for(c: Contender, j: Job) -> str:
    return cachemod.make_key(kind=j.kind, contender=c.name, model=c.model, api=c.api, prompt=j.prompt_text(), image_sha=j.image_sha,
                             schema_name=j.kind, rep=j.rep, extra=c.thinking)


class Runner:
    def __init__(self, shots_dir: Path, cache: cachemod.ResultCache, budget: Budget, *, log: Callable[[str], None] = print,
                 call_fn: Callable[[Contender, Job, bytes], Out] | None = None) -> None:
        self.shots_dir, self.cache, self.budget, self.log = shots_dir, cache, budget, log
        self._call_fn = call_fn or self._default_call
        self._jpeg: dict[str, bytes] = {}
        self._lock = threading.Lock()
        self.stop = threading.Event()
        self.counts = {"cached": 0, "live": 0, "failed": 0, "dropped": 0}

    def jpeg(self, fname: str) -> bytes:
        with self._lock:
            if fname not in self._jpeg:
                from understudy_agent.models.imaging import prepare_frame

                self._jpeg[fname] = prepare_frame((self.shots_dir / fname).read_bytes())
            return self._jpeg[fname]

    @staticmethod
    def _default_call(c: Contender, j: Job, jpeg: bytes) -> Out:
        return c.call(j.kind, jpeg, desc=j.desc, step=j.step, check=j.check)

    def run_one(self, c: Contender, j: Job) -> dict[str, Any] | None:
        key = key_for(c, j)
        hit = self.cache.get(key)
        if hit is not None:
            with self._lock:
                self.counts["cached"] += 1
            return hit
        if self.stop.is_set() or not self.budget.allow(c.est_cost()):
            self.stop.set()
            self.budget.drop({"contender": c.name, "kind": j.kind, "case_id": j.case_id, "rep": str(j.rep), "reason": "budget"})
            with self._lock:
                self.counts["dropped"] += 1
            return None
        out = self._call_fn(c, j, self.jpeg(j.image_file))
        row = self.cache.put(key, {"kind": j.kind, "contender": c.name, "model": c.model, "api": c.api, "case_id": j.case_id,
                                   "rep": j.rep, "group": j.group, "image_sha": j.image_sha, **out.as_row()})
        self.budget.add(out.cost_usd if out.cost_usd is not None else c.est_cost(), contender=c.name, kind=j.kind)
        with self._lock:
            self.counts["live" if out.ok else "failed"] += 1
        return row

    def run(self, contenders: list[Contender], jobs: list[Job]) -> None:
        def worker(c: Contender) -> None:
            t0 = time.time()
            for i, j in enumerate(jobs, 1):
                if self.stop.is_set() and self.cache.get(key_for(c, j)) is None:
                    self.budget.drop({"contender": c.name, "kind": j.kind, "case_id": j.case_id, "rep": str(j.rep), "reason": "budget"})
                    with self._lock:
                        self.counts["dropped"] += 1
                    continue
                self.run_one(c, j)
                if i % 25 == 0:
                    self.log(f"  {c.name}: {i}/{len(jobs)} jobs, {time.time() - t0:.0f}s, est. spend US${self.budget.spent:.3f}")

        threads = [threading.Thread(target=worker, args=(c,), name=f"bench-{c.name}") for c in contenders]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
