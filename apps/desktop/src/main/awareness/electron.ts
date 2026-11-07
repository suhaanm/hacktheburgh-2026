// The real adapters for the awareness controller: Electron's screen and powerMonitor, loopback HTTP, the permission-free probes, the real
// frame source and the HTTP glance port. This is the only awareness file that imports 'electron' statically, and no test imports it.
//
// Wiring (src/main/index.ts, owned by the shell track; NOT edited here):
//
//   import { createElectronAwareness } from './awareness/electron'
//   const awareness = createElectronAwareness({
//     userDataDir: app.getPath('userData'),
//     endpoints: understudy.endpoints,                      // { engine, agent } from engine/endpoints.ts
//     identity: () => understudy.engine.identity,           // { person, role }
//     killed: () => understudy.kill.isKilled(),
//     workSession: () => coachPoller.lastState()?.task != null,
//     log: ctx.log,
//   })
//   awareness.start()                                       // a no-op unless UNDERSTUDY_X_AWARENESS (or UNDERSTUDY_X) is set and awarenessEnabled is on
//   // the hotkey: globalShortcut.register('CommandOrControl+Alt+G', () => void awareness.hotkey())   (pick a free accelerator)
//   // the consent card: awareness.setConsent({ trigger: true, periodic: false }); the Privacy screen: awareness.getAwarenessState()
//   app.on('before-quit', () => awareness.dispose())
import { app, powerMonitor, screen } from 'electron'
import { isLoopbackUrl, type Endpoints } from '../engine/endpoints'
import { createFakeFrameSource } from './capture-fake'
import { createDesktopFrameSource, type FrameSource } from './capture'
import { createLoopbackPost, type Identity } from './events'
import { createHttpGlancePort } from './glance'
import { createAwareness, type Awareness, type PowerLike } from './index'
import { createConsoleProbe, createFrontmostSource, createScreenShareProbe } from './probes'
import { AwarenessSettingsStore } from './settings'
import type { GlancePort } from './types'

export interface ElectronAwarenessOptions {
  userDataDir?: string
  endpoints: Pick<Endpoints, 'engine' | 'agent'>
  identity: () => Identity
  killed?: () => boolean
  workSession?: () => boolean
  log?: (scope: string, ...args: unknown[]) => void
  // Overrides (mock mode and tests): a fake frame source, another glance port.
  frames?: FrameSource
  port?: GlancePort
  env?: Record<string, string | undefined>
}

async function getJson(url: string): Promise<unknown | null> {
  if (!isLoopbackUrl(url)) return null
  const ctl = new AbortController()
  const t = setTimeout(() => ctl.abort(), 2000)
  try {
    const res = await fetch(url, { signal: ctl.signal })
    if (!res.ok) return null
    return await res.json()
  } catch {
    return null
  } finally {
    clearTimeout(t)
  }
}

export function createElectronAwareness(opts: ElectronAwarenessOptions): Awareness {
  const env = opts.env ?? process.env
  const mock = env.UNDERSTUDY_MOCK === '1'
  const settings = new AwarenessSettingsStore(opts.userDataDir ?? app.getPath('userData'))
  return createAwareness({
    settings,
    engineUrl: opts.endpoints.engine,
    identity: opts.identity,
    env,
    getCursorPoint: () => screen.getCursorScreenPoint(),
    power: powerMonitor as unknown as PowerLike,
    getJson,
    post: createLoopbackPost({ isLoopback: isLoopbackUrl }),
    frontmost: createFrontmostSource(),
    console: createConsoleProbe(),
    screenShare: createScreenShareProbe(),
    // In mock mode no real screen is ever read: the fake source hands out a fixture. The real source needs the Screen Recording permission.
    frames: opts.frames ?? (mock ? createFakeFrameSource() : createDesktopFrameSource()),
    port: opts.port ?? createHttpGlancePort({ agentUrl: opts.endpoints.agent, isLoopback: isLoopbackUrl }),
    killed: opts.killed,
    workSession: opts.workSession,
    log: opts.log,
  })
}
