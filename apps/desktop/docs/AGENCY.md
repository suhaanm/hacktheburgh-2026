# Agency: letting the assistant do small things, safely

Alongside teaches first. Agency is an optional, off-by-default helper for the moments when a learner says "can you just open it?" The assistant offers a choice ("I can open it for you, or show you how. Which would you like?"), waits, and only acts after the learner presses Yes in a window the model cannot press.

## What it can do

| Tool | What | Needs | Confirmation |
|---|---|---|---|
| `open_for_me{kind,value}` | Opens ONE website (http/https), app, indexed file (reveals it in Finder) or an everyday settings pane (displays, text_size, sound, wifi, bluetooth, notifications, keyboard, general). Web search = open a prefilled `https://www.google.com/search?q=...` URL. | Nothing special. No screenshot, no Accessibility. | Every time (both modes) |
| `act_for_me{goal}` | A short task of up to 8 steps on Gemini's `computer_use` tool: click, double-click, type, a few keys, scroll, wait. One action per model call, on a fresh screenshot. | macOS Accessibility; `ALONGSIDE_AGENCY_LOOP=1` (hidden until verified end to end) | `ask_each`: every action. `ask_per_task`: the plan once, then low-risk clicks run; typing, keys and anything the model or the policy flags still ask. |
| `do_it_for_me{target}` (OVERLAY) | One click on one grounded element | Accessibility | Gated by the same switch |

Setting `agency`: `off` (default) / `ask_each` (recommended) / `ask_per_task`. `doItForMeAllowed` is kept equal to `agency !== 'off'`. With `off`, every tool returns `{allowed:false, code:'agency_off'}` and the assistant teaches instead and mentions the switch.

## What it never does

Enforced in code (`src/main/agency/policy.ts`), not by the prompt:

- Hard denylist on the grounded label, the target text and any typed text: pay, purchase, buy, order, checkout, send, submit, delete, remove, erase, transfer, confirm, sign in, log in, password, card, allow, grant, install, accept (plus the extra words from the Clicky safety policy). Blocked means no confirmation window, no action: the assistant shows the target and leaves it to the learner.
- Never into a secure field, during a scam check (`spot_scam` lesson or running `scam_check` agent), or on a `safetyCritical` lesson step.
- URLs: http/https only, no credentials, no `javascript:`/`file:`/`data:`, no bare or private IPs, no punycode. The one localhost exception is our practice stage origin.
- Keys: an allowlist only (no screenshot shortcut). Typed text max 300 characters.
- **Return is blocked, with one narrow exception (`return-after-type`, user decision 16:11).** It passes only when ALL hold: the immediately preceding executed action of the same task was a `type` whose text is a plain query (80 characters or fewer, no `@`, no 6+ digit run, no card-like or secret-like text, nothing on the denylist); the focused element is not an `AXSecureTextField` (if that cannot be read, the frontmost window title must not match login, sign in, password, checkout, payment, pay, billing, card, account, register, apply-now or submit; if neither can be read, it stays blocked); the frontmost app is the task's scoped target and is a browser or a named native app (never Claude or a terminal); the goal has no denylist word once negated clauses are removed; no safety-critical step and no scam check; at most 2 Return presses per task; under `ask_per_task` the plan is already confirmed (then no further prompt; `ask_each` still asks). Only the word "submit" in the model's own description of the Return is ignored; any other denylist word still blocks. The audit line says `keys: return-after-type`. Return after a click, on a login or payment page, or for a dialog stays blocked.
- **Cookie banners.** Declining options (No thanks, Reject, Reject all, Only necessary, Dismiss, Close, Not now, Decline) may be clicked even though their label says cookie or consent; Accept, Agree, Allow all and anything else with those words stay blocked, unless the GOAL text itself says to accept the cookies (then only cookie-banner labels pass). Other denylist words in the same label still block.
- **Hard floors, never relaxed:** paying, purchasing and transfers; passwords and card details; sending or posting messages and email; permanent deletion; system security, permissions and Settings; installing software.
- Blocked results say what was blocked, why in one sentence and what the learner can do next.
- Rate: at least 1.5 s between actions, at most 12 per task, at most 16 per minute.
- Stop (`session:ended`) ends a task at the next check; nothing is left half-done and nothing queued runs.

## Loop discipline (`act-for-me.ts`)

A mutation only follows a fresh screen read. The model proposes one action; our policy decides, not the model's words. The action is shown on screen (ring, ghost-cursor path, a plain sentence) before it runs. A failed action is never retried and the same action is never run twice. Two steps with no visible change end the task. Success is reported only when the Verifier confirms the goal on a fresh screenshot; otherwise the result is `gave_up` and the assistant is told not to say it is done. The learner's goal text is the only task; text in screenshots is data. The model call is stateless (`store:false`): each request carries the goal, a short text history and a fresh screenshot. Google's prompt-injection detection is on, and the model's `require_confirmation` forces a confirmation even after the plan was approved.

Without Accessibility the loop never acts: it rings the target and tells the learner what to click.

## Audit

