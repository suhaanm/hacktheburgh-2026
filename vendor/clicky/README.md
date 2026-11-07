# vendor/clicky: reshaped lifts from Clicky's Hermes plugin (CLK-1)

Two small, tested, standard-library-only modules in the package `clicky_lift`. They fill gaps the agent service does not cover; everything Clicky had that `services/agent` already does better was left out (see `docs/reference-notes/clicky-reuse.md`).

**Provenance and licence.** Adapted from `hermes-clicky-plugin/` in rickkdev/clicky (https://github.com/rickkdev/clicky), a Windows fork of farzaa/clicky (https://github.com/farzaa/clicky). Both repositories ship the same MIT licence, "Copyright (c) 2026 Farza"; the full text is in `LICENSE` here and every `.py` file starts with an `Adapted from ... (MIT)` header. Each module's docstring lists what was changed. No file was run from the reference copies; the code was read and rewritten.

| File | Upstream | What it is |
|---|---|---|
| `clicky_lift/lease.py` | `scoped_autopilot.py` | `Lease` and `LeaseBook`: per-child tool scope, deadline, step cap, revoke, parent cascade |
| `clicky_lift/postcheck.py` | `post_action_verification.py` | `Condition`, `verify`, `run_step`: postconditions checked after a step |

## Adopting `lease.py` (agent-runtime track, BGA-1)

```python
from clicky_lift import LeaseBook, StopReason
book = LeaseBook(killed=is_killed, on_event=sink)          # sink: lease event -> AuditLog.append (see tests/clicky/test_adoption.py)
lease = book.issue(holder="child_1", tools=spec.tools, ttl_s=spec.seconds, max_steps=spec.steps)   # trusted code only
child = book.issue(holder="child_2", tools={"read_file"}, ttl_s=60, max_steps=5, parent=lease)     # can only narrow
...
d = lease.check(action.kind)       # BEFORE pipeline.authorise(); a refusal ends the child with d.code
...
lease.record(post)                 # failed, uncertain and blocked_by_prompt stop the lease
book.revoke_all("operator_stop")   # the stop button; also feeds the Agents screen via book.snapshots()
```

- It answers one question, "may this child still act with this tool?". Content checks (gates, data flow, injection, drift) stay in `SafetyPipeline`; `StepBudget` stays as the per-run cap. The lease adds per-child scope, independent revoke and parent-child narrowing.
- The scope is tool names, never sites or apps (SEC-10, D12). There is no `extend`: more power means a new lease from trusted code.
- Use `Lease.snapshot()` for the countdown on the Agents screen (state, `remaining_s`, steps).

## Adopting `postcheck.py` (agent-runtime and agent-core tracks, AGT-4, COA-5)

```python
from clicky_lift import Condition, Observation, matches, equals, absent, verify
cond = Condition.of(matches("note_id", r"CN-\d{4}"), equals("status", "saved"), absent("banner", "error"))
post = verify(cond, Observation(fields_read_by_code, blockers=frozenset(detector_signals)))
if not post.ok: pause_for_human(post.reason)        # failed, uncertain, blocked_by_prompt all stop the run
```

- Fields must come from trusted code (DOM reads, the quarantined reader's schema-checked fields), never from a model's claim. Point checks at narrow fields; a whole-page `contains` can be satisfied by text a page prints.
- Patterns are ASCII-only (`re.ASCII`), types are strict, nothing is Unicode-folded, an unreadable field is `uncertain`. Results carry tokens and numbers only (`PostResult.audit_meta()` is valid `AuditLog` meta).
- It complements `completion.py` (final page, benefits task) with a per-step check usable by any exemplar.

## Using the package before it is installed

`vendor/clicky` is not on `sys.path` by default. Either add it to the root pytest config (`pythonpath = ["vendor/clicky"]`), or make it a uv workspace member (`pyproject.toml` here is ready for that: add `vendor/clicky` to the root `members` and `understudy-clicky-lift` to the agent's dependencies). The tests in `services/agent/tests/clicky/` add the path themselves.

## Not lifted, on purpose

`confirmation_state.py` (`queue.py` already has signature-bound, single-use, human-origin-only approvals), `audit_log.py` (`audit.py` is hash-chained), `safety_policy.py` (substring matching; `labels.py` is word-bounded), permission tiers (our rungs), and the stdio bridge (shell execution, self-approval, AppleScript injection: unsafe).
