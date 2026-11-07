#!/usr/bin/env node
// Submission readiness gate. Usage: npm run submit-check [-- --fast]   (--fast skips typecheck/tests/build)
// Prints a PASS/WARN/FAIL table; exits 1 on any FAIL. Never prints secret values.
import { spawnSync } from 'node:child_process'
import { existsSync, readFileSync, statSync, readdirSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
process.chdir(root)
const fast = process.argv.includes('--fast')
const rows = []
const add = (name, status, detail = '') => rows.push({ name, status, detail })
const run = (cmd, args, opts = {}) => spawnSync(cmd, args, { encoding: 'utf8', maxBuffer: 256 * 1024 * 1024, ...opts })
const git = (args, opts) => run('git', args, opts)

// Big files that are allowed to be tracked (keep in sync with docs/SUBMISSION_CHECK.md).
const BIG_FILE_ALLOWLIST = [/^package-lock\.json$/, /^assets\/showtime\/clips\//, /^media\/.*\.(mp4|png)$/]

const tracked = git(['ls-files', '-z']).stdout.split('\0').filter(Boolean)

// 1. .env ignored + untracked
{
  const ignored = git(['check-ignore', '-q', '.env']).status === 0
  const isTracked = tracked.some((f) => f === '.env' || (/^\.env\./.test(f) && f !== '.env.example'))
  if (!existsSync('.env')) add('.env ignored and untracked', ignored && !isTracked ? 'PASS' : 'FAIL', '.env absent locally; ignored=' + ignored)
  else add('.env ignored and untracked', ignored && !isTracked ? 'PASS' : 'FAIL', `ignored=${ignored} tracked=${isTracked}`)
}

// 2. secrets in tracked files and history
{
  const values = []
  if (existsSync('.env')) {
    for (const line of readFileSync('.env', 'utf8').split('\n')) {
      const m = line.match(/^\s*(?:export\s+)?([A-Z0-9_]*(?:KEY|TOKEN|SECRET)[A-Z0-9_]*)\s*=\s*(.*)$/)
      if (!m) continue
      const v = m[2].trim().replace(/^['"]|['"]$/g, '')
      if (v.length >= 8) values.push(v)
    }
  }
  let treeHits = []
  let histHits = 0
  for (const v of values) {
    // -f /dev/stdin keeps the value out of argv/process list
    const t = git(['grep', '-l', '-F', '-f', '/dev/stdin', 'HEAD', '--'], { input: v + '\n' })
    const tw = git(['grep', '-l', '-F', '-f', '/dev/stdin', '--'], { input: v + '\n' }) // working tree tracked files
    for (const out of [t.stdout, tw.stdout]) for (const l of out.split('\n').filter(Boolean)) treeHits.push(l.replace(/^HEAD:/, ''))
    const h = git(['log', '--all', '--oneline', '-S' + v])
    histHits += h.stdout.split('\n').filter(Boolean).length
  }
  const shapes = [/AIza[0-9A-Za-z_-]{35}/, /\bsk-[A-Za-z0-9_-]{20,}/, /\bghp_[A-Za-z0-9]{30,}/, /-----BEGIN [A-Z ]*PRIVATE KEY-----/]
  const shapeHits = []
  for (const f of tracked) {
    try {
      if (!existsSync(f) || statSync(f).size > 2 * 1024 * 1024) continue
      const buf = readFileSync(f)
      if (buf.includes(0)) continue
      const s = buf.toString('utf8')
      if (shapes.some((r) => r.test(s))) shapeHits.push(f)
    } catch {}
  }
  treeHits = [...new Set(treeHits)]
  const bad = treeHits.length + histHits + shapeHits.length
  const note = values.length ? `${values.length} .env secret(s) checked` : 'no .env secrets to compare (shape scan only)'
  add(
    'No secrets in tracked files/history',
    bad ? 'FAIL' : values.length ? 'PASS' : 'WARN',
    bad ? `files: ${[...new Set([...treeHits, ...shapeHits])].slice(0, 6).join(', ')}; history commits: ${histHits}` : note,
  )
}

// 3. build dirs not tracked
{
  const bad = tracked.filter((f) => /^(node_modules|out|dist)\//.test(f))
  add('No node_modules/out/dist tracked', bad.length ? 'FAIL' : 'PASS', bad.length ? `${bad.length} files, e.g. ${bad[0]}` : '')
}

// 4. big files
{
  const big = []
  for (const f of tracked) {
    try {
      if (existsSync(f) && statSync(f).size > 2 * 1024 * 1024 && !BIG_FILE_ALLOWLIST.some((r) => r.test(f))) big.push(f)
    } catch {}
  }
  add('No tracked file >2 MB (allowlist aside)', big.length ? 'FAIL' : 'PASS', big.slice(0, 4).join(', '))
}

// 5. typecheck / tests / build
if (fast) {
  add('typecheck / tests / build', 'WARN', 'skipped (--fast)')
} else {
  for (const [name, cmd, args] of [
    ['npm run typecheck', 'npm', ['run', 'typecheck']],
    ['npx vitest run', 'npx', ['vitest', 'run']],
    ['npm run build', 'npm', ['run', 'build']],
  ]) {
    const r = run(cmd, args, { timeout: 8 * 60 * 1000 })
    const tail = (r.stdout + r.stderr).trim().split('\n').slice(-2).join(' | ').slice(0, 160)
    add(name, r.status === 0 ? 'PASS' : 'FAIL', r.status === 0 ? '' : tail)
  }
}

// 6. README sections
{
  const readme = existsSync('README.md') ? readFileSync('README.md', 'utf8') : ''
  const heads = readme.split('\n').filter((l) => /^#{1,3}\s/.test(l)).map((l) => l.toLowerCase())
  const need = {
    overview: /problem|what it does|overview|about/,
    'setup/quickstart': /quickstart|setup|install|getting started/,
    architecture: /architecture/,
    'trust/safety/privacy': /trust|safety|privacy|security/,
    limitations: /limitation/,
    'credits/licensing': /credit|licen|acknowledg/,
    team: /team/,
  }
  const missing = Object.entries(need).filter(([, re]) => !heads.some((h) => re.test(h))).map(([k]) => k)
  add('README required sections', missing.length ? 'FAIL' : 'PASS', missing.length ? 'missing: ' + missing.join(', ') : '')
}

// 7. LICENSE
{
  const lic = readdirSync('.').find((f) => /^licen[cs]e(\.|$)/i.test(f))
  add('LICENSE present', lic ? 'PASS' : 'WARN', lic ? lic : 'missing: TBD, user decides (README says MIT is simplest)')
}

// 8. THIRD_PARTY_NOTICES coverage of `Adapted from` files
{
  const g = git(['grep', '-l', '--untracked', 'Adapted from', '--', 'src', 'scripts', 'spikes', 'tools', 'apps'])
  const files = g.stdout.split('\n').filter(Boolean).filter((f) => f !== 'scripts/submit-check.mjs')
  const notices = existsSync('THIRD_PARTY_NOTICES.md') ? readFileSync('THIRD_PARTY_NOTICES.md', 'utf8') : ''
  const unlisted = files.filter((f) => !notices.includes(f) && !notices.includes(f.split('/').pop()))
  add(
    'THIRD_PARTY_NOTICES lists every `Adapted from` file',
    !notices ? 'FAIL' : unlisted.length ? 'FAIL' : 'PASS',
    unlisted.length ? `${unlisted.length} unlisted, e.g. ${unlisted.slice(0, 3).join(', ')}` : `${files.length} files`,
  )
  // upstream-level fallback: notices must at least name the upstream of each header
  void files
}

// 9. docs referenced by README exist
{
  const readme = existsSync('README.md') ? readFileSync('README.md', 'utf8') : ''
  const refs = new Set()
  for (const m of readme.matchAll(/\]\((?!https?:|#|mailto:)([^)\s#]+)/g)) refs.add(m[1])
  for (const m of readme.matchAll(/`((?:docs|scripts|assets|apps|fixtures|tests|src)\/[A-Za-z0-9_./-]+\.[A-Za-z0-9]+)`/g)) refs.add(m[1])
  const missing = [...refs].filter((p) => !existsSync(join(root, decodeURIComponent(p))))
  add('Docs/paths referenced by README exist', missing.length ? 'FAIL' : 'PASS', missing.length ? missing.slice(0, 5).join(', ') : `${refs.size} refs`)
}

// 10. repo visibility
{
  const r = run('gh', ['repo', 'view', '--json', 'visibility', '-q', '.visibility'], { timeout: 20000 })
  const vis = (r.stdout || '').trim()
  add('Repo visibility', r.status !== 0 ? 'WARN' : /public/i.test(vis) ? 'PASS' : 'WARN', r.status !== 0 ? 'gh unavailable or no remote' : /public/i.test(vis) ? 'PUBLIC' : `${vis}: user must decide before submit`)
}

// 11. stage assets + showtime clips
{
  const stage = ['apps/demo-stage/index.html', 'apps/demo-stage/stage.js', 'apps/demo-stage/stage.css', 'scripts/stage-server.mjs']
  const miss = stage.filter((f) => !existsSync(f))
  add('Demo stage present', miss.length ? 'FAIL' : 'PASS', miss.join(', '))
  const sc = existsSync('assets/showtime/script.json')
  const clips = existsSync('assets/showtime/clips') ? readdirSync('assets/showtime/clips').filter((f) => !f.startsWith('.')) : []
  add('Showtime script + clips', !sc ? 'FAIL' : clips.length ? 'PASS' : 'WARN', !sc ? 'assets/showtime/script.json missing' : clips.length ? `${clips.length} clips` : 'clips/ is empty')
}

// table
const icon = { PASS: '\x1b[32mPASS\x1b[0m', WARN: '\x1b[33mWARN\x1b[0m', FAIL: '\x1b[31mFAIL\x1b[0m' }
const w = Math.max(...rows.map((r) => r.name.length))
console.log(`\nSubmission check${fast ? ' (--fast)' : ''}\n`)
for (const r of rows) console.log(`${icon[r.status]}  ${r.name.padEnd(w)}  ${r.detail}`)
const n = (s) => rows.filter((r) => r.status === s).length
console.log(`\nPASS ${n('PASS')}  WARN ${n('WARN')}  FAIL ${n('FAIL')}`)
process.exit(n('FAIL') ? 1 : 0)
