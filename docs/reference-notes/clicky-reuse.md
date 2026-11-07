# Clicky reuse map (CLK-1)

Read-only study, nothing run. Sources: farzaa/clicky (Swift app, TypeScript worker) and rickkdev/clicky (Windows fork; adds the Python `hermes-clicky-plugin`). Both LICENSE files are identical: MIT, Copyright (c) 2026 Farza. The plugin credits "Rick / Clicky contributors", so headers and notices name the fork.

## Reuse map

| Module | What it does | Decision | Fits | Effort / benefit |
|---|---|---|---|---|
| `scoped_autopilot.py` | bounded session: timeout, step cap, scope, stop on bad verification, cancel | **Lifted and reshaped:** `vendor/clicky/clicky_lift/lease.py` | runtime: one lease per child agent (BGA-1) | Fills a gap (per-child tool scope, expiry, single revoke, cascade). 2 h, medium |
| `post_action_verification.py` | classifies a fresh observation: success, failed, uncertain, blockedByPrompt | **Lifted and reshaped:** `clicky_lift/postcheck.py` | after each agent step, beside `completion.py` | `completion.py` checks only the final page; this checks every step. 2 h, medium-high |
| `confirmation_state.py` | confirmation with expiry, approve, cancel, stale | Skip | none | `queue.py` already has human-origin-only, signature-bound, single-use approvals. Clicky's is weaker (replayable; bound to the proposal id only) |
| `audit_log.py` | JSONL log, secret regexes | Skip | none | `audit.py` is hash-chained, locked, token-only |
| `safety_policy.py` | substring keyword flags | Words only | `security/labels.py` | Substring match fires on "format" inside "information" and scans the model's own rationale. Ours is word-bounded and NFKC-normalised |
| `permission_policy.py` | five tiers; a request cannot raise the tier | Principle only | gates, rungs A0 to A3 | Rungs are richer. Principle kept: a child lease can only narrow its parent. Alongside already carries the tiers in TypeScript |
| `plugin.yaml`, `schemas.py`, `register(ctx)` | manifest, tool schemas, registration | Conventions only | PLG-1 manifest | Fifteen lines of YAML; nothing worth lifting |
| `bridge_client.py`, mac bridge | JSON-RPC over stdio, runs osascript | **Do not adopt** | none | Unsafe, see below |
| Overlay, capture, bezier flight, arrows; the key-proxy worker | Swift, C#, TypeScript | Overlay etc. already in `apps/desktop` with notices; worker skipped | none | No new work |

**Words our `labels.py` lacks** (plain vocabulary, for agent-safety to add): credential: passcode, otp, one-time code, seed phrase, private key, secret key, login code; pay: invoice, wire transfer.

## Lifted modules

Package `clicky_lift` in `vendor/clicky/` (MIT text, `Adapted from` headers, README with adoption snippets). Standard library only, injectable clock, audit-safe output (tokens and numbers, never page text). 107 hermetic tests in `services/agent/tests/clicky/`, hostile-input suites included; breaking any of four safety properties on purpose made a test fail.
- **Lease** (`Lease`, `LeaseBook`): scope is a set of tool names plus a time to live, a step cap and revocation. An out-of-scope call stops the lease (fail closed). A child can only narrow its parent, and a revoked parent stops it. Monotonic clock fixed at construction (Clicky let the caller pass the time). **No site or app scope**: SEC-10 and D12 forbid it. No `extend`.
- **Postcheck** (`Condition`, `verify`, `run_step`): declarative postconditions over named fields read by code. Blockers beat success; an unreadable field is `uncertain`; exact, ASCII-only matching; verdicts never echo observed values.

Adoption: `lease.check(kind)` before `pipeline.authorise`, `lease.record(post)` after; `on_event` to `AuditLog.append`; `killed=is_killed` (all shown running against the real pipeline in `test_adoption.py`). **Gap found, already closed by agent-safety:** `consume_approval` ignored approval age; it now has a 30-minute limit.

## Unsafe to run (not run)

1. `bridge_client.py` runs `subprocess.run(..., shell=True)` on a command from `CLICKY_BRIDGE_COMMAND` or an unquoted inferred path.
2. `tools.execute_clicky_action` hard-codes `permissionDecision` and `safetyDecision` as "allow" in the bridge request, and a model-supplied `confirmationApproved` becomes an approved confirmation. The model can self-approve; the policy modules are not enforced on that path.
3. The mac bridge interpolates the hotkey key into AppleScript unescaped (`focusWindow` escapes only the double quote): script injection.
4. `ClickyAnalytics` (Swift, C#) ships a PostHog key and sends transcripts and replies; a form-service email POST sits in `CompanionManager.swift`. Also bundled game music and upstream signing and update settings.

## Ranked feature ideas (Alongside overlap marked)

1. **Lease countdown and revoke on the Agents screen.** Effort 1 to 2 h (runtime, dashboard). Demo value high: visible expiry, revoke stops a child in under a second. New.
2. **Per-step verified chips** ("verified" or "uncertain, asked you") from postcheck. Effort 1 to 2 h. Demo high. Alongside verifies coach steps only.
3. **Ring-accuracy fixtures with distractor regions** (the fork's pointing redesign: a skipped pointer beats a wrong one). A COA-2 eval: ring-on-target rate with a Wilson interval, DOM-first against a vision-only baseline, labelled synthetic. Effort 2 to 3 h (platform). Demo medium, evidence high. Alongside has overlay, mapping and DOM grounding, not the eval.
4. **Tone from the memory file:** coach flavour reads `## Preferences` and the pack's tone; edit a line, tone changes. Alongside has two personas and push-to-talk; only the memory tie is new. Effort 1 h. Demo medium.
5. **Capabilities-first plugin handshake** (PLG-1): report capabilities and reasons before use, "unavailable" never fake success, no self-raised permissions. Conventions only. Effort 1 h. Demo low to medium.

**Not worth it:** the `[POINT:x,y]` text tag (DOM-first grounding supersedes it; keep "none if unsure" for the vision fallback; the fork's own notes call semantic localisation unsolved); ElevenLabs through Clicky's path (single-voice proxy; D19's cached audio makes sentence-pipelined speech moot); a stdio JSON-RPC plugin host (3 h or more, low demo value).
