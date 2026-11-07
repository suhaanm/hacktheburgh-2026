# Reference note: Mark8 (idea only, no licence)

Source read (read only): `packages/core/src/{events,fold}.ts`, `apps/portal/src/lib/player.ts`. Nothing is copied; the points below are the ideas we re-implement in our own words and our own language (Python).

## What the idea is

1. **One typed event stream is the only source of truth.** Every observable step is an event appended to a JSONL file. Views never read anything else.
2. **A pure reducer.** `state = fold(events)`: no clock, no I/O, no randomness. The same events always give the same state, so replays can be compared and tested.
3. **Replay on a virtual clock.** A recorded file is played back at 1x to 200x. Long gaps (slow model calls in Mark8; idle time for us) are squeezed to a cap so the replay stays watchable. The UI sees the same state shape live and in replay.
4. **A baseline beside every prediction.** Mark8's evaluation always prints the naive answer next to the model's. We carry this into every analytic response (`meta`, baselines).

## What we take, concretely

- `store/`: append-only JSONL, schema-validated on write, `fold(events) -> State` pure, `replay(file, speed, squeeze_idle_s)` that yields frames with a compressed replay time: `t_replay[i] = t_replay[i-1] + min(gap, squeeze) / speed`.
- Tests: fold twice gives equal state; replay twice gives equal frames.

## What we do differently

- Our events carry no free text, no URLs, no field values (CAP-4). Mark8 stores rich text; we cannot.
- We partition by origin (`real/` vs `synthetic/`) and refuse to mix origins in one file.
- Mark8's headline claim is weak in its own recorded runs. We copy the method, not the claim: every number carries its split, n and interval.
