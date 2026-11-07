// macOS privacy permissions: status (with a real capture probe), requests, deep links, relaunch and a change feed.
// macOS attributes a grant to the RESPONSIBLE app: the Terminal that launched a dev build, or Alongside when packaged.
// `hint` says which one to switch on. Other platforms have no such gate and report everything as granted.
import { execFile } from 'node:child_process'
import { app, desktopCapturer, shell, systemPreferences } from 'electron'
import type { WebContents } from 'electron'
import { IPC } from '../shared/ipc'
import type { PermissionPane, PermissionStatus, PermState, ScreenProbe } from '../shared/permissions'

const SETTINGS_URLS: Record<PermissionPane, string> = {
  screen: 'x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture',
  microphone: 'x-apple.systempreferences:com.apple.preference.security?Privacy_Microphone',
  accessibility: 'x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility',
}

const POLL_MS = 1500
const PROBE_ATTEMPTS = 3
const PROBE_TIMEOUT_MS = 3000
const PROBE_RETRY_GAP_MS = 150
// A successful probe stays valid this long; a failed one is retried sooner so a fresh grant shows up quickly.
const PROBE_OK_TTL_MS = 30_000
const PROBE_FAIL_TTL_MS = 4000

export type PermissionSender = Pick<WebContents, 'id' | 'isDestroyed' | 'send' | 'once'>

export interface Permissions {
  status(): Promise<PermissionStatus>
  requestMicrophone(): Promise<boolean>
  requestAccessibility(): boolean
  requestScreen(): Promise<PermissionStatus>
  openSettings(pane: PermissionPane): void
  relaunch(): void
  subscribe(sender: PermissionSender): void
  unsubscribe(sender: PermissionSender): void
  subscriberCount(): number
  dispose(): void
}

export interface PermissionsOptions {
  log?: (...args: unknown[]) => void
  platform?: NodeJS.Platform
  pollMs?: number
  // Test seams: the real ones are `ps` and Electron's desktopCapturer.
  readProcessTable?: () => Promise<string>
  probe?: () => Promise<ScreenProbe>
  now?: () => number
}

const asPermState = (raw: string): PermState => (raw === 'granted' || raw === 'denied' || raw === 'not-determined' || raw === 'restricted' ? raw : 'unknown')

/** Walks the process tree above `pid` and names the first macOS app bundle found (Terminal, iTerm, Claude, ...). */
export function findLaunchingApp(psOutput: string, pid: number): string | null {
  const parents = new Map<number, { ppid: number; comm: string }>()
  for (const line of psOutput.split('\n')) {
    const m = /^\s*(\d+)\s+(\d+)\s+(.+?)\s*$/.exec(line)
    if (m) parents.set(Number(m[1]), { ppid: Number(m[2]), comm: m[3] })
  }
  let cursor = parents.get(pid)?.ppid
  for (let depth = 0; cursor !== undefined && cursor > 1 && depth < 16; depth++) {
    const entry = parents.get(cursor)
    if (!entry) return null
    // The outermost bundle in the path: ".../Claude.app/.../Claude Helper.app/..." is "Claude".
    const bundle = /\/([^/]+)\.app\//.exec(entry.comm)
    if (bundle && !/^Electron(?: Helper.*)?$/.test(bundle[1])) return bundle[1]
    cursor = entry.ppid
  }
  return null
}

export function buildPermissionHint(opts: { packaged: boolean; launcher: string | null }): string {
  if (opts.packaged && !opts.launcher) return 'Switch on "Alongside" in the list, then reopen it.'
  if (opts.launcher) return `You started this from "${opts.launcher}", so macOS lists "${opts.launcher}" (and sometimes "Electron"). Switch on whichever you see, then reopen the app.`
  return 'Switch on "Electron" in the list (or the Terminal app you started this from), then reopen the app.'
}

function psTable(): Promise<string> {
  return new Promise((resolve) => {
    execFile('ps', ['-axo', 'pid=,ppid=,comm='], { maxBuffer: 4 * 1024 * 1024 }, (err, stdout) => resolve(err ? '' : stdout))
  })
}

const sleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms))

function withTimeout<T>(promise: Promise<T>, ms: number): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error(`timed out after ${ms} ms`)), ms)
    promise.then(
      (v) => {
        clearTimeout(timer)
        resolve(v)
      },
      (e) => {
        clearTimeout(timer)
        reject(e)
      },
    )
  })
}

// desktopCapturer's first call is flaky (sometimes []), so ask up to three times. A blank thumbnail is not a source.
export async function probeScreenCapture(attempts = PROBE_ATTEMPTS): Promise<ScreenProbe> {
  let threw = false
  for (let i = 0; i < attempts; i++) {
    try {
      const sources = await withTimeout(desktopCapturer.getSources({ types: ['screen'], thumbnailSize: { width: 64, height: 36 } }), PROBE_TIMEOUT_MS)
      if (sources.some((s) => !s.thumbnail.isEmpty())) return 'ok'
      threw = false
    } catch {
      threw = true
    }
    if (i < attempts - 1) await sleep(PROBE_RETRY_GAP_MS)
  }
  return threw ? 'error' : 'empty'
}

