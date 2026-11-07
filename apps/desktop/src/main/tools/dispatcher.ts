// The single entry for every Live tool call: used by the Live IPC (live:toolCall) and the debug HTTP (POST /tool).
import { LiveToolNameSchema, ToolArgSchemas } from '../../shared/protocol'
import type { LiveToolName, ToolArgs, ToolResult, ToolResultMap } from '../../shared/protocol'
import type { Services } from '../../shared/contracts'
import type { ConfirmBroker } from '../confirm'
import type { ServiceContext } from '../context'
import { createActuator, type Actuator } from '../actuator'
import { createDoItForMe } from '../actuator/flow'
import { createAgency, setAgency } from '../agency'
import { setAssist } from '../agency/assist'
import { createAxResolver } from '../agency/ax-resolver'
import { FILE_DATA_NOTICE, wrapSnippet } from '../../shared/files'

export type ToolSource = 'live' | 'debug'
export type Dispatch = (name: string, args: unknown, source?: ToolSource) => Promise<ToolResult>

// DEMO DIRECTOR hook (interactive demo only; unset otherwise): may answer a tool call itself, or return undefined for the normal path.
export type ToolIntercept = (name: string, args: unknown) => Promise<ToolResult | undefined>
let intercept: ToolIntercept | null = null
export function setToolIntercept(fn: ToolIntercept | null): void {
  intercept = fn
}

const POINTER_IDS = ['point-ring', 'point-arrow']

type Handlers = { [N in LiveToolName]: (args: ToolArgs<N>) => Promise<ToolResultMap[N]> }

export function createDispatcher(ctx: ServiceContext, s: Services, confirm: ConfirmBroker, actuator: Actuator = createActuator({ log: ctx.log })): Dispatch {
  const doItForMe = createDoItForMe({ ctx, s, confirm, actuator })
  setAssist(doItForMe) // auto-assist on stall (teaching/runner) reuses this exact flow
  const agency = createAgency({ ctx, s, confirm, actuator })
  const resolveAx = createAxResolver({ log: ctx.log })
  setAgency(agency)
  const handlers: Handlers = {
    async point_at({ target, step }) {
      const shot = await s.capture.grab('ground')
      const res = await s.grounder.ground({ target, shot })
      s.overlay.clear(POINTER_IDS)
      if (!res.found || !res.box) {
        return { found: false, confidence: res.confidence, note: res.reason ?? "I can't see that on the screen." }
      }
      // Native apps: snap the ring to the exact Accessibility frame of the control the target names (vision is only
      // good to ~+-20 points). No confident match keeps the vision box.
      let box = res.box
      if (resolveAx && !process.env.VITEST) {
        const c = { x: (res.box.xmin + res.box.xmax) / 2, y: (res.box.ymin + res.box.ymax) / 2 }
        const ax = await resolveAx(`${target} ${res.label ?? ''}`.trim(), c)
        if (ax && ax.how === 'label') box = ax.box
        if (process.env.ALONGSIDE_DEBUG === '1') ctx.log('point_at', `MEASURE vision=${JSON.stringify(res.box)} ax=${ax ? JSON.stringify({ how: ax.how, text: ax.text, box: ax.box }) : 'none'}`)
      }
      s.overlay.show([
        { id: 'point-ring', kind: 'ring', tone: 'guide', box, label: res.label ?? target, step },
        { id: 'point-arrow', kind: 'arrow', tone: 'guide', to: box },
      ])
      return { found: true, confidence: res.confidence, note: res.label }
    },
    start_lesson: ({ goal }) => s.runner.start(goal),
    step_done: ({ note }) => s.runner.onStepDone(note),
    verify_step: ({ expected_outcome }) => s.runner.verifyStep(expected_outcome),
    async set_help_level({ level, reason }) {
      if (ctx.settings.get().helpLevelMode === 'locked') {
        return { applied: false, level: ctx.state.get().level, note: 'The learner locked the help level.' }
      }
      return s.runner.requestLevel(level, reason)
    },
    // AGENTS hook: spawn_agent
    spawn_agent: ({ kind, task, payload }) => s.agents.spawn(kind, task, payload),
    async ask_user_confirm({ question, options }) {
      return { choice: await confirm.ask(question, options) }
    },
    async update_profile({ note }) {
      await s.learner.addNote(note)
      return { ok: true }
    },
    async end_lesson({ summary, teachBackScore, confidence }) {
      await s.runner.end(summary, teachBackScore, confidence)
      return { ok: true }
    },
    // AGENTS hook: clear_annotations
    async clear_annotations() {
      s.overlay.clear()
      return { ok: true }
    },
    // Opt-in; see src/main/actuator/flow.ts for the refusals, the real-click confirmation and the audit.
    do_it_for_me: ({ target }) => doItForMe({ target }),
    // AGENCY: see src/main/agency/ and docs/AGENCY.md (policy, real-click confirmations, audit, Stop).
    open_for_me: (args) => agency.runOpenForMe(args),
    act_for_me: ({ goal }) => agency.runActForMe(goal),
    // FILES: query the local index only (never a path to read). Snippets are the person's own file text, wrapped as untrusted data.
    async search_files({ query, k }) {
      if (!s.files) return { ok: false, mode: 'none', unverified: true, reason: 'files_off', note: 'File search is not available.', results: [], data_notice: FILE_DATA_NOTICE }
      const res = await s.files.search(query, k)
      return { ...res, results: res.results.slice(0, 3).map((hit) => ({ ...hit, snippet: wrapSnippet(hit.snippet) })) }
    },
  }

  return async (name, args, source = 'debug') => {
    const started = Date.now()
    if (intercept) {
      try {
        const handled = await intercept(name, args)
        if (handled !== undefined) return handled
      } catch (err) {
        ctx.log('dispatcher', `intercept failed for ${name}, using the normal path:`, err instanceof Error ? err.message : String(err))
      }
    }
    const parsedName = LiveToolNameSchema.safeParse(name)
    if (!parsedName.success) return { error: `Unknown tool: ${name}` }
    const tool = parsedName.data

    // The screen is only readable while a session is active; the debug HTTP bypasses this for headless tests.
    const { phase } = ctx.state.get()
    if (source === 'live' && (phase === 'asleep' || phase === 'listening_for_name')) {
      return { error: 'No active session' }
    }

    const parsedArgs = ToolArgSchemas[tool].safeParse(args ?? {})
    if (!parsedArgs.success) return { error: `Bad arguments for ${tool}: ${parsedArgs.error.issues.map((i) => i.message).join('; ')}` }

    let ok = true
    try {
      const run = handlers[tool] as (a: unknown) => Promise<ToolResult>
      return await run(parsedArgs.data)
    } catch (err) {
      ok = false
      const message = err instanceof Error ? err.message : String(err)
      ctx.log('dispatcher', `${tool} failed:`, message)
      return { error: message }
    } finally {
      ctx.bus.emit('tool:called', { name: tool, args: parsedArgs.data, ms: Date.now() - started, ok })
    }
  }
}
