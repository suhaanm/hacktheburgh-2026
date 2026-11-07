# Alongside design language

A patient, dignified companion. Calm, trustworthy, never gamified or childish. Older adults find toy-like interfaces patronising, so there are no mascots, confetti, streaks or exclamation marks. Praise is specific and rare.

## Principles
1. **Plain and large.** Base text is 18px (20px at the big setting), Atkinson Hyperlegible, strong contrast, generous space. Every control is at least 44px (52px at the big setting).
2. **One thing at a time.** One step, one mark, one question. The dock never covers the centre of the screen.
3. **Honest about what it sees.** A red dot and the words "I can see your screen" show whenever the screen is being read. A large Stop is always visible.
4. **Help that fades, visibly.** The level chip shows four bars of support draining as the learner takes over. This is the product in one picture.
5. **Never colour alone.** State is also carried by shape, text, dashes and icons.

## Tokens (`src/renderer/design/tokens.css`)
- **Roles, not colours:** `bg`, `surface`, `surface-raised`, `surface-sunken`, `ink`, `ink-muted`, `ink-subtle`, `line`, `line-strong`, `focus`, `success|warn|danger-ink` and `-soft`, `accent`, `accent-soft`, `on-accent`.
- **Themes** are attributes on `<html>`: `data-theme="light|dark"` (follows the OS), `data-high-contrast="true"`, `data-dyslexia-font="true"`, `data-big-annotations="true"`, `data-persona="<id>"`. `applyDesignSettings()` sets them from `Settings`. Light is warm paper, dark is warm charcoal, high contrast is pure black on white or white on black with 3px borders and a 4px focus ring.
- **Persona accent:** `personas.ts` names a token (`accent-marcus`); `accent` resolves to it. Names are never in CSS or components.
- **Type scale:** 16, 18, 20, 24, 30, 40, 56px, multiplied by `--ui-scale` (1.12 with big annotations). OpenDyslexic replaces the face and widens letter and word spacing and line height. Fonts are bundled with `@fontsource`; nothing loads from the network.
- **Space and shape:** 4px base (4 to 64), radii 8, 14, 22, pill. Shadows are soft and warm; high contrast drops them for hard borders.
- **Stage legibility:** the dock is small, so the hero moment is also drawn large by the overlay (`levelChip` and `caption` in `annotation-style.ts`: 28px and 24px, times 1.6 with big marks). The dock chip, pill and captions are for the person at the keyboard, not the back of the room.
- **Motion:** 90 to 1100ms durations, one ease-out curve. With `prefers-reduced-motion` (or `data-motion="reduced"`) durations collapse and the orb, spinner and chip animations stop; state is still readable from the static shapes (ring weight, dashes, dots).

## Components
`PresenceOrb` (abstract orb, never a face: breathes while listening, ripples while speaking, dims and dots while thinking, dashed ring while connecting, red with "!" on error), `ListeningLight` + `MuteButton`, `LevelChip` (compact, default, hero; bars drain and the name slides on change; lock icon when locked), `Captions`, `StopButton`, `AgentTray`, `ConfirmModal` (two choices, real clicks only), `SkillStepper`, `ProgressView` (skills, hints-per-task bars, confidence line, all SVG), `SettingsPanel`, `Onboarding`, `ErrorBanner`. The dock adds `ProfileTab` ("About you"): the learner's own profile file, shown in plain sections with Forget per line or section, Add a line, a whole-file editor, a visible sharing status (carer sharing is OFF by default) and a two-step Delete everything. Every write carries the last-read revision, and a stale revision loads the latest without losing what the learner typed. Review all components in every state: `design/gallery.html`.

