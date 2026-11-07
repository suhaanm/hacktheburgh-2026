import { IPC } from '../shared/ipc'
import type { LiveBridge } from '../shared/contracts'
import type { ServiceContext } from './context'

// Forwards stage directions to the Live session that runs in the dock renderer. No-op when no session is live.
export function createLiveBridge(ctx: ServiceContext): LiveBridge {
  return {
    inject(text, opts) {
      const { phase } = ctx.state.get()
      if (phase === 'asleep' || phase === 'listening_for_name') return
      ctx.sendDock(IPC.liveInject, { text, interrupt: opts?.interrupt })
    },
  }
}
