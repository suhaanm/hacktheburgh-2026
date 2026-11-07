// electron-builder configuration for the local, UNSIGNED Knack.app and dmg (apps/desktop/KNACK_BUILD.md has the commands and what a signed release still needs).
// The product name, bundle id and icon file names come from packages/design/brand/brand.json: change them there.
const path = require('node:path')
const brand = require('../../packages/design/brand/brand.json')

module.exports = {
  appId: brand.bundleId,
  productName: brand.name,
  copyright: 'Built for Hack the Burgh XIII',
  directories: { output: 'dist-app', buildResources: 'build' },
  // The built app (electron-vite output) and nothing else: no sources, no checks, no maps. The external packages (dotenv, zod, @google/genai) are added from node_modules.
  files: ['out/main/**', 'out/preload/**', 'out/renderer/**', 'package.json', '!out/knack-check/**', '!**/*.map'],
  asar: true,
  extraResources: [
    // The built dashboard, served by the app from app://knack (src/main/knack/app-protocol.ts); no web server, no remote content.
    { from: '../dashboard/dist', to: 'dashboard' },
    // The menu bar icons (tray.ts looks in resources/tray) and the app icon (app-icon.ts looks for resources/icon.png).
    { from: 'resources/tray', to: 'tray', filter: ['*.png'] },
    { from: 'build/icon.png', to: 'icon.png' },
    // Written by scripts/package-knack.mjs: where the repository is, so this local build can start the engine and the agent (KNACK_REPO overrides it).
    { from: 'build/knack-config.json', to: 'knack-config.json' },
    // The on-device "Hey Knack" listener (native/knack-wake, built by scripts/build-wake-helper.sh): wake/helper.ts looks in resources/knack-wake. Compile only; it fails closed.
    { from: 'resources/knack-wake', to: 'knack-wake' },
  ],
  electronDist: path.join(__dirname, 'node_modules/electron/dist'),
  electronVersion: require('./node_modules/electron/package.json').version,
  mac: {
    target: [{ target: 'dir', arch: ['arm64'] }, { target: 'dmg', arch: ['arm64'] }],
    category: 'public.app-category.productivity',
    icon: 'build/icon.icns',
    // Unsigned on purpose: a signed, notarised release needs the owner's Apple Developer ID (KNACK_BUILD.md).
    identity: null,
    hardenedRuntime: false,
    gatekeeperAssess: false,
    // The Dock icon is the app's, so the app is a normal one (not LSUIElement); the usage strings are what macOS shows when the app first asks.
    extendInfo: {
      NSMicrophoneUsageDescription: `${brand.name} listens only while you hold the talk key, and only if you turn voice on.`,
      NSSpeechRecognitionUsageDescription: `${brand.name} can recognise its wake phrase on this Mac, if you turn that on.`,
      NSAppleEventsUsageDescription: `${brand.name} can ask other apps to do steps for you when you allow it.`,
    },
  },
  dmg: { title: brand.name, icon: 'build/icon.icns', sign: false },
  // The hardened-runtime entitlements file is for a signed release; an unsigned local build has none.
  npmRebuild: false,
}
