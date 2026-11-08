# Defaults and automation inside the safety layers (SHELL-WEB)

The owner asked (8 Nov, 00:15) for every toggle and state to be as automated as possible inside the safety layers. These are the defaults the shell, Home and first run choose, and the lines they never cross.

## Never automated (a real click is the only way in)

- A consent: capture, screen glances, voice, a connection. First run shows each as a card with Yes, Not now and Never of one size and one weight; none is pre-selected, none is answered by a timer, a key or a default. Unanswered means asked once, later, in context.
- An approval, a "Resume the run", a "Run while I'm away", anything irreversible or outward. No keystroke approves (`keys.test.ts`).
- A macOS permission: the page shows the state and offers Allow or Open System Settings; macOS shows its own prompt; the worker answers there.

## Automated, with the reason

| Default | Where | Reason |
|---|---|---|
| First run opens by itself on the first launch of the Knack app on this Mac, whatever identity the engine already has | `shouldStartFirstRun` (`inApp`) | A seeded example worker must not skip the role choice (owner, 00:45). A browser tab keeps the old rule. A deep link is never hijacked; a session that showed it once does not show it again (Back is not a trap). |
| The role pack's safe defaults are written when the consent screen is done: its tools, risky actions "never without me", short tone, gradual pace, its hours | `defaultAnswers` | Five questions the worker would answer the same way become zero clicks; all of it is editable in Your data. |
| "Not sure yet" and every Skip pick nothing; nothing is written | `NO_ROLE`, `skip` | Skipping must never cost the worker a choice they did not make. |
| The last consent answer advances to the next screen | `advance` | One click fewer; the cards still need real answers. |
| An unfinished first run resumes where it stopped | `parseProgress` | A closed window must not send the worker back to the start. Strict read: anything unexpected starts again from the top. |
| First run tells the shell it is open (`firstRun: true`) so the Hey Knack listener does not prompt at launch; it is told when first run ends | `wakeContext` | The first microphone prompt belongs to the moment the worker said Yes. |
| Admin view is remembered on this device; an admin lands on Firm | `viewAs.ts`, `App.tsx` | The owner's walk-through should not repeat the switch. It is a view, not a permission. |
| The sidebar badge, the Home row and the corner count read one number | `refreshNeedsBadge` | Three numbers that disagree look like a bug. |
| Home chooses its hero by fixed rules: a blocking approval or a safety pause first, then the best pointer | `blockingItem` | Something the worker must decide outranks something they could learn. |

## Click and word budgets for first run (reasons for the change)

The spec said three clicks and at most 50 words and 4 controls per first-run screen. The owner then asked for the role choice, three consents and a check that the voice and the pointer work. The budgets that follow are the smallest that keep every consent printed whole:

| Where | Clicks to Home with nothing skipped | Note |
|---|---|---|
| Browser tab | 3 | role, capture, Show my week |
| Knack app | 5 | role, capture, screen glances, voice, Show my week |
| With connection chips | one more | Continue, owner choice (D55) |

The consent screen carries one card per consent (title, the consent sentence printed whole, three buttons): about 30 words and 4 controls a card, so about 110 words and 10 controls with three cards. The budget for that one screen is therefore 120 words and 12 controls; the role screen (24 words, 6 controls with Skip) and the check screen stay within 50 and 8. `budgets.json` is the lead's file: the numbers above are the proposal.

## Not changed

Pinned views stay off by default (the sidebar's six rows are a measured budget); turning them on is one switch in Settings. The word "synthetic" is untouched until the owner's scope is confirmed.
