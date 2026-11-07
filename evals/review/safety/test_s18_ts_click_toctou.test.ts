// S-18 (Medium): the TS actuator reads the window under the point in one osascript process (topWindowAt, 150-400 ms) and sends the click in
// ANOTHER one; nothing looks again in between except the kill flag. A window that moves, a notification banner or a Space switch in that gap
// gets the click. Fix: do the hit test and the click in the SAME script (read the window list, verify the pinned window id, post the CGEvent,
// all in-process, a few ms), or re-run topWindowAt right before sending. Fakes only: no desktop, no network.
import { createActuator, type DesktopProbe } from '../../../apps/desktop/src/main/actuator/index'

const PIN = { id: 7, pid: 100, owner: 'TextEdit' }
const DISPLAY = { x: 0, y: 0, width: 1728, height: 1117 }

it('a click is not sent when the window under the point changed after the hit test passed', async () => {
  let reads = 0
  const sent: string[][] = []
  const probe: DesktopProbe = {
    frontmostApp: async () => 'TextEdit',
    frontWindow: async () => ({ owner: 'TextEdit', layer: 0, windowId: 7, pid: 100 }),
    // first read: the pinned window; every later read: a notification banner has appeared under the same point
    topWindowAt: async () => (++reads === 1 ? { owner: 'TextEdit', layer: 0, windowId: 7, pid: 100 } : { owner: 'NotificationCenter', layer: 23, windowId: 99, pid: 55 }),
  }
  const actuator = createActuator({
    platform: 'darwin', dryRun: false, isTrusted: () => true, displayBounds: () => DISPLAY, scaleFactor: () => 2, probe,
    osascript: async (args: string[]) => void sent.push(args), killFileExists: () => false,
    sleep: async () => undefined, readClipboard: async () => '', writeClipboard: async () => undefined,
    openExternal: async () => undefined, showItemInFolder: () => undefined, openAppProcess: async () => undefined,
  })
  const r = await actuator.clickAt({ x: 500, y: 500 }, { target: { app: 'TextEdit', window: PIN } })
  expect({ clicksSent: sent.length, ok: r.ok, detail: r.detail }).toEqual({ clicksSent: 0, ok: false, detail: expect.any(String) })   // refused: the second read disagrees
})
