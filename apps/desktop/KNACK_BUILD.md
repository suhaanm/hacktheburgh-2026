# Building Knack.app

Knack.app is the Electron app in this folder: the dashboard in its own window, a menu-bar item and the corner pill, with the engine and the agent started by the app itself. The product name, bundle id and icon file names are in one place, `packages/design/brand/brand.json`.

## Build the unsigned local app and dmg

```
cd apps/desktop
npm install                          # once; installs electron-builder (pinned 26.18.0)
../../scripts/heavy.sh npm run package
```

`npm run package` (`scripts/package-knack.mjs`) does four things and never launches the app:

1. builds the dashboard (`apps/dashboard`, `npm run build`, which type-checks first) into `apps/dashboard/dist`;
2. builds the desktop app (`electron-vite build`) into `apps/desktop/out`;
3. writes `build/knack-config.json` with the path of this repository (the built app finds the engine and the agent from it; set `KNACK_REPO` to point it somewhere else);
4. runs electron-builder (`electron-builder.config.cjs`, identity `null`, so nothing is signed) and writes **`dist-app/mac-arm64/Knack.app`** (about 300 MB unpacked) and **`dist-app/Knack-0.1.0-arm64.dmg`** (about 130 MB). `dist-app/` and `build/knack-config.json` are not committed.

First launch of an unsigned app: macOS refuses a double-click on a downloaded or copied unsigned app. Right-click the app, choose Open, and confirm once, or run `xattr -dr com.apple.quarantine dist-app/mac-arm64/Knack.app`. The app was built on this Mac, so it normally opens without that.

## What the built app does when you open it

- a window at 80% by 84% of the work area (about 1152 by 735 on a 1440 by 900 display), remembered per display; the red button and Command-W hide it, the Dock icon brings it back, Command-Q quits (a sheet asks first while something is running);
- it checks the engine (7700) and the agent (7710). If both answer it uses them and never stops them. If not it starts them as its own children, **live** (real Gemini models, `data/live-home` and `data/live-data`, seeded once) when `GEMINI_API_KEY` is in the environment or the repository's `.env`, and the models boot check passes; otherwise **example data** (`data/demo-home`, `data/demo-data`) with the one line "Running with example data". On quit it stops only the processes it started. Logs go to `data/logs/knack-<service>.log`;
- it needs `uv` (on `PATH`, `/opt/homebrew/bin`, `/usr/local/bin`, `~/.local/bin` or `~/.cargo/bin`) to start the Python services. Without it the window says so, plainly, with one Try again button.

Environment: `KNACK_REPO` (the repository, if the built app was moved), `KNACK_LIVE=0` (force example data) or `1` (ask for live), `KNACK_SHELL=0` (the old behaviour: no main window, no Dock icon changes), `KNACK_NO_SINGLE_INSTANCE=1`, `KNACK_SITES=0` (do not start the sandbox calculator sites, which bind fixed ports 7801 to 7803).

Two hidden end-to-end runs of the real app exist (nothing shown, free ports): `scripts/electron-lock.sh KNACK node scripts/knack-e2e.mjs` (stand-in services, the pill, the cards, a clean quit) and the same with `--real-services` (the app starts the real engine and agent itself, quitting stops exactly those two).

## The hidden check (no window, no Dock icon, nothing on the screen)

```
cd apps/desktop
scripts/electron-lock.sh KNACK node scripts/knack-check.mjs --out /tmp/knack-pictures
```

Builds the app and the dashboard into `out/knack-check`, then runs `src/main/knack/check-main.ts` under Electron with the activation policy "prohibited", stand-in services on private ports and a private data folder. It checks the dashboard served from `app://knack`, the token-adding proxy, the window size, the corner column (bottom-right, 16 px, card above pill, secure-input hold, Review, done, error, voice, Stopped, resume), and writes a picture of each page (the page's own pixels, never the screen).

## What a signed release still needs (owner only)

1. An Apple Developer ID Application certificate in the keychain (`CSC_NAME` or `CSC_LINK`/`CSC_KEY_PASSWORD`), and in `electron-builder.config.cjs` replace `identity: null` and `hardenedRuntime: false` with `hardenedRuntime: true`, `gatekeeperAssess: true` and an entitlements file (`com.apple.security.cs.allow-jit` for V8, `com.apple.security.device.audio-input` for the microphone, and the Apple Events entitlement for driving other apps).
2. Notarisation: `APPLE_ID`, `APPLE_APP_SPECIFIC_PASSWORD` and `APPLE_TEAM_ID` (or an App Store Connect API key), and `notarize` set in the mac config. electron-builder submits and staples.
3. Privacy usage strings (microphone, speech recognition, Apple Events) are already in the Info.plist from `mac.extendInfo`; Accessibility and Screen Recording are granted by the owner in System Settings the first time Knack must point at or act on the screen (a human-only step).
4. The app must find the engine and the agent on another Mac: set `KNACK_REPO`, or bundle the services (not done: this build is for the machine the repository is on).

## What the packaging step does to the bundle (`scripts/after-pack.cjs`, run by electron-builder before the dmg)

1. It deletes Electron's generic camera, Bluetooth and system-audio usage strings from the bundle's Info.plist (Knack asks for none of them). The microphone, speech recognition and Apple Events strings Knack uses stay (`tests/after-pack.test.ts` pins both).
2. It seals the bundle again with an ad-hoc signature (`codesign --sign -`: no identity, no Apple account). The stock Electron signature names the app `Electron` and binds no Info.plist, so `codesign --verify` fails; sealed again it is `app.knack.desktop` with its Info.plist bound, which is what macOS reads for the microphone and speech prompts and for the permission list.

Neither step is fatal: if one fails the build says so and the app is as it was. Check a build with `codesign --verify --deep --strict dist-app/mac-arm64/Knack.app` (exit 0) and `plutil -p dist-app/mac-arm64/Knack.app/Contents/Info.plist | grep UsageDescription`.

## Known limits

- Build from a normal checkout (a real `node_modules` in `apps/desktop`). A worktree whose `node_modules` is a **symlink** to another checkout's makes electron-builder miss the transitive dependencies of `@google/genai` (`google-auth-library`, `ws`, `protobufjs`, `p-retry`) and of React: the asar then has about 980 entries instead of 1492 and the live models fail at run time. `asar list dist-app/mac-arm64/Knack.app/Contents/Resources/app.asar | wc -l` should say about 1490.

- In development (`npm run dev`) the Dock label and the macOS permission lists show Electron: only a packaged build carries the Knack name there.
- `build/knack-config.json` records the repository path at build time; a build made inside a git worktree points at that worktree unless `KNACK_BAKE_REPO=/path/to/the/main/checkout` is set when packaging.
- Quitting with a force-kill (not Command-Q) can leave the services it started running; start Knack again (it reuses them) or stop them with `scripts/stop.sh`.
