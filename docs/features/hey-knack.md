# Hey Knack: voice that points

> Say 'Hey Knack'. Knack speaks, points with a ring and a ghost cursor, and clicks only after a real click on an Allow card.

**Capability:** Voice and Hey Knack · **Status:** built · **Master document:** `docs/PITCH_FEATURES.md` · **Index:** `docs/features/index.md`

This page covers Hey Knack: an on-device wake phrase, Voice guidance and 'do it for me' behind a click.

## Hey Knack: an on-device wake phrase

**Status:** built (code and tests on main; not run with a real microphone yet; docs/knack-ux/09-wake-voice.md has not landed) · **Page:** `docs/features/hey-knack.md` · **Targets:** G-Research

### What it does

Knack is woken by the words 'hey knack'. Listening is on by default (the owner's decision), but it happens on the Mac, prints only a closed 'heard' event, and stores no audio and no transcript.

### How it works

A native helper uses macOS on-device speech recognition. If on-device recognition is not available it turns itself off with one plain line and never falls back to server recognition. The phrase is matched by a closed accept list: a greeting (hey, hay, heya) at the start of an utterance, then the name 'knack' (close spellings only at the end of an utterance or before a request word; 'knock' only before a request word). 'Hey Jack', 'a knack for it' and 'hey knock it off' are rejected. The listener is dormant, with the microphone released, when the switch is off, the screen is locked or the Mac asleep, Stop everything is engaged, Do Not Disturb, a call, a meeting or a screen share is on, a Live conversation or an agent run is under way, or the worker is away. macOS still asks for Microphone and Speech Recognition, which only the owner can grant.

### Where to see it

Menu bar (listening indicator and the Listen for Hey Knack switch); first launch asks for the two macOS permissions. The corner pill shows 'Listening' after the wake.

### Demo moment

Say 'Hey Knack'. The pill shows 'Listening', a soft cue plays, and Knack answers by voice. Try 'hey Jack': nothing happens.

### Evidence and its label

| What | Label | Source |
|---|---|---|
| The matcher is pinned by tests over more than 300 distinct ordinary sentences and more than 40 accepted variants: on the held-out set exactly one false accept ('Hey nack, nack, nack, that is all I hear from this network') and no misses; over both sets the Wilson upper bound is below 0.02 for false accepts and below 0.07 for misses | offline tests on text strings, not a microphone | `apps/desktop/src/main/wake/corpus.test.ts` |
| A line-for-line Swift port of the matcher is checked against the TypeScript specification over the whole corpus | offline tests | `apps/desktop/src/main/wake/matching.ts (header)` |

### Honest limit

No real microphone has been used yet; the rates above describe the matching logic on strings, not how often a real recogniser and microphone trigger it. The phrase is an on-device detector's, so an unusual accent or a noisy room is untested. Earlier documents (docs/FLAGS.md, docs/FEATURE_CATALOGUE.md) still say there is no always-listening microphone; D52 supersedes that for Hey Knack.

### Hackathon target

- **G-Research (make the invisible visible)**: nothing recorded; the invisible listener is made visible by an indicator and a switch

## Voice guidance and 'do it for me' behind a click

**Status:** built (the click path fails closed until the first supervised real-click test has passed) · **Page:** `docs/features/hey-knack.md` · **Targets:** Wordsmith, G-Research

### What it does

After the wake, a live voice conversation starts. Knack speaks while it guides, shows the place with a ring and a ghost cursor, and never clicks for you on voice alone.

### How it works

The wake starts the Live voice session (Gemini). Screen frames go only through the consent card (Yes, Not now, Never) and the image gate. Its tools are a closed set: point_at (ring and ghost cursor) and do_it_for_me. The second fails closed until the owner has completed the first supervised real-click test; a persisted record written only by that test turns it on. Even then, voice alone is never consent: a real mouse click on an Allow card issues the one-time token and the per-run permit. It is never unattended, never a purchase, never a real account. A typed context packet (closed grammar, freshness limits) tells the session what is on the screen, what waits for approval and what the coach is doing. Holding Option-Space talks.

### Where to see it

Corner pill (voice state and End), the ring on the real screen, the Allow card.

### Demo moment

Ask: 'Where do I see what needs me?' A ring and a ghost cursor show Needs you; Knack does not click. Say 'do it for me': it says it will show you instead, because the first supervised test is pending.

### Evidence and its label

| What | Label | Source |
|---|---|---|
| The click state machine is covered by tests: no tool call does anything without a Live session; with no rung record the answer is always 'first supervised test pending' and no card is shown; the card's Allow counts only as a real mouse click (voice, key or timer is ignored); Stop everything wins from any state | offline tests | `apps/desktop/src/main/wake/click-machine.test.ts` |

### Honest limit

Not run with a microphone, a Live session or a real click. The 'do it for me' path stays off until the first real-click rung is reported with the owner present. Voice quality and latency are not measured.

### Hackathon target

- **Wordsmith (most complicated end-to-end browser-use workflow)**: a voice-guided browser workflow with the click gated by consent
- **G-Research (make the invisible visible)**: the next step made visible and spoken

## 30-second spoken script

> Say 'hey knack'. A small helper on your Mac, using Apple's on-device speech, listens for that phrase and nothing else. It stores no audio and no words. When it hears you, Knack speaks, and shows you where to click with a ring and a ghost cursor. It will not click for you on a voice command. Only a real mouse click on an Allow card can do that, and even that is switched off until a supervised test has passed.

## Slide bullets

- Wake phrase 'hey knack', matched on the Mac by a closed accept list.
- Prints only 'heard'; no audio, no transcript; fails closed if on-device speech is missing.
- Dormant on a call, a meeting, a screen share, a lock, Stop everything.
- Guides with ring, ghost cursor and speech; never clicks on voice alone.
- Built and tested; not yet run with a real microphone.

## Sources

- `docs/DECISIONS.md (D52)`
- `docs/FIRST_LAUNCH.md`
- `apps/desktop/src/main/wake/matching.ts`
- `apps/desktop/src/main/wake/guards.ts`
- `apps/desktop/src/main/wake/click-machine.ts`
- `apps/desktop/src/main/wake/corpus.test.ts`
- `docs/knack-ux/09-wake-voice.md (landing, branch worktree-agent-a86cc292e454adbb6)`

## Related pages

`awareness-glances.md`, `screen-annotations.md`, `computer-use.md`, `models-and-routing.md`
