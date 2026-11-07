// The attention layer, desktop side (REQ-8). One call from main/index.ts, after the services exist:
//     const attention = startAttention({ endpoints, person, signals, ports, killed, sources })     (stopAttention in will-quit)
// and Cue gets `attention.adapter.cuePort()` as `attention` in createCueController deps. No Electron import here: every surface is a port the
// shell binds, so the whole layer runs and is tested without a window. Off unless the flag is on (see flags.ts); then nothing is created.
import { createAttentionAdapter, type AttentionAdapter, type AttentionPorts } from './adapter'
import { createProducerBridge, type ProducerBridge, type ProducerSources } from './bridge'
import { createHttpClient, type AttentionClient } from './client'
import { attentionEnabled } from './flags'
import { createVoiceLock, type VoiceLock } from './lock'
import type { AttentionSignals } from './signals'

export * from './adapter'
export * from './bridge'
export * from './client'
export * from './flags'
export * from './lock'
export * from './signals'
export * from './types'

export interface StartAttentionContext {
  engineUrl: string
  person: () => string | null
  signals: () => AttentionSignals
  ports: AttentionPorts
  killed?: () => boolean
  sources?: ProducerSources
  log?: (scope: string, ...args: unknown[]) => void
  env?: Record<string, string | undefined>
  /** Tests and storyboards: a client instead of the engine over loopback. */
  client?: AttentionClient
  lock?: VoiceLock
  force?: boolean
  bridgeEveryMs?: number
}

export interface AttentionHandle {
  adapter: AttentionAdapter
  bridge: ProducerBridge | null
  lock: VoiceLock
  stop(): void
}

let running: AttentionHandle | null = null

export function startAttention(ctx: StartAttentionContext): AttentionHandle | null {
  if (!ctx.force && !attentionEnabled(ctx.env)) return null
  if (running) return running
  const lock = ctx.lock ?? createVoiceLock()
  const client = ctx.client ?? createHttpClient({ baseUrl: ctx.engineUrl, person: ctx.person, log: ctx.log })
  const adapter = createAttentionAdapter({ client, signals: ctx.signals, ports: ctx.ports, lock, killed: ctx.killed, log: ctx.log })
  const bridge = ctx.sources ? createProducerBridge(ctx.sources, (ev) => adapter.report(ev)) : null
  adapter.start()
  let timer: ReturnType<typeof setInterval> | null = null
  if (bridge) {
    void bridge.pollOnce()
    timer = setInterval(() => void bridge.pollOnce(), Math.max(5_000, ctx.bridgeEveryMs ?? 15_000))
  }
  running = {
    adapter,
    bridge,
    lock,
    stop() {
      if (timer) clearInterval(timer)
      adapter.stop()
      running = null
    },
  }
  return running
}

export function stopAttention(): void {
  running?.stop()
}
