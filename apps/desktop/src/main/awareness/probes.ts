// Permission-free probes for the gates, each behind an injected `exec` so tests never run a process. Only READ-ONLY system queries:
//   frontmost app   `lsappinfo info -only bundleid -app front`   (Launch Services, no permission, ~40 ms). Window titles are NOT available this
//                   way and are never read: Accessibility or Screen Recording would be needed, and neither is requested.
//   secure input    `ioreg -r -k IOConsoleUsers -d 1 -w 0`      (IORegistry, no permission, ~0.1 s). While any app has secure event input on (a
//                   password field has focus), the console session entry carries the key kCGSSessionSecureInputPID. The same output says
//                   whether the console is locked.
//   screen sharing  `ps -axo comm=` matched on EXACT process names that only exist while sharing (heuristic and incomplete: see below).
// What each parser returns is a boolean, an enum or a bundle id. User names, pids and every other field in the raw output are dropped.
import { execFile } from 'node:child_process'
import { BUNDLE_ID_RE } from './denylist'
import type { SecureInputState } from './types'

export type ExecResult = { stdout: string }
export type Exec = (file: string, args: readonly string[], opts: { timeoutMs: number }) => Promise<ExecResult>

/** The one real exec: execFile (no shell), bounded time and output. Used only by the real factories below. */
export const realExec: Exec = (file, args, opts) =>
  new Promise((resolve, reject) => {
    execFile(file, [...args], { timeout: opts.timeoutMs, maxBuffer: 8 * 1024 * 1024, encoding: 'utf8' }, (err, stdout) => (err ? reject(err) : resolve({ stdout })))
  })

// ------------------------------------------------------------------------------------------------ frontmost app
export function parseBundleId(out: string): string | null {
  const m = /"CFBundleIdentifier"\s*=\s*"([^"\n]{2,121})"/.exec(out)
  if (!m || !BUNDLE_ID_RE.test(m[1])) return null
  return m[1]
}

export interface FrontmostSource {
  /** Bundle id of the frontmost app, or null when it could not be read. */
  read(): Promise<string | null>
}

export function createFrontmostSource(exec: Exec = realExec): FrontmostSource {
  return {
    async read() {
      try {
        const r = await exec('lsappinfo', ['info', '-only', 'bundleid', '-app', 'front'], { timeoutMs: 1500 })
        return parseBundleId(r.stdout)
      } catch {
        return null
      }
    },
  }
}

// ------------------------------------------------------------------------------------------------ secure input and console lock
export interface ConsoleState {
  secureInput: SecureInputState
  // true / false from IOConsoleLocked; null when the line is missing.
  locked: boolean | null
}

/**
 * Parses the output of `ioreg -r -k IOConsoleUsers -d 1 -w 0`. 'on' only when an IOConsoleUsers entry exists and carries
 * kCGSSessionSecureInputPID; 'off' when the entry exists without it; 'unknown' when there is no entry (the probe could not see the session).
 * The 'on' form is from the documented behaviour of secure event input, not yet seen on this Mac (it needs a password field focused,
 * which is a real interaction this build does not perform). The 'off' form is checked against a real capture of the output.
 */
export function parseConsoleState(out: string): ConsoleState {
  const line = out.split('\n').find((l) => /"IOConsoleUsers"\s*=\s*\(/.test(l))
  const lockedMatch = /"IOConsoleLocked"\s*=\s*(Yes|No)\b/.exec(out)
  const locked = lockedMatch ? lockedMatch[1] === 'Yes' : null
  if (!line) return { secureInput: 'unknown', locked }
  return { secureInput: line.includes('kCGSSessionSecureInputPID') ? 'on' : 'off', locked }
}

export interface ConsoleProbe {
  read(): Promise<ConsoleState>
}

export function createConsoleProbe(exec: Exec = realExec): ConsoleProbe {
  return {
    async read() {
      try {
        const r = await exec('ioreg', ['-r', '-k', 'IOConsoleUsers', '-d', '1', '-w', '0'], { timeoutMs: 2500 })
        return parseConsoleState(r.stdout)
      } catch {
        return { secureInput: 'unknown', locked: null }
      }
    },
  }
}

// ------------------------------------------------------------------------------------------------ screen sharing (heuristic)
// Exact executable names that exist only while sharing: Zoom's share helper and macOS's screensharingd. A loose match would be wrong:
// ScreenSharingSubscriber (always running) and Zoom's audio driver are not sharing. Not covered: Teams, Meet, FaceTime, QuickTime or
// the system presenter overlay. "No helper seen" therefore means "not detected", never "not sharing".
const SHARE_PROCS = new Set(['cpthost', 'screensharingd'])

export function parseScreenShare(psOut: string): boolean {
  for (const line of psOut.split('\n')) {
    const base = line.trim().split('/').pop()?.toLowerCase() ?? ''
    if (SHARE_PROCS.has(base)) return true
  }
  return false
}

export interface ScreenShareProbe {
  /** true when a sharing helper is running; false when none was seen; null when the list could not be read. */
  read(): Promise<boolean | null>
}

export function createScreenShareProbe(exec: Exec = realExec): ScreenShareProbe {
  return {
    async read() {
      try {
        const r = await exec('ps', ['-axo', 'comm='], { timeoutMs: 2000 })
        return parseScreenShare(r.stdout)
      } catch {
        return null
      }
    },
  }
}
