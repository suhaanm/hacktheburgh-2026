# Capabilities and permissions

What a worker expects Knack to do, what each thing needs from macOS and from keys, what the worker sees when it is missing, and the one plain fix. The rule for all of it: a missing permission or key is never silence and never a dead switch. The worker gets a card (or a status line with a button) that says what is missing in plain words and opens the place that fixes it. Cards are in `apps/desktop/src/main/wake/texts.ts`; the tests that pin them are named in the last column.

macOS permissions are granted by the owner only, in System Settings, Privacy and Security. Knack never grants one and never asks for one before it is needed. Knack's own consent (a voice to a cloud model, a picture of the screen, a click) is separate from macOS permissions and is always a real mouse click on a card.

## The matrix

| What the worker expects | macOS permissions | Keys, models, extension | What the worker sees when it is missing | The fix, in the words the card uses | Test |
|---|---|---|---|---|---|
| Say "Hey Knack" | Microphone, then Speech Recognition (both asked natively by the listener the first time it listens, so the prompts belong to Knack). Dictation language installed for on-device speech | the listener binary (`scripts/build-wake-helper.sh`); no key; no live models | a card once per cause and a status line with a button in the menu bar and Settings: "Hey Knack needs the microphone." / "Hey Knack needs speech recognition." / "Hey Knack cannot listen yet." with System Settings | "Turn it on for Knack in System Settings, then switch Listen for Hey Knack off and on." For Dictation: "Turn on Dictation in System Settings, Keyboard." | controller.test "a blocked listener ...", helper.test |
| Hold to talk (Option-Space) | Microphone (the conversation's own capture) | Gemini key (from `.env`, main process), live models on, the first-wake voice card answered Yes | a card the moment the key is pressed: "Hey Knack heard you." with the reason; with no consent yet it shows the same two cards as the first wake, then "Talking is on." | live models: "Live voice needs live models. Turn them on in Settings." (Open Settings); microphone: "Live voice needs the microphone. Turn it on in System Settings."; limit: "Today's talking limit is reached. You can raise it in Settings." | controller.test "every capability ...", "the words always get an answer" |
| Knack speaks | none | model voice: Gemini key and live models; fixed lines: ElevenLabs key and `UNDERSTUDY_VOICE` | with no key the conversation does not open (the card above); fixed lines that cannot be spoken are simply written on the card or pill as well: every spoken line also exists as text | the same live-models card | texts, controller.test |
| Point at something in the Knack window | none (Knack reads its own page, no picture is taken) | live models for the conversation | the model says it cannot find it; if the Knack window is hidden or minimised there is nothing to point at | "Open Knack" from the Dock or menu bar, then ask again | point-ground.test "the Knack window" |
| Annotate a browser page | none | the Knack browser extension installed and switched on (its popup); the desktop's extension server | the model says it cannot find it. If Screen Recording is also off, the card below appears | install the extension and turn it on; the card says "Pointing in Knack or in a browser with the extension works without this." | point-ground.test "a browser tab with the extension" |
| Look at the screen to find a target anywhere | **Screen Recording** | live models, the second first-wake card answered Yes (a picture of the screen goes to a cloud model about every 5 seconds), not a private app or a password field | one card, at most once in ten minutes: "To find it, Knack must see your screen." with System Settings. Nothing is captured and nothing is sent while it is off | "Turn Knack on in System Settings, Screen Recording." | point-ground.test "the screen picture is the last resort", controller.test |
| Click for me | **Accessibility** (and Screen Recording for the target's picture), only after the first supervised test | the R1 record `rung_cleared.json`, the agent service route `/desktop/click`, `UNDERSTUDY_REAL_ACTUATOR` armed, pyobjc in the agent environment | before the test: Knack says "I will show you instead" and points, no card. After Allow, if it cannot run: "I could not click for you." or "Click for you needs Accessibility." / "...needs Screen Recording." with System Settings | "Turn Knack on in System Settings, Accessibility. For now I will show you instead." | click-machine.test, controller.test "an allowed click that cannot run" |
| Run a routine while I am away | none for sandbox and browser routines; Accessibility and Screen Recording for a routine on the real desktop, with the routine's own consent | the agent service running (Knack starts it), live models for model-driven steps, Knack open and the Mac awake | the routine does not start; the quit sheet already says "Routines set to run while you are away will not run until you open Knack"; Needs you holds what it could not do | open Knack; set Open at login; keep the Mac awake | `knack/quit-guard.ts` (the quit sheet); agent tests |

"Never silence" has one honest exception: a spoken fixed line is quiet when ElevenLabs is not set up. The same words are on a card or the pill, so nothing is lost.

## First run: the order of permissions

The order is fixed by who asks, and the worker is told one thing at a time.

1. **Microphone.** On the set-up step "Turn on Hey Knack" the worker clicks "Turn on". The shell calls `window.knackShell.wake.arm()`, which starts the listener, which asks macOS for the microphone. Until `arm()` the listener stays off while set-up is showing (the shell reports `wake.context({ firstRun: true })` when set-up starts), so no prompt appears at launch out of context. Words on the step: title "Turn on Hey Knack", body "Knack listens on this Mac only. macOS will ask for the microphone, then speech recognition.", buttons "Turn on" and "Not now".
2. **Speech Recognition.** Asked by the same listener straight after the microphone is granted, with no click in between. Nothing for the shell to do; if either is refused the listener ends with a closed code, a card appears once, and `wake.state()` returns `fix: 'microphone'` or `'speech'` for a button beside the line in Settings.
3. **Screen Recording.** Only when the worker turns on screen glances or answers Yes to "Knack may look at your screen while we talk" and then asks Knack to find something that is not in Knack or in a browser tab with the extension. Words: "To find things anywhere on your screen, Knack needs Screen Recording. Pointing in Knack or in your browser does not." Button "Open System Settings".
4. **Accessibility.** Only for click for me, and only after the first supervised test has passed. Words: "To click for you, Knack needs Accessibility. It will always ask first, with Allow once." Pointing never needs it.

Not asked by Knack at first run, ever: Input Monitoring, Automation, Full Disk Access.

## First run: the Try it step

The last step of first run, after the permissions. The shell reports `wake.context({ firstRun: true })` from the start of set-up to its end, so the model knows to be brief and kind (the context packet says `first_run=yes`; the screen id is `first_run` while the worker is on those screens).

Sequence:

1. Screen: title "Say Hey Knack" (3 words); one line under it, "Then say: show me where the Needs you list is." (10 words); a quiet "Listening" status when `wake.state().listening`; one button, "Skip". If the listener is blocked the step shows the status line and its System Settings button instead (`wake.state().line` and `.fix`).
2. The worker says "Hey Knack". The chime plays; the pill says Listening. The first time ever, the two cards appear (Talk with Knack?, then the screen card), each needing a real click; Not now on the screen card is fine here, because pointing in the Knack window needs no picture.
3. Knack's first words, once, fixed: "Hi, I am Knack. Try saying: show me where the Needs you list is." (the code sends this as the model's opening turn, so the words are ours even though the voice is the model's; the model is told to say exactly this and then wait).
4. The worker says "show me where the Needs you list is". The model calls `point_at` with the description "Needs you". Knack finds the sidebar row by its name in the Knack window (no picture, no permission), draws the ring and moves the ghost cursor to it, and the model says: "That is the Needs you list." Then it says they can ask for help or say goodbye.
5. The step is done when `wake.state().welcomed` turns true (the first conversation started), or when the worker clicks Continue. The Continue button is always there.

For Track A: the ring overlay is hidden while the Knack window is focused (docs/knack-ux/08-window-states.md). During first run the voice ring (annotation id `point-voice`, with `point-voice-ghost`) must still draw on the Knack window, or the Try it step shows nothing. `tryRing` can call the same pointing path; the voice conversation does it through `point_at` with no help from the shell.

## Packaged Knack.app

What works from a packaged `Knack.app`:

- The key. `apps/desktop/src/main/knack/env.ts` loads the repository's `.env` into the main process (the repository is found through `Resources/knack-config.json`, `repo`). The Gemini key never leaves the main process: it is sent in one header to mint a one-use, ten-minute ephemeral token locked to the configured model (`live/token.ts`), and the websocket uses only that token. The renderer that owns the speaker and microphone gets audio over IPC and nothing else; `live/static.test.ts` pins that no renderer source has the key, a token minter, the Gemini host or a websocket, and that no log line carries content.
- The listener: `resolveHelperPath` looks in `process.resourcesPath/knack-wake` first, so the binary only needs to be copied into `Contents/Resources` (an electron-builder `extraResources` entry; there is no electron-builder config in the repository yet).
- The cards, the pill, the menu bar rows, the consent cards, the Knack window pointing, the browser-extension pointing.

What only works from the repository checkout today:

- The key itself: it lives in the repository's `.env`; without the repository on disk the packaged app has no key, so live voice shows "Live voice needs live models." A key in the app's own data folder is not supported yet.
- The services: the engine and agent are started from `services/` (Python, `uv`) and the sandbox sites from the repository; a packaged app without the repository cannot start them.
- The data folder: kill file, service token, `rung_cleared.json` and the owner tokens live under the repository's `data/`.
- The listener binary until it is built with `scripts/build-wake-helper.sh` and copied into the app.
- The macOS usage strings: the packaged app's Info.plist needs `NSMicrophoneUsageDescription` and `NSSpeechRecognitionUsageDescription` (the exact words are in 09-wake-voice.md) and the signed listener needs the `com.apple.security.device.audio-input` entitlement under the hardened runtime. From `electron-vite dev` the responsible process is Electron.app, whose Info.plist has no speech string; the listener carries its own embedded copy, and whether macOS shows the prompt cleanly in that case is only known at the owner's first launch.
- Screen Recording and Accessibility are granted per app: a packaged Knack.app and a dev Electron are different apps to macOS, so a grant made for one does not carry over.
