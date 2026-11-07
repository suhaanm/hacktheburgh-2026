// Drives one full video_call lesson against an ALREADY RUNNING app (no voice): wake -> start_lesson -> (learner does each step on the
// demo stage) -> verify -> end_lesson, printing level/skill/chip as it goes. Run the app first, under the lock, with the QA hooks:
//   ALONGSIDE_DEV_STAGE=1 ALONGSIDE_DEBUG_PORT=7777 ALONGSIDE_DEV_PORT=7778 scripts/electron-lock.sh ROLE npx electron-vite preview   (needs `npm run stage` too)
// Then:  node tests/e2e/drive-lesson.mjs [--hold 20000] [--no-stage] [--goal "Join a video call with Lily"]
const DEBUG = process.env.E2E_DEBUG_URL || `http://127.0.0.1:${process.env.ALONGSIDE_DEBUG_PORT || 7777}`
const DEV = process.env.E2E_DEV_URL || `http://127.0.0.1:${process.env.ALONGSIDE_DEV_PORT || 7778}`
const argv = process.argv.slice(2)
const opt = (name, fallback) => {
  const i = argv.indexOf(`--${name}`)
  return i >= 0 && argv[i + 1] ? argv[i + 1] : fallback
}
const useStage = !argv.includes('--no-stage')
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const post = async (base, route, body) => (await fetch(base + route, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body ?? {}) })).json()
const get = async (base, route) => (await fetch(base + route)).json()
const tool = (name, args) => post(DEBUG, '/tool', { name, args: args ?? {} })
const brief = async () => {
  const s = await get(DEBUG, '/state')
  return `phase=${s.phase} level=${s.level} step=${s.skill ? `${s.skill.step}/${s.skill.stepCount}` : '-'}`
}

const t0 = Date.now()
const stamp = () => `+${((Date.now() - t0) / 1000).toFixed(1)}s`
console.log(stamp(), 'health', await get(DEBUG, '/health'))
if (useStage) {
  await post(DEV, '/dev/stage/open')
  await post(DEV, '/dev/stage/call', { fn: 'setStep', args: ['video_call', 0] })
  console.log(stamp(), 'stage open')
}
await post(DEBUG, '/settings', { patch: { demoMode: true } })
await post(DEBUG, '/wake', { personaId: 'marcus' })
await sleep(800)
console.log(stamp(), 'wake ->', await brief())

const started = await tool('start_lesson', { goal: opt('goal', 'Join a video call with Lily') })
console.log(stamp(), 'start_lesson', JSON.stringify(started), '->', await brief())

for (let i = 1; i <= (started.stepCount ?? 0); i++) {
  await sleep(1200)
  if (useStage) await post(DEV, '/dev/stage/call', { fn: 'setStep', args: ['video_call', Math.min(i, 5)] })
  const before = (await get(DEBUG, '/state')).skill?.step
  const verdict = await tool('verify_step', { expected_outcome: 'the step is done' })
  console.log(stamp(), `step ${i}: verified=${verdict.completed} (${(verdict.evidence ?? verdict.error ?? '').slice(0, 70)})`)
  const after = (await get(DEBUG, '/state')).skill?.step
  if (after !== undefined && after === before) console.log(stamp(), '  step_done', JSON.stringify(await tool('step_done', {})))
  console.log(stamp(), '  ', await brief())
  if (!(await get(DEBUG, '/state')).skill) break
}
console.log(stamp(), 'end_lesson', JSON.stringify(await tool('end_lesson', { summary: 'Joined a video call with Lily.', teachBackScore: 0.9, confidence: 4 })))
const learner = await get(DEV, '/dev/learner')
console.log(stamp(), 'attempts recorded:', learner.attempts?.length, 'video_call skill:', JSON.stringify(learner.skills?.video_call))
console.log(stamp(), 'final', await brief())
const hold = Number(opt('hold', 0))
if (hold) {
  console.log(stamp(), `holding ${hold} ms so you can look at the dock`)
  await sleep(hold)
}
await post(DEBUG, '/stop')
