#!/usr/bin/env node
// Knack link audit: a READ-ONLY, end-to-end check of the links between the components of a RUNNING stack, before the demo is recorded.
//
//   node scripts/link-audit.mjs [--engine URL] [--agent URL] [--dashboard URL] [--sites URL] [--desktop-ext URL]
//                               [--expect live|mock|any] [--person ID] [--ingest private|off|URL] [--explain] [--json]
//
// Defaults: engine http://127.0.0.1:7700, agent http://127.0.0.1:7710, dashboard http://127.0.0.1:5173, sites http://127.0.0.1:7801 (the
// other two calculators are the next two ports). It prints one line per link, PASS, FAIL or SKIP, with the method and the exact URL path;
// never a response body, never a key, never a token. Exit code 1 if any link FAILs. SKIP is for a check the caller turned off or that does
// not apply (it says why); a SKIP never hides a failure the caller asked for.
//
// What it does NOT do: it sends no click, key or frame, starts no run, approves or rejects nothing, posts nothing to the stack under test
// and never reads the checkout's data/ directory. Every request is a GET, with two exceptions that are safe by construction:
//   * POST /evidence/explain (a computation over typed facts; in live mode it can reach a model, so it is skipped unless --explain);
//   * the extension ingest check, which writes events, and so runs against a THROWAWAY engine and throwaway sandbox sites that this script
//     starts on free ports in a temporary directory (a headless Chromium with the built extension visits a calculator page and the events
//     must appear in that engine). `--ingest URL` names an engine you say is private; `--ingest off` skips it.
//
// The links, in order: engine health and flags; agent health; the dashboard and its proxy to both; the data every demo scene reads (Home
// pointers, Needs you, Routines, Growth, Repeats, Forecasts, Firm, Evidence, Privacy ledger); the model layer and its context manifests
// (counts only); voice; the sandbox calculators; the desktop extension server; the extension ingest path.
import { existsSync, mkdtempSync, readFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { Procs, extensionDist, getJson, pythonOf, repoRootFrom, removeTree, sleep, startPrivateEngine, startPrivateSites, until } from './lib/private-stack.mjs'

// ---------------------------------------------------------------------------------------------- arguments
const argv = process.argv.slice(2)
const flag = (name, dflt) => {
  const i = argv.indexOf(`--${name}`)
  return i >= 0 ? (argv[i + 1] && !argv[i + 1].startsWith('--') ? argv[i + 1] : true) : dflt
}
if (argv.includes('--help') || argv.includes('-h')) {
  console.log(readFileSync(new URL(import.meta.url), 'utf8').split('\n').filter((l) => l.startsWith('//')).slice(0, 26).map((l) => l.replace(/^\/\/ ?/, '')).join('\n'))
  process.exit(0)
}
const strip = (u) => String(u).replace(/\/+$/, '')
const ENGINE = strip(flag('engine', 'http://127.0.0.1:7700'))
const AGENT = strip(flag('agent', 'http://127.0.0.1:7710'))
const DASH = strip(flag('dashboard', 'http://127.0.0.1:5173'))
const SITES_A = strip(flag('sites', 'http://127.0.0.1:7801'))
const sitePort = Number(new URL(SITES_A).port || 7801)
const SITES = { a: SITES_A, b: SITES_A.replace(/:\d+$/, `:${sitePort + 1}`), c: SITES_A.replace(/:\d+$/, `:${sitePort + 2}`) }
const DESKTOP_EXT = flag('desktop-ext', null)
const EXPECT = String(flag('expect', 'any'))
const INGEST = String(flag('ingest', 'private'))
const WITH_EXPLAIN = argv.includes('--explain')
const AS_JSON = argv.includes('--json')
if (!['live', 'mock', 'any'].includes(EXPECT)) {
  console.error('--expect must be live, mock or any')
  process.exit(2)
}
const repo = repoRootFrom(import.meta.url)

// ---------------------------------------------------------------------------------------------- the machinery
const results = []
let group = ''
const section = (name) => {
  group = name
  if (!AS_JSON) console.log(`\n${name}`)
}
/** Run one link check. `fn` returns { ok, detail } or { skip: 'why' }. Anything it throws is a FAIL that says what, never what came back. */
async function link(method, path, fn) {
  let r
  try {
    r = await fn()
  } catch (e) {
    const why = e?.name === 'AbortError' ? 'timed out' : String(e?.cause?.code ?? e?.message ?? e).slice(0, 100)
    r = { ok: false, detail: `no answer (${why})` }
  }
  const status = r.skip ? 'SKIP' : r.ok ? 'PASS' : 'FAIL'
  const row = { group, status, method, path, detail: r.skip ?? r.detail ?? '' }
  results.push(row)
  if (!AS_JSON) console.log(`  ${status}  ${method.padEnd(4)} ${path.padEnd(52)} ${row.detail}`)
  return r
}
const get = (base, path, headers = {}, ms = 20000) => getJson(base + path, { headers: { accept: 'application/json', ...headers } }, ms)
const keys = (o) => (o && typeof o === 'object' ? Object.keys(o) : [])
const plural = (n, w) => `${n} ${w}${n === 1 ? '' : 's'}`
const yn = (v) => (v ? 'yes' : 'no')

// ---------------------------------------------------------------------------------------------- ENGINE
let engineHealth = null
let identity = null
const ENGINE_LAYERS = ['privacy', 'localmodel', 'calendar', 'git', 'proactive', 'cue', 'awareness', 'evidence', 'attention', 'hitlist', 'insights']

section('ENGINE')
await link('GET', '/health', async () => {
  const r = await get(ENGINE, '/health')
  if (r.status !== 200 || !r.body?.ok) return { ok: false, detail: `status ${r.status}` }
  engineHealth = r.body
  const live = r.body.mock === false
  const ids = r.body.models ?? {}
  const idsSet = ['planner', 'fast', 'computer_use'].every((k) => typeof ids[k] === 'string' && ids[k] && ids[k] !== '(not set)')
  const mode = `mock=${r.body.mock}, provider=${r.body.provider}`
  if (EXPECT === 'live') {
    if (!live) return { ok: false, detail: `${mode}: expected live models (start with make live, and check the Gemini key line in .env)` }
    if (r.body.provider !== 'gemini') return { ok: false, detail: `${mode}: expected provider gemini` }
    if (!idsSet) return { ok: false, detail: `${mode}: a model role has no id set (planner, fast, computer_use)` }
    if (r.body.key_present === false) return { ok: false, detail: `${mode}: no key present` }
  }
  if (EXPECT === 'mock' && live) return { ok: false, detail: `${mode}: expected mock mode` }
  return { ok: true, detail: `${mode}, roles with an id: ${idsSet ? 'planner, fast, computer_use' : 'not all (mock)'}${EXPECT === 'any' ? ' (expectation: any)' : ''}` }
})
await link('GET', '/health (extension layers)', async () => {
  if (!engineHealth) return { ok: false, detail: 'no health answer' }
  const ext = engineHealth.extensions ?? {}
  const off = ENGINE_LAYERS.filter((k) => ext[k] !== true)
  const extra = keys(ext).filter((k) => !ENGINE_LAYERS.includes(k))
  if (off.length || engineHealth.x_flag !== true) return { ok: false, detail: `layers not on: ${off.join(', ') || 'none'}; x_flag=${engineHealth.x_flag} (an explicit UNDERSTUDY_X=0 or a missing module turns a layer off)` }
  return { ok: true, detail: `all ${ENGINE_LAYERS.length} layers true (${ENGINE_LAYERS.join(', ')}), x_flag true${extra.length ? `; also ${extra.join(', ')}` : ''}` }
})
await link('GET', '/health (engine sees the agent)', async () => {
  if (!engineHealth) return { ok: false, detail: 'no health answer' }
  const warn = (engineHealth.warnings ?? []).join(', ')
  return engineHealth.services?.agent === true ? { ok: true, detail: `services.agent true${warn ? `; warnings: ${warn}` : ''}` } : { ok: false, detail: 'services.agent is false: the engine cannot reach the agent service (AGENT_PORT must match)' }
})
await link('GET', '/identity', async () => {
  const r = await get(ENGINE, '/identity')
  identity = r.body
  if (r.status !== 200 || !identity?.person) return { ok: false, detail: `status ${r.status}: no person set up (the first-run or the demo seed makes one)` }
  return { ok: true, detail: `person set (${identity.person}), role ${identity.role}` }
})
const PERSON = String(flag('person', identity?.person ?? 'p_learn01'))
const Q = `person=${encodeURIComponent(PERSON)}`
await link('GET', '/kill', async () => {
  const r = await get(ENGINE, '/kill')
  if (r.status !== 200) return { ok: false, detail: `status ${r.status}` }
  return r.body?.killed === false ? { ok: true, detail: 'the stop flag is clear' } : { ok: false, detail: 'the stop flag is SET: nothing will run until it is cleared (Resume in the app, or POST /kill/clear by the worker)' }
})
await link('GET', '/study/mode', async () => {
  const r = await get(ENGINE, '/study/mode')
  if (r.status !== 200) return { ok: false, detail: `status ${r.status}` }
  return r.body?.active === false ? { ok: true, detail: 'no study mode is forcing the coach (a left-over one would change what the ring does)' } : { ok: false, detail: 'a study mode is ACTIVE: the coach is being forced to a fixed help level (POST /study/mode/clear)' }
})

// ---------------------------------------------------------------------------------------------- AGENT
section('AGENT')
let agentHealth = null
await link('GET', '/health', async () => {
  const r = await get(AGENT, '/health')
  if (r.status !== 200 || !r.body?.ok) return { ok: false, detail: `status ${r.status}` }
  agentHealth = r.body
  const state = r.body.supervisor?.state
  const ext = r.body.extensions ?? {}
  const need = ['agents', 'models'].filter((k) => ext[k] !== true)
  if (need.length) return { ok: false, detail: `routers not loaded: ${need.join(', ')}` }
  if (state !== 'idle') return { ok: false, detail: `supervisor ${state}: a run is active or stopped (expected idle before a demo)` }
  if (r.body.voice !== true) return { ok: false, detail: 'the voice router is not loaded (no spoken lines)' }
  return { ok: true, detail: `supervisor idle, agents and models and voice loaded, sandbox ${yn(r.body.sandbox)}, mock=${r.body.mock}, live router ${yn(ext.live)} (false is by design: Live voice runs in the desktop app)` }
})
await link('GET', '/health (agent and engine mode agree)', async () => {
  if (!engineHealth || !agentHealth) return { ok: false, detail: 'missing a health answer' }
  return engineHealth.mock === agentHealth.mock ? { ok: true, detail: `both mock=${agentHealth.mock}` } : { ok: false, detail: `engine mock=${engineHealth.mock} but agent mock=${agentHealth.mock}: the two were started with different UNDERSTUDY_MOCK` }
})
await link('GET', '/health (sandbox sites reachable from the agent)', async () => (agentHealth?.sandbox === true ? { ok: true, detail: 'sandbox true' } : { ok: false, detail: 'sandbox false: the agent cannot reach the calculators on 7801 (start them: scripts/dev.sh)' }))
let modelsStatus = null
await link('GET', '/models/status', async () => {
  const r = await get(AGENT, '/models/status')
  if (r.status !== 200 || !r.body) return { ok: false, detail: `status ${r.status}` }
  modelsStatus = r.body
  const roles = keys(r.body.roles)
  const gem = r.body.providers?.gemini
  if (r.body.config_error) return { ok: false, detail: 'config_error is set (the routing table did not load)' }
  if (EXPECT === 'live') {
    if (!gem?.configured || !gem?.enabled_by_flag) return { ok: false, detail: `gemini configured=${gem?.configured}, enabled_by_flag=${gem?.enabled_by_flag}` }
    const bad = Object.entries(r.body.boot ?? {}).filter(([, v]) => v && v.ok === false).map(([k]) => k)
    if (bad.length) return { ok: false, detail: `boot check failed for ${bad.join(', ')} (a model id the key cannot use)` }
    if (gem.health === 'down' || gem.health === 'degraded') return { ok: false, detail: `gemini health ${gem.health}` }
  }
  return { ok: true, detail: `roles ${roles.join(', ')}; gemini configured=${yn(gem?.configured)} health=${gem?.health}; boot checks ${plural(keys(r.body.boot).length, 'provider')}; meter ${plural((r.body.meter ?? []).length, 'row')}` }
})
await link('GET', '/models/status (ledger coverage)', async () => {
  const c = modelsStatus?.ledger_coverage
  if (!c) return { ok: false, detail: 'no ledger_coverage block' }
  return c.all_provider_calls_ledgered === true ? { ok: true, detail: `every provider call is ledgered (unledgered ${c.unledgered_calls}; ledger rows ${c.ledger_rows?.calls ?? '?'})` } : { ok: false, detail: `${c.unledgered_calls} provider call(s) have no ledger row` }
})
await link('GET', '/models/status (context manifests, counts only)', async () => {
  const rows = modelsStatus?.meter ?? []
  const calls = rows.reduce((n, r) => n + (r.n ?? 0), 0)
  const withManifest = rows.reduce((n, r) => n + (r.calls_with_manifest ?? 0), 0)
  const sections = new Set(rows.flatMap((r) => keys(r.mean_section_tokens)))
  const dropped = rows.reduce((n, r) => n + (r.dropped_items ?? 0), 0)
  if (!modelsStatus) return { ok: false, detail: 'no models status' }
  const note = calls === 0 ? 'no model call has been made yet in this process' : `${withManifest} of ${calls} call(s) carried a context manifest`
  return { ok: true, detail: `${note}; sections seen: ${sections.size ? [...sections].join(', ') : 'none'}; items dropped by budgets: ${dropped}` }
})
await link('GET', '/voice/status', async () => {
  const r = await get(AGENT, '/voice/status')
  if (r.status !== 200) return { ok: false, detail: `status ${r.status}` }
  const live = engineHealth && engineHealth.mock === false
  if (!r.body.enabled) return { ok: false, detail: 'voice is not enabled (UNDERSTUDY_VOICE)' }
  if (live && !r.body.voice_configured) return { ok: false, detail: 'live mode but no spoken voice is configured (ElevenLabs key and voice id): fixed lines would be silent' }
  return { ok: true, detail: `enabled, mock=${r.body.mock}, voice configured=${yn(r.body.voice_configured)}, free text refused=${yn(!r.body.free_text)}` }
})
await link('GET', '/voice/lines', async () => {
  const r = await get(AGENT, '/voice/lines')
  const lines = (r.body?.data ?? []).map((l) => l.line_id)
  if (r.status !== 200 || !lines.length) return { ok: false, detail: `status ${r.status}, ${lines.length} lines` }
  // The Hey Knack path speaks four fixed lines by id (apps/desktop/src/main/wake/texts.ts SPOKEN_LINES). An id the agent does not know is a 422 and silence.
  let wanted = ['wake.show_instead', 'wake.done', 'wake.did_not_work', 'wake.stopped']
  const texts = join(repo, 'apps/desktop/src/main/wake/texts.ts')
  if (existsSync(texts)) {
    const src = readFileSync(texts, 'utf8')
    const block = /SPOKEN_LINES[^{]*\{([\s\S]*?)\n\}/.exec(src)?.[1] ?? ''
    const found = [...block.matchAll(/'(wake\.[a-z_]+)'\s*:/g)].map((m) => m[1])
    if (found.length) wanted = found
  }
  const missing = wanted.filter((id) => !lines.includes(id))
  return missing.length
    ? { ok: false, detail: `${lines.length} lines, but the agent does not know ${missing.join(', ')}: Hey Knack asks for them by id and gets a 422 (add them to services/agent/understudy_agent/voice/lines.py)` }
    : { ok: true, detail: `${lines.length} fixed lines, including the ${wanted.length} that Hey Knack speaks` }
})

await link('GET', '/desktop/click', async () => {
  // Hey Knack's "click when I say so" asks the agent for ONE real click through this route. It is not built on purpose: the answer is 404 and the
  // desktop reports route_missing and clicks nothing until the owner's supervised R1 run (D52). A GET never clicks whatever the route is.
  const r = await get(AGENT, '/desktop/click', {}, 5000)
  if (r.status === 404 || r.status === 405) return { skip: "expected, closed by design: do_it_for_me answers route_missing and clicks nothing until the owner's supervised R1 run (D52)" }
  return { ok: true, detail: `status ${r.status}: the route exists now; it must still refuse without the rung record and the one-time token` }
})

// ---------------------------------------------------------------------------------------------- DASHBOARD
section('DASHBOARD')
await link('GET', '/', async () => {
  const r = await get(DASH, '/', { accept: 'text/html' })
  if (r.status !== 200) return { ok: false, detail: `status ${r.status}` }
  const title = /<title>([^<]*)<\/title>/i.exec(r.text)?.[1] ?? ''
  const knack = /knack/i.test(title)
  return knack ? { ok: true, detail: `serves the app shell (title mentions Knack), ${r.bytes} bytes` } : { ok: false, detail: `serves a page whose title does not name Knack (${title.slice(0, 40)}): an old build?` }
})
await link('GET', '/engine/health (dashboard proxy)', async () => {
  const r = await get(DASH, '/engine/health')
  if (r.headers.get('x-understudy-proxy-token') === 'missing') return { ok: false, detail: 'the proxy has no per-boot token (data/.token missing): restart the stack' }
  if (r.status !== 200 || !r.body?.ok) return { ok: false, detail: `status ${r.status}: the proxy does not reach the engine (ENGINE_PORT)` }
  return engineHealth && r.body.mock !== engineHealth.mock ? { ok: false, detail: 'the proxy reaches a DIFFERENT engine than --engine (mock differs)' } : { ok: true, detail: `reaches the engine, mock=${r.body.mock}` }
})
await link('GET', '/agent/health (dashboard proxy)', async () => {
  const r = await get(DASH, '/agent/health')
  if (r.status !== 200 || !r.body?.ok) return { ok: false, detail: `status ${r.status}: the proxy does not reach the agent (AGENT_PORT)` }
  return { ok: true, detail: `reaches the agent, supervisor ${r.body.supervisor?.state}` }
})
await link('GET', '/engine/insights/admin/firm (proxy adds the token)', async () => {
  const r = await get(DASH, '/engine/insights/admin/firm', { 'x-understudy-role': 'admin' }, 60000)
  if (r.status === 403) return { ok: false, detail: `403 ${r.body?.error?.code ?? ''}: the proxy did not add the per-boot token (the dashboard and the services use different data directories)` }
  if (r.status !== 200) return { ok: false, detail: `status ${r.status}` }
  const users = r.body?.data?.users ?? r.body?.data?.rows ?? r.body?.data?.people
  return { ok: true, detail: `Firm data answers through the proxy (${r.bytes} bytes; origin ${r.body?.meta?.origin}${Array.isArray(users) ? `; ${plural(users.length, 'row')}` : ''})` }
})

// ---------------------------------------------------------------------------------------------- DATA THE SCENES READ
section('DATA THE SCENES READ (engine; person ' + PERSON + ')')
await link('GET', '/insights/worker', async () => {
  const r = await get(ENGINE, `/insights/worker?${Q}`)
  if (r.status !== 200) return { ok: false, detail: `status ${r.status}` }
  const d = r.body?.data ?? {}
  const ps = d.pointers ?? []
  if (d.status !== 'ok' || !ps.length) return { ok: false, detail: `status ${d.status}, ${plural(ps.length, 'pointer')}: Home would show its empty state, not a hero (seed the demo)` }
  return { ok: true, detail: `${plural(ps.length, 'pointer')} (kinds: ${[...new Set(ps.map((p) => p.kind))].join(', ')}); origin ${r.body.meta?.origin}, badge "${r.body.meta?.badge}"` }
})
await link('GET', '/queue', async () => {
  const r = await get(ENGINE, '/queue')
  const items = r.body?.data ?? []
  if (r.status !== 200) return { ok: false, detail: `status ${r.status}` }
  const pending = items.filter((i) => i.status === 'pending')
  const irr = pending.filter((i) => i.risk_class === 'irreversible' || i.kind === 'irreversible_step').length
  return pending.length ? { ok: true, detail: `${plural(pending.length, 'pending item')} (${irr} irreversible): Needs you has something to show` } : { ok: false, detail: 'nothing pending: Needs you is empty (the overnight story is not seeded)' }
})
await link('GET', '/briefing', async () => {
  const r = await get(ENGINE, `/briefing?${Q}`)
  const cards = r.body?.data?.cards ?? []
  if (r.status !== 200) return { ok: false, detail: `status ${r.status}` }
  return cards.length ? { ok: true, detail: `${plural(cards.length, 'card')} (cap ${r.body.data.cap})` } : { ok: false, detail: 'no briefing cards' }
})
await link('GET', '/memory/proposals', async () => {
  const r = await get(ENGINE, '/memory/proposals')
  if (r.status !== 200 || !Array.isArray(r.body)) return { ok: false, detail: `status ${r.status}` }
  return r.body.length ? { ok: true, detail: `${plural(r.body.length, 'rule proposal')} waiting (Needs you row)` } : { ok: false, detail: 'no rule proposal waiting' }
})
await link('GET', '/routines', async () => {
  const r = await get(ENGINE, '/routines', {}, 40000)
  const rs = r.body?.data ?? []
  if (r.status !== 200) return { ok: false, detail: `status ${r.status}` }
  const proposed = rs.filter((x) => x.status === 'proposed').length
  const compiled = rs.filter((x) => x.driver === 'compiled').length
  return rs.length ? { ok: true, detail: `${plural(rs.length, 'routine')}, ${proposed} proposed, ${compiled} with a compiled bundle (needed for the agent run)` } : { ok: false, detail: 'no routines found (the finder produced none)' }
})
await link('GET', '/growth', async () => {
  const r = await get(ENGINE, `/growth?${Q}`, {}, 40000)
  if (r.status !== 200) return { ok: false, detail: `status ${r.status}` }
  const d = r.body?.data ?? {}
  if (!d.readiness?.ready) return { ok: false, detail: `${d.occurrences?.total ?? 0} occurrence(s), ${d.readiness?.needed ?? 10} needed: Growth shows its empty state, no curve (the demo seed fills it; re-run it with --reset)` }
  return { ok: true, detail: `${d.occurrences.total} occurrences, curve of ${plural((d.curve ?? []).length, 'point')}, origin ${r.body.meta?.origin}/${d.origin_detail}` }
})
await link('GET', '/hitlist', async () => {
  const r = await get(ENGINE, `/hitlist?${Q}`, {}, 40000)
  const rows = r.body?.data?.rows ?? []
  if (r.status !== 200) return { ok: false, detail: `status ${r.status}` }
  return rows.length ? { ok: true, detail: `state ${r.body.data.state}, ${plural(rows.length, 'repeat')} (Routines, Could automate)` } : { ok: false, detail: `state ${r.body?.data?.state}: no repeats listed` }
})
await link('GET', '/offhours/report', async () => {
  const r = await get(ENGINE, '/offhours/report?since=2020-01-01T00:00:00Z')
  if (r.status !== 200) return { ok: false, detail: `status ${r.status}` }
  const n = (k) => (r.body?.[k] ?? []).length
  return n('ran') + n('queued') ? { ok: true, detail: `overnight story: ${n('ran')} ran, ${n('queued')} queued, ${n('failed')} failed, ${n('yielded')} yielded` } : { ok: false, detail: 'the overnight story is empty' }
})
await link('GET', '/coach/next?dry=1', async () => {
  const r = await get(ENGINE, `/coach/next?${Q}&dry=1`)
  if (r.status !== 200) return { ok: false, detail: `status ${r.status}` }
  return { ok: true, detail: `action ${r.body?.data?.action} (a dry poll: it keeps nothing and does not advance the quiet period)` }
})
await link('GET', '/coach/state', async () => {
  const r = await get(ENGINE, `/coach/state?${Q}`)
  if (r.status !== 200) return { ok: false, detail: `status ${r.status}` }
  return { ok: true, detail: `level ${r.body?.level}, chip ${r.body?.chip}, case ${r.body?.case} of ${r.body?.cases_total}` }
})
await link('GET', '/cue/next?dry=1', async () => {
  const r = await get(ENGINE, `/cue/next?${Q}&dry=1`)
  if (r.status !== 200) return { ok: false, detail: `status ${r.status}${r.body?.error?.code ? ` ${r.body.error.code}` : ''}` }
  return { ok: true, detail: `kind ${r.body?.data?.kind} (a dry poll)` }
})
await link('GET', '/attention/next?peek=1', async () => {
  const r = await get(ENGINE, `/attention/next?${Q}&peek=1`)
  if (r.status !== 200) return { ok: false, detail: `status ${r.status}${r.body?.error?.code ? ` ${r.body.error.code}` : ''}` }
  const d = r.body?.data ?? {}
  return { ok: true, detail: `active ${yn(d.active)}, item ${d.item ? 'present' : 'none'}, digest ready ${yn(d.digest_ready)} (a peek delivers nothing)` }
})
await link('GET', '/evidence/packet', async () => {
  const r = await get(ENGINE, `/evidence/packet?${Q}`)
  if (r.status !== 200) return { ok: false, detail: `status ${r.status}${r.body?.error?.code ? ` ${r.body.error.code}` : ''}` }
  const d = r.body?.data ?? {}
  const n = (x) => (Array.isArray(x) ? x.length : keys(x).length)
  return { ok: true, detail: `${plural(n(d.blocks), 'block')}, ${plural(n(d.facts), 'fact')}, ${plural(n(d.limitations), 'limitation')}` }
})
await link('POST', '/evidence/explain', async () => {
  const live = engineHealth && engineHealth.mock === false
  if (live && !WITH_EXPLAIN) return { skip: 'live mode: it can reach a model and write a ledger row; pass --explain to include it' }
  const r = await getJson(`${ENGINE}/evidence/explain`, { method: 'POST', headers: { 'content-type': 'application/json', 'x-understudy-actor': 'worker' }, body: JSON.stringify({ person: PERSON, question: 'where did my time go' }) }, 60000)
  if (r.status !== 200) return { ok: false, detail: `status ${r.status}${r.body?.error?.code ? ` ${r.body.error.code}` : ''}` }
  const d = r.body?.data ?? r.body ?? {}
  return { ok: true, detail: `answered; source ${d.source ?? d.route ?? '?'}, number check ${d.provenance_ok ?? d.checked ?? 'n/a'}` }
})
await link('GET', '/privacy/summary', async () => {
  const r = await get(ENGINE, '/privacy/summary')
  if (r.status !== 200) return { ok: false, detail: `status ${r.status}` }
  const d = r.body?.data ?? {}
  const sent = (x) => (typeof x === 'object' && x ? `${x.sent ?? 0} sent, ${x.blocked ?? 0} blocked` : '?')
  return { ok: true, detail: `${d.calls ?? 0} ledgered call(s) (${d.mock_calls ?? 0} mock, ${d.worker_requested_calls ?? 0} worker-requested); frames ${sent(d.images)}; audio turns ${sent(d.audio)}` }
})
await link('GET', '/privacy/ledger', async () => {
  const r = await get(ENGINE, '/privacy/ledger')
  if (r.status !== 200) return { ok: false, detail: `status ${r.status}` }
  const n = (r.body?.data ?? []).length
  return { ok: true, detail: `${plural(n, 'row')} (metadata only)${n === 0 ? ': empty. In live mode rows appear as models are called; the Privacy scene says "nothing sent yet" until then' : ''}` }
})
await link('GET', '/eval/report', async () => {
  const r = await get(ENGINE, '/eval/report', {}, 60000)
  if (r.status !== 200) return { ok: false, detail: `status ${r.status}: the Evidence page has no report (make eval FAST=1)` }
  const age = r.body?.generated_at ? Math.round((Date.now() - Date.parse(r.body.generated_at)) / 3600000) : null
  return { ok: true, detail: `${plural((r.body?.evidence_map ?? []).length, 'section')}, ${plural((r.body?.findings ?? []).length, 'finding')}, generated ${age === null ? '?' : `${age} h ago`} (mock=${r.body?.mock})` }
})
await link('GET', '/insights/admin/firm', async () => {
  const r = await get(ENGINE, '/insights/admin/firm', { 'x-understudy-role': 'admin' })
  // Direct to the engine there is no token, so the admin gate must refuse. A 200 here would mean the Admin data is open to any local page.
  if (r.status === 200) return { ok: false, detail: '200 without the per-boot token: the admin gate is OPEN' }
  return r.status === 403 ? { ok: true, detail: `403 ${r.body?.error?.code} (the gate holds; the dashboard proxy supplies the token)` } : { ok: false, detail: `status ${r.status}` }
})
await link('GET', '/genome/t_entitlement_check', async () => {
  // No person: the screen's default case (a novice and the nearest expert). The demo person's own trace is the coach's, not the ribbon's.
  const r = await get(ENGINE, '/genome/t_entitlement_check', {}, 60000)
  if (r.status !== 200) return { ok: false, detail: `status ${r.status}${r.body?.error?.code ? ` ${r.body.error.code}` : ''}` }
  return { ok: true, detail: `work ribbon data answers (origin ${r.body?.meta?.origin}, n ${r.body?.meta?.n} ${r.body?.meta?.n_unit})` }
})
await link('GET', '/hazard/p_nov03', async () => {
  // An apprentice persona in the synthetic data (the stuck model's series for one novice).
  const r = await get(ENGINE, '/hazard/p_nov03', {}, 60000)
  if (r.status !== 200) return { ok: false, detail: `status ${r.status}${r.body?.error?.code ? ` ${r.body.error.code}` : ''}` }
  return { ok: true, detail: `stuck-model reading answers (${r.bytes} bytes; origin ${r.body?.meta?.origin})` }
})
await link('GET', '/localmodel/status', async () => {
  const r = await get(ENGINE, '/localmodel/status')
  if (r.status !== 200) return { ok: false, detail: `status ${r.status}` }
  const d = r.body?.data ?? {}
  return { ok: true, detail: `local model enabled=${yn(d.enabled)}, running=${yn(d.running)}, mode ${d.mode} (rules fallback when it is not running)` }
})

// ---------------------------------------------------------------------------------------------- SANDBOX
section('SANDBOX CALCULATORS')
for (const [id, base] of Object.entries(SITES)) {
  await link('GET', `${new URL(base).host}/healthz`, async () => {
    const r = await get(base, '/healthz')
    return r.status === 200 && r.body?.site === id ? { ok: true, detail: `site ${id} answers` } : { ok: false, detail: `status ${r.status}: site ${id} is not running (scripts/dev.sh starts 7801 to 7803)` }
  })
}
await link('GET', `${new URL(SITES.a).host}/step/1`, async () => {
  const r = await get(SITES.a, '/step/1', { accept: 'text/html' })
  return r.status === 200 && /Question 1 of 4/.test(r.text) ? { ok: true, detail: 'calculator A first question page' } : { ok: false, detail: `status ${r.status}` }
})
await link('GET', `${new URL(SITES.a).host}/casenote`, async () => {
  const r = await get(SITES.a, '/casenote', { accept: 'text/html' })
  return r.status === 200 && /Case note/.test(r.text) ? { ok: true, detail: 'case-note page' } : { ok: false, detail: `status ${r.status}` }
})
await link('GET', `${new URL(SITES.a).host}/__state`, async () => {
  const r = await get(SITES.a, '/__state')
  if (r.status !== 200) return { ok: false, detail: `status ${r.status}` }
  const subs = (r.body?.submissions ?? []).length
  const notes = keys(r.body?.notes).length
  return subs === 0 ? { ok: true, detail: `${plural(notes, 'saved note')}, 0 submissions (a demo starts with 0 submissions and the sites reset)` } : { ok: false, detail: `${subs} submission(s) already recorded: reset the sites (POST /__reset) before recording` }
})

// ---------------------------------------------------------------------------------------------- DESKTOP
section('DESKTOP APP')
await link('GET', '/ext/status', async () => {
  if (!DESKTOP_EXT) return { skip: 'pass --desktop-ext http://127.0.0.1:7720 (the app\'s extension server) once Knack is open' }
  const r = await get(strip(DESKTOP_EXT), '/ext/status', {}, 5000)
  if (r.status !== 200) return { ok: false, detail: `status ${r.status}` }
  const seen = r.body?.extension_seen_ms
  return { ok: true, detail: `the app's extension server answers; extension last seen ${seen === null ? 'never' : `${Math.round(seen / 1000)} s ago`}; ${r.body?.pending ?? 0} grounding request(s) pending` }
})

// ---------------------------------------------------------------------------------------------- EXTENSION INGEST
section('EXTENSION INGEST (a headless Chromium with the built extension)')
await ingest()

// ---------------------------------------------------------------------------------------------- summary
const count = (s) => results.filter((r) => r.status === s).length
const summary = { pass: count('PASS'), fail: count('FAIL'), skip: count('SKIP') }
if (AS_JSON) console.log(JSON.stringify({ engine: ENGINE, agent: AGENT, dashboard: DASH, expect: EXPECT, person: PERSON, summary, results }, null, 2))
else {
  console.log(`\n${summary.pass} PASS, ${summary.fail} FAIL, ${summary.skip} SKIP`)
  for (const r of results.filter((x) => x.status === 'FAIL')) console.log(`  FAIL  ${r.method} ${r.path}: ${r.detail}`)
}
process.exit(summary.fail ? 1 : 0)

// ---------------------------------------------------------------------------------------------- the ingest check
async function ingest() {
  if (INGEST === 'off') {
    await link('POST', '/events (extension to engine)', async () => ({ skip: '--ingest off' }))
    return
  }
  const procs = new Procs()
  let context = null
  let priv = null
  let root = null
  let userData = null
  try {
    let playwright
    try {
      playwright = await import('playwright')
    } catch {
      await link('POST', '/events (extension to engine)', async () => ({ ok: false, detail: 'playwright is not installed (npm install at the repo root)' }))
      return
    }
    let dist
    try {
      dist = extensionDist(repo)
      pythonOf(repo)
    } catch (e) {
      await link('POST', '/events (extension to engine)', async () => ({ ok: false, detail: String(e.message).slice(0, 160) }))
      return
    }
    let engine, sitesA, person
    if (INGEST === 'private') {
      priv = await startPrivateEngine({ repo, procs, person: 'p_audit', onboard: true })
      root = priv.root
      const sites = await startPrivateSites({ repo, procs })
      engine = priv.engine
      sitesA = sites.urls.a
      person = 'p_audit'
    } else {
      engine = strip(INGEST)
      sitesA = SITES.a
      person = PERSON
    }
    const outcome = await link('POST', '/events (extension to engine)', async () => {
      const before = (await get(engine, `/events?partition=real&person=${person}&limit=50000`)).body?.events?.length ?? 0
      userData = mkdtempSync(join(tmpdir(), 'knack-ingest-'))
      context = await playwright.chromium.launchPersistentContext(userData, {
        channel: 'chromium',
        headless: true,
        args: [`--disable-extensions-except=${dist}`, `--load-extension=${dist}`, '--no-first-run', '--no-default-browser-check'],
      })
      let [sw] = context.serviceWorkers()
      if (!sw) sw = await context.waitForEvent('serviceworker', { timeout: 20000 })
      await until(() => sw.evaluate(async () => Boolean((await chrome.storage.local.get('salt')).salt)), 15000, 'extension init')
      await sw.evaluate(
        async ({ engine, person }) => {
          await chrome.storage.local.set({ config: { capturing: true, person, role: 'benefits-processor', engine_url: engine, desktop_url: 'http://127.0.0.1:9' } })
        },
        { engine, person },
      )
      const page = await context.newPage()
      await page.goto(`${sitesA}/step/1`)
      await sleep(800)
      await page.click('main form button[type=submit]').catch(() => undefined) // a click on the first question's button: one more event, no field values
      await sleep(1500)
      let rows = []
      const got = await until(
        async () => {
          rows = (await get(engine, `/events?partition=real&person=${person}&limit=50000`)).body?.events ?? []
          return rows.length > before
        },
        25000,
        'events from the extension',
        500,
      ).catch(() => false)
      if (!got) return { ok: false, detail: 'no event reached the engine within 25 s (capture off for this person, the engine refused the extension origin, or the extension is not loaded)' }
      const types = {}
      for (const e of rows.slice(before)) types[e.type] = (types[e.type] ?? 0) + 1
      const textual = rows.slice(before).filter((e) => JSON.stringify(e).match(/"(url|text|value|href|title|innerText)"\s*:/)).length
      if (textual) return { ok: false, detail: `${textual} event(s) carry a url, text or value field (L0 capture must not)` }
      return { ok: true, detail: `${rows.length - before} event(s) reached ${INGEST === 'private' ? 'a throwaway engine' : 'the named engine'} (${Object.entries(types).map(([k, v]) => `${k} ${v}`).join(', ')}); 0 carried a url, text or value field` }
    })
    void outcome
  } catch (e) {
    if (!results.some((r) => r.path === '/events (extension to engine)')) {
      await link('POST', '/events (extension to engine)', async () => ({ ok: false, detail: String(e?.message ?? e).slice(0, 200) }))
    }
  } finally {
    await context?.close().catch(() => undefined)
    await procs.stopAll()
    if (root) removeTree(root)
    if (userData) removeTree(userData)
  }
}
