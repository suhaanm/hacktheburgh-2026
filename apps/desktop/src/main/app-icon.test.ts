import path from 'node:path'
import { describe, expect, it } from 'vitest'
import { appIconPath } from './app-icon'

describe('app icon lookup', () => {
  it('prefers the app folder, then the packaged resources, else nothing', () => {
    const only = (...files: string[]) => (p: string) => files.includes(p)
    expect(appIconPath('/app', '/res', only('/app/build/icon.png', '/res/icon.png'))).toBe(path.join('/app', 'build', 'icon.png'))
    expect(appIconPath('/app', '/res', only('/res/icon.png'))).toBe(path.join('/res', 'icon.png'))
    expect(appIconPath('/app', undefined, only())).toBeNull()
  })

  it('the exported files exist: the 1024 px app icon, the .icns, and every menu-bar state at 1x and 2x', async () => {
    const fs = await import('node:fs')
    const root = path.join(__dirname, '../..')
    for (const f of ['build/icon.png', 'build/icon.icns']) expect(fs.existsSync(path.join(root, f)), f).toBe(true)
    for (const b of ['trayTemplate', 'trayActingTemplate', 'trayGlanceTemplate', 'trayPausedTemplate']) {
      for (const suffix of ['', '@2x']) expect(fs.existsSync(path.join(root, `resources/tray/${b}${suffix}.png`)), `${b}${suffix}`).toBe(true)
    }
    // a macOS .icns starts with the magic "icns"
    expect(fs.readFileSync(path.join(root, 'build/icon.icns')).subarray(0, 4).toString('ascii')).toBe('icns')
    // the PNG is 1024 x 1024; the tray PNGs are 18 and 36 px, pure black with alpha (template images)
    const png = (f: string) => fs.readFileSync(path.join(root, f))
    const size = (b: Buffer) => [b.readUInt32BE(16), b.readUInt32BE(20)]
    expect(size(png('build/icon.png'))).toEqual([1024, 1024])
    expect(size(png('resources/tray/trayTemplate.png'))).toEqual([18, 18])
    expect(size(png('resources/tray/trayTemplate@2x.png'))).toEqual([36, 36])
  })
})
