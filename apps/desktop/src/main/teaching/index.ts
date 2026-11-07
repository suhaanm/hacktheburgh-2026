// Wiring for src/main/services.ts: ONE memoised bundle per ServiceContext so learner, levels, runner and
// teaching share state. Nothing here touches `s` at construction time (services.ts rule): the runner reads
// the other services lazily through getters.
import type { Services, Teaching } from '../../shared/contracts'
import type { ServiceContext } from '../context'
import { TeachingLearnerStore, resolveUserDataDir } from './learner-store'
import { createLevelEngine } from './levels'
import type { TeachingLevelEngine } from './levels'
import { createTeaching } from './prompts'
import { LessonRunnerImpl } from './runner'
import { autoAssistEnabled, getAssist } from '../agency/assist'

export interface TeachingBundle {
  learner: TeachingLearnerStore
  levels: TeachingLevelEngine
  runner: LessonRunnerImpl
  teaching: Teaching
  ready: Promise<void>
}

// ALONGSIDE_PLAN_TIMEOUT_MS: how long start_lesson waits for the Argon plan before using the built-in one (default 8000).
function planTimeoutOverride(): { planTimeoutMs: number } | undefined {
  const n = Number(process.env.ALONGSIDE_PLAN_TIMEOUT_MS)
  return Number.isFinite(n) && n >= 500 ? { planTimeoutMs: n } : undefined
}

const bundles = new WeakMap<ServiceContext, TeachingBundle>()

export function teachingBundle(ctx: ServiceContext, s: Services): TeachingBundle {
  const existing = bundles.get(ctx)
  if (existing) return existing

  const learner = new TeachingLearnerStore({ dir: resolveUserDataDir(ctx.userDataDir), getSettings: () => ctx.settings.get() })
  const levels = createLevelEngine()
  const ready = learner
    .load()
    .then(() => undefined)
    .catch((err) => ctx.log('teaching', 'could not load profile.md:', err instanceof Error ? err.message : err))

  const runner = new LessonRunnerImpl({
    get capture() { return s.capture },
    get grounder() { return s.grounder },
    get verifier() { return s.verifier },
    get architect() { return s.architect },
    get overlay() { return s.overlay },
    get live() { return s.live },
    get learner() { return s.learner },
    get levels() { return s.levels },
    state: ctx.state,
    bus: ctx.bus,
    getSettings: () => ctx.settings.get(),
    // Auto-assist on stall: only wired with ALONGSIDE_AUTO_ASSIST=1 (default off); reuses the do_it_for_me flow.
    ...(autoAssistEnabled() ? { assist: (args: { target: string }) => (getAssist() ? getAssist()!(args) : Promise.reject(new Error('assist unavailable'))) } : {}),
    config: planTimeoutOverride(),
    // Re-read profile.md at each lesson start so edits made outside the app (and the demo seed) are honoured.
    get ready() { return ready.then(() => learner.refresh()) },
    log: (scope, ...args) => ctx.log(String(scope), ...args),
  })

  const teaching = createTeaching({
    getSettings: () => ctx.settings.get(),
    getLevel: () => ctx.state.get().level,
    learner: {
      snapshot: () => s.learner.snapshot(),
      preferredName: () => learner.preferredName(),
    },
    getLesson: () => runner.currentLesson(),
    ready: () => ready.then(() => learner.refresh()),
  })

  const bundle: TeachingBundle = { learner, levels, runner, teaching, ready }
  bundles.set(ctx, bundle)
  return bundle
}
