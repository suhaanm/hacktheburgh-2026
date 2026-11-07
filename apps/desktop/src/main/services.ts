// DI bag. ONE LINE PER SERVICE: an owner swaps in their real implementation by editing only their own line.
// Flags: ALONGSIDE_MOCK=1 mocks every model-backed service; ALONGSIDE_MOCK_<NAME>=1 mocks one (NAME in upper case,
// e.g. ALONGSIDE_MOCK_GROUNDER=1). Plumbing services (overlay, live) are real by default and mocked only per-service.
// Factories must not touch `s` at construction time: other services may not exist yet. Read `s.x` inside methods.
import type { Services, ServiceName } from '../shared/contracts'
import type { ServiceContext } from './context'
import { createCapture } from './capture'
import { createLiveBridge } from './live-bridge'
import { createOverlayController } from './overlay-controller'
import { createAgentsFromServices } from './agents/wire'
import { teachingBundle } from './teaching'
import { createFiles } from './files'
import { installStageTruth } from './showtime/stage-truth'
import { createGrounder, createLessonArchitect, createRouter, createScamAnalyst, createVerifier, geminiDeps, groundingPresetFromEnv } from './gemini'
import {
  mockAgents,
  mockArchitect,
  mockCapture,
  mockGrounder,
  mockLearner,
  mockLevels,
  mockLiveBridge,
  mockOverlay,
  mockRouter,
  mockRunner,
  mockScam,
  mockTeaching,
  mockVerifier,
} from './mocks'

const PLUMBING: ReadonlySet<ServiceName> = new Set<ServiceName>(['overlay', 'live'])

export function isMocked(name: ServiceName): boolean {
  if (process.env[`ALONGSIDE_MOCK_${name.toUpperCase()}`] === '1') return true
  return process.env.ALONGSIDE_MOCK === '1' && !PLUMBING.has(name)
}

// With no real factory yet, the mock is used regardless of flags.
function pick<T>(name: ServiceName, mock: () => T, real?: () => T): T {
  return real && !isMocked(name) ? real() : mock()
}

export function createServices(ctx: ServiceContext): Services {
  const s = {} as Services
  s.capture = pick('capture', () => mockCapture(), () => createCapture(ctx)) // OVERLAY
  s.overlay = pick('overlay', () => mockOverlay(ctx), () => createOverlayController(ctx)) // OVERLAY
  s.grounder = pick('grounder', () => mockGrounder(), () => createGrounder(geminiDeps(ctx, s), { preset: groundingPresetFromEnv() })) // SERVICES
  s.verifier = pick('verifier', () => mockVerifier(), () => createVerifier(geminiDeps(ctx, s))) // SERVICES
  s.architect = pick('architect', () => mockArchitect(), () => createLessonArchitect(geminiDeps(ctx, s), { grounder: { ground: (r) => s.grounder.ground(r), prefetch: (r) => s.grounder.prefetch?.(r) } })) // SERVICES
  s.scam = pick('scam', () => mockScam(), () => createScamAnalyst(geminiDeps(ctx, s))) // SERVICES
  s.router = pick('router', () => mockRouter(), () => createRouter(geminiDeps(ctx, s))) // SERVICES
  s.live = pick('live', () => mockLiveBridge(ctx), () => createLiveBridge(ctx)) // LIVE
  s.learner = pick('learner', () => mockLearner(), () => teachingBundle(ctx, s).learner) // TEACH
  s.levels = pick('levels', () => mockLevels(), () => teachingBundle(ctx, s).levels) // TEACH
  s.runner = pick('runner', () => mockRunner(ctx, s), () => teachingBundle(ctx, s).runner) // TEACH
  s.teaching = pick('teaching', () => mockTeaching(ctx), () => teachingBundle(ctx, s).teaching) // TEACH
  s.agents = pick('agents', () => mockAgents(ctx, s), () => createAgentsFromServices(ctx, s)) // AGENTS
  s.files = createFiles(ctx, isMocked('files') ? null : geminiDeps(ctx, s)) // FILES
  installStageTruth(s, { log: (m) => ctx.log('stage-truth', m), lessonActive: () => ctx.state.get().skill !== undefined, verifyNow: () => s.runner.verifyStep() }) // interactive demo only (ALONGSIDE_DEMO_DIRECTOR=1): the practice desktop answers for itself
  return s
}
