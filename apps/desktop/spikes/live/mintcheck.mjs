// Bundles the real src/main/live-auth.ts and mints both tokens with the real key (never prints them).
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import dotenv from 'dotenv'
import { build } from 'esbuild'
const here = path.dirname(fileURLToPath(import.meta.url))
const repo = path.resolve(here, '../..')
dotenv.config({ path: path.join(repo, '.env'), quiet: true })
const outfile = path.join(here, 'out/live-auth.bundle.mjs')
await build({ entryPoints: [path.join(repo, 'src/main/live-auth.ts')], bundle: true, format: 'esm', platform: 'node', outfile, logLevel: 'error', packages: 'external', absWorkingDir: here, nodePaths: [path.join(here, 'node_modules')] })
const auth = await import(outfile)
for (const [name, fn] of [['live', auth.mintLiveToken], ['wake', auth.mintWakeToken]]) {
  const t = await fn()
  console.log(name, 'minted:', t.token.startsWith('auth_tokens/'), 'model', t.model, 'expiresInMin', Math.round((t.expiresAt - Date.now()) / 60000))
}
