// The product name and brand files, from one place: packages/design/brand/brand.json (the dashboard reads the same file through
// apps/dashboard/src/brand.ts). Every window title, menu, tooltip, notification, About box, Dock name and installer name comes from here, so
// renaming the product is one edit, and tests/brand-guard.test.ts fails when a visible string still carries an old name.
import brand from '../../../../packages/design/brand/brand.json'

export const APP_NAME: string = brand.name
/** macOS bundle identifier and electron-builder appId. */
export const BUNDLE_ID: string = brand.bundleId

/** The app's own address for the dashboard in production: app://knack (see src/main/knack/app-protocol.ts). */
export const APP_SCHEME: string = brand.protocol.scheme
export const APP_HOST: string = brand.protocol.host
export const APP_ORIGIN = `${APP_SCHEME}://${APP_HOST}`

/** Brand source files, relative to the repository root. Replacing a file replaces the icon everywhere (run `npm run icons`). */
export const BRAND_DIR = 'packages/design/brand'
export const BRAND_FILES: { readonly mark: string; readonly glyph: string; readonly trayTemplate: string } = brand.files
export const BRAND_ASSET_PATHS = {
  mark: `${BRAND_DIR}/${BRAND_FILES.mark}`,
  glyph: `${BRAND_DIR}/${BRAND_FILES.glyph}`,
  trayTemplate: `${BRAND_DIR}/${BRAND_FILES.trayTemplate}`,
} as const

/** Exported icons, relative to apps/desktop (made from the brand files by scripts/make-icons.mjs). */
export const ICON_PATHS = {
  icns: 'build/icon.icns',
  png: 'build/icon.png',
  trayTemplate: 'resources/tray/trayTemplate.png',
} as const

/** The titles of our own windows. The side panel and the overlay are not the main window, so they say what they are. */
export const WINDOW_TITLES = {
  main: APP_NAME,
  panel: `${APP_NAME} panel`,
  overlay: `${APP_NAME} overlay`,
  cue: `${APP_NAME} Cue`,
  hud: APP_NAME,
  pill: `${APP_NAME} status`,
} as const

/** "<label> · Knack": the window and document title shape. */
export const titled = (label: string): string => `${label} · ${APP_NAME}`