## Annotations on the user's screen (`annotation-style.ts`, for OVERLAY)
A mark must be visible on any wallpaper, so every line is three stacked strokes: a white **halo**, a dark ink **casing**, then the coloured **core**. The halo separates the mark from dark screens, the casing from light screens, giving at least 3:1 edge contrast on both. Cores are Okabe-Ito-derived hues (guide blue, success green, warn amber, danger vermilion) lightened to stay at least 3:1 on the casing; a test also checks they stay apart under protanopia, deuteranopia and tritanopia. Each tone has its own glyph and dash pattern, so colour is never the only cue. A missed step is a gentle amber, never red. `bigAnnotations` scales every size by 1.6, `highContrast` thickens lines and dims the screen more, `reducedMotion` stops pulses. The ghost cursor carries a visible "I will not click" tag and its press ring is a picture, not a click.

## Accessibility rules (enforced by `contrast.test.ts`)
- Body text 7:1, secondary text 4.5:1, control edges and focus ring 3:1, in all four themes and every persona accent. High-contrast text is 15:1 or better.
- Visible focus ring on everything; full keyboard operation; ARIA names for every control; `role="status"` and polite live regions for level changes and captions.
- Switches show ON and OFF as words. Segmented controls use radio semantics.
- `doItForMeAllowed` and `carerSharing` default to OFF and say so in plain words.
- The confirm dialog ignores synthetic clicks, Escape and the backdrop, and starts with focus on the dialog, not on a choice.

## Using it
`import '../design/styles'` once per window, call `followSystemTheme()` and `applyDesignSettings(settings, personaId)`. Components are presentational and props-driven. The dock (`src/renderer/dock`) wires them to `window.alongside`; `docs/design-preview/index.html` is a no-build interactive preview generated by `design/preview/build.mjs`.

## v3 premium pass (restraint, glass)

What changed (dock only; contracts untouched):
- Collapsed pill is 340 x 68: orb, one state word (Ready, Listening, Speaking, Muted, "Screen access needed"), four quiet help-level dots, and Stop only while a session or the demo runs. No grip, no bars icon, no level pill. The persona name and the long level name stay in aria-labels.
- Help level shows as four dots plus a plain word (Showing, Guided, Nudges, On my own; `LEVEL_SHORT`). `LEVEL_NAMES` are unchanged for state and aria.
- Expanded panel: header (orb, name, mute, collapse), three tabs (Chat, Progress, Settings), the conversation, one composer capsule. "About you" lives inside Settings, the easier-to-read font is in Settings, advanced settings stay under "More settings". The footer shows one quiet listening line and Stop only when something is running.
- Listening line is honest about Screen Recording: "Screen access needed" with an "Open settings" button.
- Showtime: the panel stays open while the demo runs, so its control strip sits above the header and never covers it.
- 380 px safety: chrome text scales with `--cs = min(--ui-scale, 1.15)`, content scales fully; dyslexia letter-spacing eased (0.01em, word 0.06em).
- Approval stays the one-line compact bar (text plus two small pill buttons).

Tokens added (end of components.css): `--v3-hair`, `--v3-hair-strong`, `--v3-hilite` (inner highlight), `--v3-chip`, `--v3-tabink`, `--v3-radius: 24px`, `--cs`. Glass uses `backdrop-filter: blur(var(--glass-blur)) saturate(1.8)` plus macOS `vibrancy: 'under-window'`; high contrast turns glass and highlights off.

Preview shots: `docs/design-shots/v3-*.png` (light, dark, glass, glassdark, dys = dyslexia + 1.5x, hc, onboarding, real-mac-panel, real-mac-pill). Regenerate with `src/renderer/design/shots.html` (vite build, then headless Chrome with `?theme=dark&glass=1&dys=1&scale=1.5&hc=1`). The older `design-preview/index.html` (vanilla JS) still shows the v2 look.

v3.1/v3.2 (15:30): glass is the default (`glass: true`, `glassOpacity: 0.4`, which gives a shell alpha of about 72%; cards stay at 94%+). It falls back to solid under high contrast, `prefers-reduced-transparency`, or when the platform has no vibrancy. Added an inner highlight sheen, 28 px radius, quieter "Talk to X" capsule, lighter composer. Expanded dock is now 360 x 580 and the pill 320 x 64, with smaller headlines and a denser conversation. Talk is the default at every launch: the chat Talk | Type switch is transient and never writes `textOnly`; a saved `textOnly` is cleared once on dock load.
