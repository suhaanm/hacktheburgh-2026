import os from 'node:os'
import path from 'node:path'
import type { Services } from '../../shared/contracts'
import type { ServiceContext } from '../context'
import { createAgentModelPort } from './gemini-port'
import { createAgents } from './index'
import type { AgentRuntimeApi } from './runtime'

// Services may not exist yet at construction time, so every dependency is read lazily from `s`.
export function createAgentsFromServices(ctx: ServiceContext, s: Services): AgentRuntimeApi {
  const runtime = createAgents({
    state: ctx.state,
    bus: ctx.bus,
    capture: { grab: (purpose) => s.capture.grab(purpose) },
    grounder: { ground: (req) => s.grounder.ground(req) },
    scam: { analyze: (req, opts) => s.scam.analyze(req, opts) },
    overlay: { show: (annotations) => s.overlay.show(annotations), clear: (ids) => s.overlay.clear(ids) },
    live: { inject: (text, opts) => s.live.inject(text, opts) },
    learner: { snapshot: () => s.learner.snapshot() },
    settings: () => ctx.settings.get(),
    model: createAgentModelPort(),
    exportsDir: path.join(ctx.userDataDir ?? path.join(os.tmpdir(), 'alongside'), 'exports'),
  })
  // The dispatcher's clear_annotations also removes any scam highlights we are still tracking.
  const offClear = ctx.bus.on('tool:called', ({ name }) => {
    if (name === 'clear_annotations') runtime.clearHighlights()
  })
  // The big Stop control stops everything an agent is doing. Goodbye/idle leave running checks to finish.
  const offStop = ctx.bus.on('session:ended', ({ reason }) => {
    if (reason === 'stop') runtime.cancelAll()
  })
  return {
    ...runtime,
    dispose() {
      offClear()
      offStop()
      runtime.dispose()
    },
  }
}
