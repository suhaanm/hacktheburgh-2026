import { describe, expect, it } from 'vitest'
import { createActuator } from '../../src/main/actuator'

function rig(over: { trusted?: boolean; osascriptFails?: boolean; dryRun?: boolean } = {}) {
  const events: string[] = []
  let clipboard = 'my earlier clipboard'
  const actuator = createActuator({
    platform: 'darwin',
    isTrusted: () => over.trusted ?? true,
    dryRun: over.dryRun ?? false,
    displayBounds: () => ({ x: 0, y: 0, width: 1000, height: 800 }),
    openExternal: async () => undefined,
    showItemInFolder: () => undefined,
    osascript: async (args) => {
      events.push(`osascript ${args.join(' ')} | clipboard=${clipboard}`)
      if (over.osascriptFails) throw new Error('boom')
    },
    readClipboard: async () => (events.push('read'), clipboard),
    writeClipboard: async (t) => void (events.push(`write ${t}`), (clipboard = t)),
  })
  return { actuator, events, clip: () => clipboard }
}

describe('actuator.pasteText (the typing fallback)', () => {
  it('puts the text on the clipboard, presses Cmd+V, then restores the earlier clipboard', async () => {
    const { actuator, events, clip } = rig()
    const r = await actuator.pasteText!('software engineer')
    expect(r.ok).toBe(true)
    expect(events[0]).toBe('read')
    expect(events[1]).toBe('write software engineer')
    expect(events[2]).toMatch(/^osascript .*command down.* \| clipboard=software engineer$/)
    expect(events[3]).toBe('write my earlier clipboard')
    expect(clip()).toBe('my earlier clipboard')
  })

  it('restores the clipboard even when the paste keystroke fails, and says failed', async () => {
    const { actuator, clip } = rig({ osascriptFails: true })
    const r = await actuator.pasteText!('hello')
    expect(r).toMatchObject({ ok: false, reason: 'failed' })
    expect(clip()).toBe('my earlier clipboard')
  })

  it.each([
    ['', 'empty'],
    ['bad\u0007bell', 'control character'],
    ['x'.repeat(301), 'too long'],
  ])('refuses text that typeText would refuse (%s)', async (text) => {
    const { actuator, events } = rig()
    expect((await actuator.pasteText!(text)).reason).toBe('blocked')
    expect(events).toEqual([])
  })

  it('without Accessibility nothing is touched; a dry run touches nothing', async () => {
    const a = rig({ trusted: false })
    expect(await a.actuator.pasteText!('hello')).toMatchObject({ ok: false, reason: 'accessibility' })
    expect(a.events).toEqual([])
    const d = rig({ dryRun: true })
    expect(await d.actuator.pasteText!('hello')).toMatchObject({ ok: true, reason: 'dry-run' })
    expect(d.events).toEqual([])
  })
})
