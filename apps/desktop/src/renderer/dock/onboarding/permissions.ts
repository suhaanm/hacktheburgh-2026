// Permissions as the flow sees them: SHELL's API (window.alongside.permissions) plus pure helpers that turn raw status
// into the words and the single action each row shows. Nothing here ever blocks the flow.
import type { AlongsideApi } from '../../../shared/ipc'
import type { PermState, PermissionStatus } from '../../../shared/permissions'

export type { PermState, PermissionStatus }
export type PermKind = 'microphone' | 'screen' | 'accessibility'
export type PermissionsApi = AlongsideApi['permissions']

export type RowAction = 'request' | 'open' | 'restart' | 'none'

export interface RowView {
  kind: PermKind
  title: string
  line: string
  optional: boolean
  granted: boolean
  chip: string
  action: RowAction
  actionLabel: string
}

const ROWS: Readonly<Record<PermKind, { title: string; line: string; optional: boolean }>> = {
  microphone: { title: 'Microphone', line: 'So I can hear you when you speak to me.', optional: false },
  screen: { title: 'Screen recording', line: 'I only see your screen while you are talking to me.', optional: false },
  accessibility: { title: 'Clicking for you', line: 'Optional. So I can click for you, only if you ask.', optional: true },
}

export function describeRow(kind: PermKind, status: PermissionStatus | null, opts: { restart?: boolean } = {}): RowView {
  const base = ROWS[kind]
  const raw: PermState | boolean | undefined = status === null ? undefined : status[kind]
  const granted = raw === true || raw === 'granted'
  const view = (chip: string, action: RowAction, actionLabel: string, ok = granted): RowView => ({ kind, ...base, granted: ok, chip, action, actionLabel })
  const blocked = raw === 'denied' || raw === 'restricted'

  if (kind === 'screen' && (status?.needsRestart || opts.restart)) return view('Restart needed', 'restart', 'Restart now', false)
  if (granted) return view('Allowed', 'none', '')
  if (kind === 'microphone') return blocked ? view('Blocked', 'open', 'Open Microphone settings') : view('Not allowed yet', 'request', 'Allow the microphone')
  if (kind === 'screen') {
    if (blocked) return view('Blocked', 'open', 'Open Screen Recording settings')
    if (raw === 'not-determined') return view('Not allowed yet', 'request', 'Allow screen recording')
    return view(raw === undefined || raw === 'unknown' ? 'Not checked yet' : 'Not allowed yet', 'open', 'Open Screen Recording settings')
  }
  return view('Not allowed yet', 'request', 'Allow me to click')
}

/** The OS flips Screen Recording to allowed during this setup but the running app only sees the screen after a restart. */
export function screenNeedsRestart(atStart: PermState | null, now: PermissionStatus | null): boolean {
  if (now === null) return false
  if (now.needsRestart) return true
  return atStart !== null && atStart !== 'granted' && now.screen === 'granted' && now.probe !== 'ok'
}

/** Browser fallback (the gallery, or a build without the IPC): the microphone can still be asked for, nothing else can be checked. */
export function fallbackPermissions(): PermissionsApi {
  const status: PermissionStatus = { microphone: 'unknown', screen: 'unknown', accessibility: false, probe: 'skipped', needsRestart: false, hint: '' }
  return {
    status: async () => status,
    requestMicrophone: async () => {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
        stream.getTracks().forEach((t) => t.stop())
        return true
      } catch {
        return false
      }
    },
    requestAccessibility: () => false,
    requestScreen: async () => status,
    openSettings: () => undefined,
    relaunch: () => undefined,
    onChange: () => () => undefined,
  }
}

export function getPermissionsApi(): PermissionsApi {
  return (window.alongside as Partial<AlongsideApi> | undefined)?.permissions ?? fallbackPermissions()
}

// ---------- microphone level meter ("Test it") ----------
export interface MicMeter {
  stop(): void
}

/** Opens the microphone only to draw a level bar; nothing is recorded or sent. `onLevel` gets 0..1. */
export async function startMicMeter(onLevel: (level: number) => void): Promise<MicMeter> {
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
  const ctx = new AudioContext()
  const source = ctx.createMediaStreamSource(stream)
  const analyser = ctx.createAnalyser()
  analyser.fftSize = 512
  source.connect(analyser)
  const data = new Uint8Array(analyser.fftSize)
  let raf = 0
  const tick = (): void => {
    analyser.getByteTimeDomainData(data)
    let peak = 0
    for (const v of data) peak = Math.max(peak, Math.abs(v - 128))
    onLevel(Math.min(1, (peak / 128) * 2.2))
    raf = requestAnimationFrame(tick)
  }
  tick()
  return {
    stop: () => {
      cancelAnimationFrame(raf)
      source.disconnect()
      stream.getTracks().forEach((t) => t.stop())
      void ctx.close()
    },
  }
}
