// Who the events belong to. Local only: a stable random person id (never a name or an account) plus the role the worker picked
// in onboarding. UNDERSTUDY_PERSON / UNDERSTUDY_ROLE override; otherwise the id is generated once and kept in the user-data folder.
import { randomBytes } from 'node:crypto'
import fs from 'node:fs'
import path from 'node:path'
import { isPerson, isRole, type Identity } from './event'

export const DEFAULT_ROLE = 'benefits-processor' // the deep role pack; the dashboard's onboarding replaces it

export interface IdentityDeps {
  env?: Record<string, string | undefined>
  userDataDir: string | null
  readFile?: (file: string) => string
  writeFile?: (file: string, data: string) => void
}

export function newPersonId(bytes: Buffer = randomBytes(4)): string {
  return `p_${bytes.toString('hex')}`
}

export function loadIdentity(deps: IdentityDeps): Identity {
  const env = deps.env ?? process.env
  const file = deps.userDataDir ? path.join(deps.userDataDir, 'understudy-identity.json') : null
  const read = deps.readFile ?? ((f: string) => fs.readFileSync(f, 'utf8'))
  const write =
    deps.writeFile ??
    ((f: string, data: string) => {
      fs.mkdirSync(path.dirname(f), { recursive: true })
      fs.writeFileSync(f, data, { mode: 0o600 })
    })

  let saved: Partial<Identity> = {}
  if (file) {
    try {
      saved = JSON.parse(read(file)) as Partial<Identity>
    } catch {
      saved = {}
    }
  }
  const envPerson = (env.UNDERSTUDY_PERSON ?? '').trim()
  const envRole = (env.UNDERSTUDY_ROLE ?? '').trim()
  const person = isPerson(envPerson) ? envPerson : saved.person && isPerson(saved.person) ? saved.person : newPersonId()
  const role = isRole(envRole) ? envRole : saved.role && isRole(saved.role) ? saved.role : DEFAULT_ROLE
  if (file && (saved.person !== person || saved.role !== role) && !isPerson(envPerson)) {
    try {
      write(file, JSON.stringify({ person, role }))
    } catch {
      /* an unwritable folder only means a new id next run */
    }
  }
  return { person, role }
}

/** Reads `role:` from the memory file's front matter (the engine's GET /memory markdown). */
export function roleFromMemory(markdown: string): string | null {
  const m = /^---\s*\n([\s\S]*?)\n---/m.exec(markdown)
  if (!m) return null
  const line = /^role:\s*([a-z][a-z0-9-]{1,40})\s*$/m.exec(m[1])
  return line ? line[1] : null
}
