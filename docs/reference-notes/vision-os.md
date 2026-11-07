# VisionOS (MIT) - notes for `supervisor.py` (AGT-2)

**What it does well.** A coordinator with one worker thread and a single replaceable pending request. Every submit bumps a generation counter and sets the previous task's cancel event. A result is accepted only if its task id and generation are still current ("obsolete_result" is logged otherwise). A deadline is armed per request and a watchdog thread converts overdue work into a timeout error. Stop is synchronous: it flips cancel, bumps the generation, clears pending, and calls a local stop hook without touching any provider.

**What informs us.** AGT-2: generations, cancel events, deadlines, watchdog, stale-result rejection, and "stop never depends on a model call".

**What we do differently.**
- We write our own supervisor (no code copied; no vendor entry needed). Our worker runs benefit runs (long, multi-navigator) rather than 5-second voice intents, so the deadline is per-run and configurable, not capped at 5 s.
- Tasks are `Callable[[TaskContext], Any]`; the context exposes `is_current()` and `check()` and every navigator step calls it, so cancellation is cooperative AND the supervisor drops results from stale generations even if a task ignores cancellation.
- The file kill flag `data/KILL` is polled by the watchdog, so an external process (engine `/kill`, desktop hotkey) stops the run without any in-process call.
- Stop latency is tested with a stubbed slow "model" call: stop must return in under 1 s regardless.
