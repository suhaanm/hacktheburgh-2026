# Hey Knack: voice that points

> Say 'Hey Knack'. Knack speaks, points with a ring and a ghost cursor, and clicks only after a real click on an Allow card.

**Capability:** Voice and Hey Knack · **Status:** built · **Master document:** `docs/PITCH_FEATURES.md` · **Index:** `docs/features/index.md`

This page covers Hey Knack: an on-device wake phrase, Voice guidance and 'do it for me' behind a click.

## Hey Knack: an on-device wake phrase

**Status:** built (code and tests are built and merged; not run with a real microphone yet; the listener helper ships inside Knack.app and the first launch needs the owner's Microphone and Speech Recognition grants and an installed on-device dictation language) · **Page:** `docs/features/hey-knack.md` · **Targets:** G-Research

### What it does

Knack is woken by the words 'hey knack'. Listening is on by default (the owner's decision), but it happens on the Mac, prints only a closed 'heard' event, and stores no audio and no transcript.

### How it works

A native helper uses macOS on-device speech recognition. If on-device recognition is not available it turns itself off with one plain line and never falls back to server recognition. The phrase is matched by a closed accept list: a greeting (hey, hay, heya) at the start of an utterance, then the name 'knack' (close spellings only at the end of an utterance or before a request word; 'knock' only before a request word). 'Hey Jack', 'a knack for it' and 'hey knock it off' are rejected. The listener is dormant, with the microphone released, when the switch is off, the screen is locked or the Mac asleep, Stop everything is engaged, Do Not Disturb, a call, a meeting or a screen share is on, a Live conversation or an agent run is under way, or the worker is away. macOS still asks for Microphone and Speech Recognition, which only the owner can grant. A missing permission or key is never silence: the worker gets a card or a status line in plain words with a button that opens the fix (docs/knack-ux/capabilities-and-permissions.md).

**What is different.** Recognition happens in a native helper that prints only a closed 'heard' event, so no text crosses into the app, and it fails closed instead of using server recognition.

### Where to see it

Menu bar: a status row ('Listening for Hey Knack. Stays on this Mac, nothing stored.') and a 'Listen for Hey Knack' switch; macOS itself draws its orange microphone indicator whenever any process uses the microphone, which Knack cannot hide. First launch asks for the two macOS permissions. The corner pill shows 'Listening' after the wake.

### Demo moment

Say 'Hey Knack'. The pill shows 'Listening', a soft cue plays, and Knack answers by voice. Try 'hey Jack': nothing happens.

### Evidence and its label

| What | Label | Source |
|---|---|---|
| The matcher is pinned by tests over more than 300 distinct ordinary sentences and more than 40 accepted variants: on the held-out set exactly one false accept ('Hey nack, nack, nack, that is all I hear from this network') and no misses; over both sets the Wilson upper bound is below 0.02 for false accepts and below 0.07 for misses | offline tests on text strings, not a microphone | `apps/desktop/src/main/wake/corpus.test.ts` |
| Measured on text strings: development set 0 false accepts in 183 ordinary sentences and 0 misses in 31 variants (the matcher was tuned on it); held-out set, written after the matcher was frozen, 1 false accept in 159 (0.63%, Wilson 0.11 to 3.48%) and 0 misses in 25 variants (Wilson 0 to 13.3%); both together 1 in 342 (0.29%, Wilson 0.05 to 1.64%) and 0 misses in 56 (Wilson 0 to 6.4%) | offline strings, not audio and not a microphone | `docs/knack-ux/09-wake-voice.md` |
| A line-for-line Swift port of the matcher agrees with the TypeScript specification over the whole corpus | offline tests | `apps/desktop/src/main/wake/matching.ts (header)` |

### Honest limit

No real microphone has been used yet; the rates above describe the matching logic on strings, not how often a real recogniser and microphone trigger it (that needs the owner's first launch and a day of use). The one held-out false accept is 'Hey nack, nack, nack, that is all I hear from this network'; it was left and pinned in a test rather than tuned away. An unusual accent or a noisy room is untested. Earlier documents (docs/FLAGS.md, docs/FEATURE_CATALOGUE.md) still say there is no always-listening microphone; D52 supersedes that for Hey Knack.

### Hackathon target

- **G-Research (make the invisible visible)**: nothing recorded; the invisible listener is made visible by an indicator and a switch

## Voice guidance and 'do it for me' behind a click

**Status:** built (the click path fails closed until the first supervised real-click test has passed) · **Page:** `docs/features/hey-knack.md` · **Targets:** Wordsmith, G-Research

### What it does

After the wake, a live voice conversation starts. Knack speaks while it guides, shows the place with a ring and a ghost cursor, and never clicks for you on voice alone.

### How it works

The wake stops the listener (releasing the microphone) and starts the Live voice conversation (Gemini), hands-free, with a soft chime. Two first-wake cards ask once, each with Yes, Not now and Never of equal weight: whether your voice may go to a cloud voice model while you talk, and whether a small picture of the screen may go about every 5 seconds; only a real mouse click answers a card. Frames go through the image gate and the ledger: never from a denylisted app or over secure input, never unattended, never stored. The conversation is bounded: started by the worker, five minutes at most, a spending cap, and a quiet half minute ends it. The model's tools are a closed set: point_at (ring and ghost cursor), clear, show_step, ask_choice, end_session and do_it_for_me. The last fails closed until the owner has completed the first supervised real-click test; a record written only by that test turns it on. Even then, voice alone is never consent: a card 'Click for you?' with Allow once or Cancel needs a real mouse click, a 20-second timer means Cancel, and the click goes through the one-time token, the per-run permit, the countdown and every real-actuator guard. It is never unattended, never a purchase, never a real account. A typed context packet (closed grammar, freshness limits; a test feeds it hostile strings) tells the session what is on the screen, what waits for approval and what the coach is doing. Holding Option-Space talks. When a task service is bound, the Live tools also include start_task, which hands the worker's request to that service: it is declared only when code can answer it, the model is told that it never starts anything and must say what the answer tells it (for example, tap Allow on the card), and the answer is a closed record, never a summary. The task service is on main (see the open-ended tasks page); the box to type a task is not.

**What is different.** Voice can ask but never approve: the click is a separate consent, a real mouse click on a card, and the whole path stays closed until a supervised test has passed.

### Where to see it

Corner pill (voice state and End), the ring on the real screen, the Allow card.

### Demo moment

Ask: 'Where do I see what needs me?' A ring and a ghost cursor show Needs you; Knack does not click. Say 'do it for me': it says it will show you instead, because the first supervised test is pending.

### Evidence and its label

| What | Label | Source |
|---|---|---|
| The click state machine is covered by tests: no tool call does anything without a Live session; with no rung record the answer is always 'first supervised test pending' and no card is shown; the card's Allow counts only as a real mouse click (voice, key or timer is ignored); Stop everything wins from any state | offline tests | `apps/desktop/src/main/wake/click-machine.test.ts` |

### Honest limit

Not run with a microphone, a Live session or a real click. The 'do it for me' path stays off until the first real-click rung is reported with the owner present, and the agent-service route it needs (POST /desktop/click) is not built (decision D56): the desktop answers 'route missing' and clicks nothing, and Knack says it will show you instead. The model's speech inside a conversation is free-form audio; every other spoken line in Knack is fixed. Voice quality and latency are not measured. The context packet does not yet carry the week's top Home insight (no screen reports it, gap G1), so the voice cannot say what the insight is; the routine is reported only for a run started with Run now; and the help level and the Needs-you item kinds are not in the packet.

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
- `docs/knack-ux/09-wake-voice.md`
- `docs/knack-ux/capabilities-and-permissions.md`
- `apps/desktop/src/main/live/tools.ts`
- `docs/DECISIONS.md (D56, item 4 and 5)`

## Related pages

`awareness-glances.md`, `screen-annotations.md`, `computer-use.md`, `models-and-routing.md`
