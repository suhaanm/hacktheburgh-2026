// The app icon (build/icon.png, exported from packages/design/brand/understudy-mark.svg by scripts/make-icons.mjs): the dock icon
// while the app runs from source or packaged. The .icns next to it is for the installer.
import fs from 'node:fs'
import path from 'node:path'

/** First existing icon file among the usual places (the app folder, then the packaged resources), or null. */
export function appIconPath(appPath: string, resourcesPath: string | undefined, exists: (p: string) => boolean = fs.existsSync): string | null {
  const candidates = [path.join(appPath, 'build', 'icon.png'), ...(resourcesPath ? [path.join(resourcesPath, 'icon.png'), path.join(resourcesPath, 'build', 'icon.png')] : [])]
  return candidates.find((p) => exists(p)) ?? null
}