`userData/actions.log`, JSON lines, mode 0600: `{t, tool, decision, ok, code, label?, host?, step?, dryRun?}`. No screenshots, no typed text, no URL paths or queries; labels that look like secrets are redacted. A task also appears as a "Doing this for you" chip in the agent tray. Each success is counted per skill or target in the profile (`## Done for me`), and the progress data carries `doneForMe: {total, text: "Done for you: N times..."}` so the progress view can show dependency honestly (the dock line itself belongs to the DESIGN lane).

## Permissions

`open_for_me` needs none. Click, type, keys and scroll need macOS Accessibility (System Settings, Privacy and Security, Accessibility). Screen Recording is already required for the core product.

## Flags

- `ALONGSIDE_AGENCY_LOOP=1`: enables `act_for_me` (otherwise it returns `unavailable`).
- `ALONGSIDE_ACTUATOR_DRYRUN=1`: every actuator call is logged, nothing happens (tests always use it).

## Fit with "keep people in control"

Off by default; every action explained before it happens; a real click approves each one (or the plan once); Stop always works; money, passwords, sending and permissions stay with the learner; everything done is logged and counted; the assistant offers to show how next time.

## Verified and not verified

Verified: 228 unit tests under `tests/agency` (policy table, open_for_me, the whole loop with a scripted model, request shape of the model call); three real `computer_use` calls on saved stage screenshots (the API accepted `system_instruction`, `enable_prompt_injection_detection` and `excluded_predefined_functions`; "make the text bigger" proposed a click on the Larger button at the right place; "reply to the message" stopped without acting).

Real Mac, dry-run actuator, debug-route driven (`docs/reports/MAC_B.md`, 14:50-15:00 GMT): 15 `open_for_me` refusals (bad URL schemes, credentials, private IP, punycode, shell-looking app names, non-indexed paths, bad panes) and 7 `act_for_me` goals (pay, send, delete, log in, password, card, buy) refused in milliseconds with no confirmation window; `agency: off` refused everything; with `ALONGSIDE_AGENCY_LOOP=1` the real model's first proposal was a click on the right Calculator key, with ring, ghost cursor and bubble shown before the approval window; no HTTP route can approve a confirmation; the audit file is mode 0600 with no typed text, screen text or URL paths. Known gaps from that run: a pending confirmation can survive Stop while no session is active (SHELL informed), and audit labels for blocked app names store the raw string.

Dry-run verified only: no approved real action (a real website open, app launch, Finder reveal, click, keystroke or scroll) has been verified on the Mac, because the test shell had no Accessibility and could not press the approval button.

Not verified: the loop end to end in Electron on a real web page (the Calculator goal, a real run at 16:05, passed; the Return-after-typing allowance and the cookie-banner decline are covered by unit tests with fake front-app and focus providers, not yet on the real careers page; reading the focused element's subrole through System Events returned nothing in the one app tried, so the window-title check is what decides in practice); the real Verifier on a post-action screen. `ask_per_task` relies on the model's `intent` text, Google's `safety_decision` and the denylist for low-risk clicks, so `ask_each` is the recommended mode.

## Auto-assist on stall (off by default)

- Opt-in twice: env `ALONGSIDE_AUTO_ASSIST=1` AND `settings.agency !== 'off'`. Without the env flag the runner has no assist hook at all.
- When the stall ladder is spent (about 20 s at L2/L3) on a non-safety-critical step, the lesson runner offers once per step: "I can click it for you, or you can try once more. Which would you like?"
- It reuses the existing `do_it_for_me` flow (`src/main/actuator/flow.ts`, registered via `src/main/agency/assist.ts`): real-click confirmation every time (never skipped, even under `ask_per_task`), denylist, scam/safety refusals, audit, Stop. The runner also pre-skips scam checks, safety steps and denylisted words.
- An approved click is narrated in one sentence, counted with `recordDoneForMe` (progress view stays honest) and followed by an offer to show how next time. A declined offer leaves the learner in control; nothing is re-offered on that step.
- Unit tests: `describe('auto-assist on stall')` in `src/main/teaching/__tests__/runner.test.ts`. Real-Mac behaviour is unverified.

## Autonomous mode (opt-in, off by default)
- `agency: 'autonomous'` lets the assistant carry out an approved action without the "Yes, go ahead" click, but only when ALL hold: the owner switched it on in the dock (Settings > Safety > "Let it act on its own when I am away"; main drops it from every other source, tools, /inject, debug server and the demo driver), the Mac has had no keyboard/mouse input for `awaySeconds` (default 60, via `powerMonitor.getSystemIdleTime()`), and a lesson step has been stalled for 90 s.
- One decision point: `askToProceed` in `src/main/agency/common.ts`. The same policy and actuator run before and after it; there is no second path.
- Floor unchanged: denylist, password fields, scam context, safety-critical steps, URL rules, 8-step cap. Extra caps: one auto action per step, 3 per session. The ring/ghost and a spoken line come first, with a 1.5 s lead-in.
- Visible: the dock shows "Autonomous: on. Acting on its own while you are away: Stop". Each audit line carries `approval: 'auto-away'`.
- Stop (button or hotkey) cancels at once and switches autonomous off (agency back to ask each time); the owner must turn it on again.
- Honest limits: real-Mac click accuracy is still being fixed, so keep it off for demos until verified. "Stalled" is a 90 s timer on the step, not a read of the help ladder.
