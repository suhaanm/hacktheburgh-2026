#!/usr/bin/env node
// Builds the local, UNSIGNED Knack.app and dmg into apps/desktop/dist-app (not committed). Run through the machine-wide slot:
//   cd apps/desktop && ../../scripts/heavy.sh npm run package
// Steps: the dashboard (apps/dashboard/dist), the desktop app (electron-vite), build/knack-config.json (where this repository is, so the built app can start the engine
// and the agent), then electron-builder with electron-builder.config.cjs. It never launches the app.
import { spawnSync } from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const here = path.dirname(fileURLToPath(import.meta.url))
const desktop = path.resolve(here, '..')
const repo = path.resolve(desktop, '../..')
const dashboard = path.join(repo, 'apps/dashboard')
const bin = (dir, name) => path.join(dir, 'node_modules/.bin', name)

function run(label, cmd, args, cwd, env = {}) {
  console.log(`\n== ${label}`)
  const r = spawnSync(cmd, args, { cwd, stdio: 'inherit', env: { ...process.env, ...env } })
  if (r.status !== 0) {
    console.error(`\n${label} failed (exit ${r.status}).`)
    process.exit(r.status ?? 1)
  }
}

if (!fs.existsSync(path.join(dashboard, 'node_modules'))) {
  console.error('apps/dashboard/node_modules is missing: run `npm install` in apps/dashboard first.')
  process.exit(1)
}
run('dashboard build (apps/dashboard/dist)', 'npm', ['run', 'build'], dashboard)
run('desktop build (out/)', bin(desktop, 'electron-vite'), ['build'], desktop)

// Where the repository is: this one, or the one named by KNACK_BAKE_REPO (a build made in a worktree for an app that should find the services of the main checkout).
// A copy of Knack.app moved to another Mac needs KNACK_REPO at run time instead.
const baked = process.env.KNACK_BAKE_REPO ? path.resolve(process.env.KNACK_BAKE_REPO) : repo
if (!fs.existsSync(path.join(baked, 'pyproject.toml'))) {
  console.error(`KNACK_BAKE_REPO is not a repository (no pyproject.toml in ${baked}).`)
  process.exit(1)
}
console.log(`the app will look for the engine and the agent in ${baked}`)
fs.mkdirSync(path.join(desktop, 'build'), { recursive: true })
fs.writeFileSync(path.join(desktop, 'build/knack-config.json'), JSON.stringify({ repo: baked }, null, 2) + '\n')

// The "Hey Knack" listener: compiled here, never run by this script (resources/knack-wake is not committed).
run('Hey Knack helper (compile only)', 'bash', ['scripts/build-wake-helper.sh'], desktop)
run('icons are current', 'node', ['scripts/make-icons.mjs'], desktop)
// CSC_IDENTITY_AUTO_DISCOVERY=false: never look for a signing identity in the keychain; the build is unsigned.
run('package (electron-builder, unsigned)', bin(desktop, 'electron-builder'), ['--mac', '--config', 'electron-builder.config.cjs', '--publish', 'never'], desktop, { CSC_IDENTITY_AUTO_DISCOVERY: 'false' })

const out = path.join(desktop, 'dist-app')
const du = (p) => spawnSync('du', ['-sh', p], { encoding: 'utf8' }).stdout.trim().split('\t')[0]
for (const entry of fs.readdirSync(out)) {
  const p = path.join(out, entry)
  if (/\.dmg$/.test(entry) || /^mac/.test(entry)) console.log(`${entry}: ${du(p)}`)
}
