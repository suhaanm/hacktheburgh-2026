# Knack mark

Concept: a solid disc (the person doing the work) with a ring offset behind it (the understudy, shadowing). The same ring-with-offset appears as the annotation language on screen.

- `knack-mark.svg`: app icon on an ink tile (dock, installer, README, browser tab).
- `knack-glyph.svg`: no tile, follows `currentColor` (dashboard wordmark).
- `knack-tray-template.svg`: macOS menu-bar template image (black on transparent; macOS recolours it). Export at 18 px and 36 px (`Template` in the file name).
- `brand.json`: the one source of truth for the product name, the bundle id, the app's own address (`app://knack`) and the three file names above. `apps/desktop/src/shared/brand.ts`, `apps/dashboard/src/brand.ts`, the icon script (`apps/desktop/scripts/make-icons.mjs`), the dashboard's `index.html` (through `vite.brand.ts`) and the packaging config (`apps/desktop/electron-builder.config.cjs`) all read it.

To rename the product, edit `name` in `brand.json`. To change the logo, replace the three SVG files (keep the file names, or change `files` in `brand.json`) and run `cd apps/desktop && npm run icons`. `apps/desktop/tests/brand-guard.test.ts` fails if a string a person can read still carries an old name.

Colours are design tokens: ink `#0e1319`, bone `#e7ebf1`, accent (dark) `#4fd1c5`. The desktop track turns these into `icon.icns`, `trayTemplate.png` and `trayTemplate@2x.png`.
