# Knack mark

Concept: a solid disc (the person doing the work) with a ring offset behind it (the understudy, shadowing). The same ring-with-offset appears as the annotation language on screen. The product name is Knack; the geometry did not change.

- `knack-mark.svg`: app icon on an ink tile (Dock, installer, README). The tile is for the Dock only, never inside the UI.
- `knack-glyph.svg`: no tile, follows `currentColor` (menu bar, monochrome favicon, print). The ring is drawn at 62% here; use this file only on single-colour surfaces.
- `knack-tray-template.svg`: macOS menu-bar template image (black on transparent; macOS recolours it). Export at 18 px and 36 px (`Template` in the file name).

In the UI the glyph is drawn by `apps/dashboard/src/components/Lockup.tsx` (`Glyph`, `Lockup`): disc in `--fg`, ring in `--accent`, both at full strength.

## Lockup rules (from `docs/knack-ux/knack-brand-sheet.svg`)

- Glyph, then the word "Knack" in the display face at 600. The disc is as tall as the capital K (the word is about 0.875 of the glyph's width). Gap between glyph and word: about one disc radius.
- Clear space: one K on every side.
- Sizes: sidebar glyph 20 px with the word at 17.5 px; first run glyph 56 px alone; corner pill glyph 14 px alone; favicon the `currentColor` glyph at 16 px. Minimums: glyph 12 px, lockup word 14 px.
- Never recolour the ring for status, add a gradient or glow, set the word in capitals, or put the mark inside a rounded tile in the UI.
- No tagline inside the app.

Colours are design tokens: ink `#0e1319`, bone `#e7ebf1`, accent light `#0a7c78`, accent dark `#4fd1c5`. The desktop track turns these into `icon.icns`, `trayTemplate.png` and `trayTemplate@2x.png` (`apps/desktop/scripts/make-icons.mjs` reads `knack-mark.svg` and `knack-tray-template.svg`).
