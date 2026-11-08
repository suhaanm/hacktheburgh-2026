import { execFileSync } from 'node:child_process'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { createRequire } from 'node:module'
import { describe, expect, it } from 'vitest'

const require = createRequire(import.meta.url)
const afterPack = require('../scripts/after-pack.cjs') as ((c: unknown) => Promise<void>) & { stripGenericUsage: (plist: string, run?: (cmd: string, args: string[]) => unknown, keys?: string[]) => string[]; GENERIC_USAGE_KEYS: string[]; NEEDED_USAGE_KEYS: string[] }
const builder = require('../electron-builder.config.cjs') as { afterPack: unknown; mac: { extendInfo: Record<string, string> } }

describe('the afterPack step of the unsigned Knack.app', () => {
  it('is the step the packager runs, and removes nothing Knack needs', () => {
    expect(builder.afterPack).toBe(afterPack)
    for (const key of afterPack.NEEDED_USAGE_KEYS) {
      expect(afterPack.GENERIC_USAGE_KEYS).not.toContain(key)
      expect(builder.mac.extendInfo[key]).toMatch(/Knack/) // the strings Knack asks with are its own words
    }
    for (const key of afterPack.GENERIC_USAGE_KEYS) expect(builder.mac.extendInfo[key]).toBeUndefined()
  })

  it('deletes each generic key that is there, asks only about the generic keys, and never throws', () => {
    const calls: string[] = []
    const present = new Set(['NSCameraUsageDescription', 'NSAudioCaptureUsageDescription'])
    const run = (_cmd: string, args: string[]): string => {
      const c = args[1] ?? ''
      calls.push(c)
      const key = c.replace(/^(Print|Delete) :/, '')
      if (c.startsWith('Print') && !present.has(key)) throw new Error('Print: Entry, ":' + key + '", Does Not Exist')
      return ''
    }
    expect(afterPack.stripGenericUsage('/nowhere/Info.plist', run)).toEqual(['NSCameraUsageDescription', 'NSAudioCaptureUsageDescription'])
    expect(calls.every((c) => afterPack.GENERIC_USAGE_KEYS.some((k) => c.endsWith(`:${k}`)))).toBe(true)
    expect(afterPack.stripGenericUsage('/nowhere/Info.plist', () => { throw new Error('no PlistBuddy') })).toEqual([])
  })

  it.runIf(process.platform === 'darwin')('on a real plist: the generic strings go and the microphone, speech recognition and Apple Events strings stay', () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'after-pack-'))
    const file = path.join(dir, 'Info.plist')
    const keys = [...afterPack.GENERIC_USAGE_KEYS, ...afterPack.NEEDED_USAGE_KEYS, 'CFBundleName']
    const body = keys.map((k) => `<key>${k}</key><string>${k === 'CFBundleName' ? 'Knack' : `words for ${k}`}</string>`).join('')
    fs.writeFileSync(file, `<?xml version="1.0" encoding="UTF-8"?><!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd"><plist version="1.0"><dict>${body}</dict></plist>`)
    const removed = afterPack.stripGenericUsage(file)
    expect(removed.sort()).toEqual([...afterPack.GENERIC_USAGE_KEYS].sort())
    const printed = execFileSync('plutil', ['-p', file], { encoding: 'utf8' })
    for (const k of afterPack.GENERIC_USAGE_KEYS) expect(printed).not.toContain(k)
    for (const k of [...afterPack.NEEDED_USAGE_KEYS, 'CFBundleName']) expect(printed).toContain(k)
    // a second run finds nothing left and changes nothing
    expect(afterPack.stripGenericUsage(file)).toEqual([])
    fs.rmSync(dir, { recursive: true, force: true })
  })

  it('does nothing off macOS', async () => {
    await expect(afterPack({ electronPlatformName: 'win32', appOutDir: '/nowhere', packager: { appInfo: { productFilename: 'Knack' } } })).resolves.toBeUndefined()
  })
})

describe('the stable identity for macOS permissions', () => {
  it('seals every build with a requirement that names only the bundle identifier, never a build hash', () => {
    const mod = require('../scripts/after-pack.cjs') as { STABLE_REQUIREMENT: string }
    expect(mod.STABLE_REQUIREMENT).toBe('=designated => identifier "app.knack.desktop"')
    expect(mod.STABLE_REQUIREMENT).not.toMatch(/cdhash/i)
  })
})