export function createPermissions(options: PermissionsOptions = {}): Permissions {
  const platform = options.platform ?? process.platform
  const log = options.log ?? ((...args: unknown[]) => console.log('[permissions]', ...args))
  const now = options.now ?? Date.now
  const probe = options.probe ?? probeScreenCapture
  const subscribers = new Set<PermissionSender>()
  let timer: NodeJS.Timeout | null = null
  let polling = false
  let lastJson = ''
  let probeCache: { at: number; screenApi: PermState; result: ScreenProbe } | null = null
  let hintPromise: Promise<string> | null = null

  const hint = (): Promise<string> => {
    hintPromise ??= (options.readProcessTable ?? psTable)().then((table) => buildPermissionHint({ packaged: app.isPackaged, launcher: findLaunchingApp(table, process.pid) }))
    return hintPromise
  }

  const probeScreen = async (screenApi: PermState, force: boolean): Promise<ScreenProbe> => {
    // 'not-determined' would make macOS show its prompt just because a status screen was opened: only requestScreen() does that.
    if (!force && screenApi === 'not-determined') return 'skipped'
    const cached = probeCache
    if (!force && cached && cached.screenApi === screenApi) {
      const ttl = cached.result === 'ok' ? PROBE_OK_TTL_MS : PROBE_FAIL_TTL_MS
      if (now() - cached.at < ttl) return cached.result
    }
    const result = await probe()
    probeCache = { at: now(), screenApi, result }
    return result
  }

  const compute = async (forceProbe: boolean): Promise<PermissionStatus> => {
    if (platform !== 'darwin') return { microphone: 'granted', screen: 'granted', accessibility: true, probe: 'skipped', needsRestart: false, hint: '' }
    const microphone = asPermState(systemPreferences.getMediaAccessStatus('microphone'))
    const screenApi = asPermState(systemPreferences.getMediaAccessStatus('screen'))
    const accessibility = systemPreferences.isTrustedAccessibilityClient(false)
    const probeResult = await probeScreen(screenApi, forceProbe)

    let screen: PermState
    let needsRestart = false
    if (probeResult === 'ok') screen = 'granted' // also covers a capture permission inherited from the launching Terminal
    else if (screenApi === 'granted') {
      // The OS says yes but nothing comes back: macOS applies a new grant only to a relaunched process.
      screen = 'unknown'
      needsRestart = probeResult === 'empty'
    } else screen = screenApi
    return { microphone, screen, accessibility, probe: probeResult, needsRestart, hint: await hint() }
  }

  const status = (): Promise<PermissionStatus> => compute(false)

  const publish = (next: PermissionStatus): void => {
    const json = JSON.stringify(next)
    if (json === lastJson) return
    lastJson = json
    for (const sender of subscribers) {
      if (sender.isDestroyed()) subscribers.delete(sender)
      else sender.send(IPC.permissionsChanged, next)
    }
  }

  const tick = async (): Promise<void> => {
    if (polling || subscribers.size === 0) return
    polling = true
    try {
      publish(await status())
    } catch (err) {
      log('poll failed:', err instanceof Error ? err.message : err)
    } finally {
      polling = false
    }
  }

  const stopPolling = (): void => {
    if (timer) clearInterval(timer)
    timer = null
  }

  const unsubscribe = (sender: PermissionSender): void => {
    subscribers.delete(sender)
    if (subscribers.size === 0) {
      stopPolling()
      lastJson = ''
    }
  }

  return {
    status,

    async requestMicrophone() {
      if (platform !== 'darwin') return true
      const granted = await systemPreferences.askForMediaAccess('microphone')
      void tick()
      return granted
    },

    requestAccessibility() {
      if (platform !== 'darwin') return true
      const trusted = systemPreferences.isTrustedAccessibilityClient(true)
      void tick()
      return trusted
    },

    // The only way to make macOS ask for Screen Recording is to try to capture.
    requestScreen: () => compute(true),

    openSettings(pane) {
      const url = SETTINGS_URLS[pane]
      if (!url || platform !== 'darwin') return
      void shell.openExternal(url).catch((err: unknown) => log('openExternal failed:', err instanceof Error ? err.message : err))
    },

    relaunch() {
      app.relaunch()
      app.exit(0)
    },

    subscribe(sender) {
      if (subscribers.has(sender)) return
      subscribers.add(sender)
      sender.once('destroyed', () => unsubscribe(sender))
      if (!timer) timer = setInterval(() => void tick(), options.pollMs ?? POLL_MS)
      void tick()
    },

    unsubscribe,
    subscriberCount: () => subscribers.size,

    dispose() {
      subscribers.clear()
      stopPolling()
    },
  }
}
