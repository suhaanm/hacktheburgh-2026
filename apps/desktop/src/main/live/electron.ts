// The real adapters for voice: Electron's ipcMain and the dock window, the macOS microphone status (read only, never requested), the
// permission-free probes, the real frame source, the HTTP ledger and grounding ports, the ephemeral-token minter. This is the only live file
// that imports 'electron' statically, and no test imports it.
//
// Wiring (src/main/index.ts, owned by the shell track; NOT edited here):
//
//   import { registerLive } from './live/electron'
//   const live = registerLive({
//     bus,
//     userDataDir: app.getPath('userData'),
//     endpoints: understudy.endpoints,                            // { engine, agent }
//     sendDock: (channel, ...args) => (windows.sendDock as unknown as (c: string, ...a: unknown[]) => void)(channel, ...args),
//     owns: (id) => windows.owns(id),
//     overlay: services.overlay,                                  // the OverlayController
//     cue: cueHandle.livePort,                                    // startCue(ctx) returns { livePort }
//     killed: () => understudy.kill.isKilled(),
//     agentActing: () => understudy.hudModel.state().agentActing, // or the agent-activity poller's acting()
//     cueVoiceOn: () => settings.get().cueVoice === true,
//     domGround: understudy.domGrounder.asGroundPort?.(),         // optional: DOM-first grounding in browsers
//     log: ctx.log,
//   })
//   live.manager.start()
//   // pass live.voice, live.speaker and live.workerUsedVoice to startCue(ctx, ...)
//   // app.on('will-quit', () => live.dispose())
import { app, ipcMain, systemPreferences } from 'electron'
import { createDesktopFrameSource, type FrameSource } from '../awareness/capture'
import { createFakeFrameSource } from '../awareness/capture-fake'
import { createConsoleProbe, createFrontmostSource, createScreenShareProbe } from '../awareness/probes'
import { isLoopbackUrl, type Endpoints } from '../engine/endpoints'
import { createBridgeIpc } from './bridge-ipc'
import { createCompositeGround, createHttpGroundPort } from './http-ground'
import { createFrameProvider } from './frame-provider'
import { createLive, type LiveRegistration } from './index'
import { createHttpLiveLedger } from './ledger'
import { createUsageLog } from './meter'
import { createRingPort } from './ring'
import { LiveSettingsStore } from './settings'
import { GateMonitor, createGateReader } from './gates'
import { checkLiveModel, createTokenMinter } from './token'
import { liveModelId } from './flags'
import type { OverlayController } from '../../shared/contracts'
import type { DoItAnswer, DoItRequest, GroundPort, LiveCuePort } from './ports'
import type { Bus } from '../bus'

export interface RegisterLiveOptions {
  bus: Pick<Bus, 'on'>
  userDataDir?: string
  endpoints: Pick<Endpoints, 'engine' | 'agent'>
  sendDock: (channel: string, ...args: unknown[]) => void
  owns: (webContentsId: number) => boolean
  overlay: Pick<OverlayController, 'show' | 'clear'>
  cue: LiveCuePort
  // Hey Knack's `do_it_for_me` (wake sessions only). Late-bound by the caller; absent: the tool answers "not available".
  doIt?: (req: DoItRequest) => Promise<DoItAnswer>
  // The code-built context packet for a conversation (wake/context-packet.ts); late-bound by the caller.
  context?: (o: { tools: import('./wire').FunctionDeclaration[]; trigger: 'key' | 'wake' }) => string
  killed: () => boolean
  agentActing: () => boolean
  cueVoiceOn?: () => boolean
  domGround?: GroundPort | null
  // The awareness layer's denylist options (glanceStrict and glanceDenylist); the defaults are strict and no worker additions.
  deny?: () => { strict: boolean; workerList: readonly string[] }
  frameSource?: FrameSource
  appKind?: () => string | undefined
  env?: Record<string, string | undefined>
  log?: (scope: string, ...args: unknown[]) => void
}

export function registerLive(o: RegisterLiveOptions): LiveRegistration {
  const env = o.env ?? process.env
  const mock = env.UNDERSTUDY_MOCK === '1' || env.ALONGSIDE_MOCK === '1'
  const dir = o.userDataDir ?? app.getPath('userData')
  const settings = new LiveSettingsStore(dir)
  const bridge = createBridgeIpc({
    send: (channel, ...args) => o.sendDock(channel, ...args),
    on: (channel, listener) => {
      const handler = (event: { sender: { id: number } }, ...args: unknown[]): void => {
        if (!o.owns(event.sender.id)) return // only our own windows may talk to the voice path
        listener(...args)
      }
      ipcMain.on(channel, handler as never)
      return () => void ipcMain.off(channel, handler as never)
    },
  })
  // In mock mode no real screen is ever read: the fake source hands out a fixture. The real source needs the Screen Recording permission.
  const frameSource = o.frameSource ?? (mock ? createFakeFrameSource() : createDesktopFrameSource())
  const frames = createFrameProvider(frameSource)
  const gateSources = {
    frontmost: createFrontmostSource(),
    console: createConsoleProbe(),
    screenShare: createScreenShareProbe(),
    killed: o.killed,
    unattended: o.agentActing,
    settings: () => settings.get(),
    deny: o.deny ?? (() => ({ strict: true, workerList: [] as readonly string[] })),
  }
  const reader = createGateReader(gateSources)
  const vision = createHttpGroundPort({ agentUrl: o.endpoints.agent, isLoopback: isLoopbackUrl, frames, gates: () => reader.read('frames') })
  const live = createLive({
    env,
    bus: o.bus,
    settings,
    tokens: createTokenMinter({ env }),
    modelCheck: () => checkLiveModel(liveModelId(env), { env }),
    gateSources,
    ledger: createHttpLiveLedger({ engineUrl: o.endpoints.engine, isLoopback: isLoopbackUrl }),
    audio: bridge.audio,
    clips: bridge.clips,
    frames,
    cue: o.cue,
    ground: createCompositeGround(o.domGround ?? null, vision),
    ring: createRingPort(o.overlay),
    doIt: o.doIt,
    context: o.context,
    usage: createUsageLog(dir),
    // Reads the status only. The prompt is the owner's to accept in System Settings; this code never calls askForMediaAccess.
    micStatus: () => (process.platform === 'darwin' ? systemPreferences.getMediaAccessStatus('microphone') : 'granted'),
    agentActing: o.agentActing,
    killed: o.killed,
    appKind: o.appKind,
    agentUrl: o.endpoints.agent,
    isLoopback: isLoopbackUrl,
    cueVoiceOn: o.cueVoiceOn,
    log: o.log,
  })
  return {
    ...live,
    dispose() {
      live.dispose()
      bridge.dispose()
    },
  }
}

// Kept so a caller can build a monitor of its own (the Privacy screen's "what is being checked" line).
export { GateMonitor }
