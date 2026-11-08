// The electron-builder afterPack step of the unsigned Knack.app (electron-builder.config.cjs): runs after the bundle is assembled and before the dmg is made.
//  1. strips the generic usage strings Electron's stock Info.plist carries for things Knack never asks for (camera, Bluetooth, system audio capture), so no macOS prompt could ever say
//     "This app needs access to the camera"; the strings Knack needs stay (microphone, speech recognition, Apple Events);
//  2. seals the bundle again with an ad-hoc signature (no identity, no Apple account): the stock signature names the app "Electron" and binds no Info.plist or resources, so
//     `codesign --verify` fails; sealed again it is app.knack.desktop with its Info.plist bound.
// Neither step is fatal: a failure is a warning and the app is as it was. Step 1 must come first (a changed Info.plist breaks the seal). macOS only.
const { execFileSync } = require('node:child_process')
const fs = require('node:fs')
const path = require('node:path')

/** Usage strings Electron's Info.plist has by default and Knack does not use. */
const GENERIC_USAGE_KEYS = ['NSCameraUsageDescription', 'NSBluetoothAlwaysUsageDescription', 'NSBluetoothPeripheralUsageDescription', 'NSAudioCaptureUsageDescription']
/** What Knack asks macOS for, with its own words (mac.extendInfo in electron-builder.config.cjs): never removed. */
const NEEDED_USAGE_KEYS = ['NSMicrophoneUsageDescription', 'NSSpeechRecognitionUsageDescription', 'NSAppleEventsUsageDescription']

/** Deletes each generic key that is present from the plist at `plist` (PlistBuddy). Returns the keys removed. Never throws. */
function stripGenericUsage(plist, run = (cmd, args) => execFileSync(cmd, args, { stdio: ['ignore', 'pipe', 'pipe'] }), keys = GENERIC_USAGE_KEYS) {
  const removed = []
  for (const key of keys) {
    try {
      run('/usr/libexec/PlistBuddy', ['-c', `Print :${key}`, plist]) // throws when the key is absent
      run('/usr/libexec/PlistBuddy', ['-c', `Delete :${key}`, plist])
      removed.push(key)
    } catch {
      /* absent, or PlistBuddy could not run: leave it */
    }
  }
  return removed
}

async function afterPack(context) {
  if (context.electronPlatformName !== 'darwin') return
  const app = path.join(context.appOutDir, `${context.packager.appInfo.productFilename}.app`)
  const plist = path.join(app, 'Contents/Info.plist')
  try {
    if (fs.existsSync(plist)) {
      const removed = stripGenericUsage(plist)
      if (removed.length) console.log(`removed generic usage strings from Info.plist: ${removed.join(', ')}`)
    }
  } catch (err) {
    console.warn(`usage strings left as they were: ${err instanceof Error ? err.message : String(err)}`)
  }
  try {
    execFileSync('codesign', ['--force', '--deep', '--sign', '-', app], { stdio: 'inherit' })
  } catch (err) {
    console.warn(`ad-hoc seal skipped: ${err instanceof Error ? err.message : String(err)}`)
  }
}

module.exports = afterPack
module.exports.stripGenericUsage = stripGenericUsage
module.exports.GENERIC_USAGE_KEYS = GENERIC_USAGE_KEYS
module.exports.NEEDED_USAGE_KEYS = NEEDED_USAGE_KEYS
