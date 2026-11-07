// False-positive surface of the matcher: which dictionary words would fire a persona after "hey"?
// Run `WAKE_COLLISIONS=1 npx vitest run tests/wake/collisions.test.ts` to print them (use it after renaming a persona).
import { existsSync, readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { PERSONA_LIST } from '../../src/shared/personas'
import { createWakeMatcher } from '../../src/renderer/wake/matcher'

const DICT = '/usr/share/dict/words'
const matcher = createWakeMatcher(PERSONA_LIST)

describe.skipIf(!existsSync(DICT))('dictionary collisions', () => {
  const words = existsSync(DICT) ? [...new Set(readFileSync(DICT, 'utf8').split('\n').map((w) => w.trim().toLowerCase()).filter((w) => /^[a-z]{3,}$/.test(w)))] : []
  const hits = words
    .map((w) => ({ w, m: matcher.match(`hey ${w}`) }))
    .filter((x) => x.m)
    .map((x) => `${x.w} -> ${x.m!.personaId} (${x.m!.score.toFixed(2)})`)

  it('prints the collision list when asked', () => {
    if (process.env.WAKE_COLLISIONS === '1') console.log(`[collisions] ${words.length} words scanned, ${hits.length} fire:\n${hits.join('\n')}`)
    // Obscure dictionary words ("amyl", "marquess") that an ASR would almost never emit after "hey"; guards against regressions.
    expect(hits.length).toBeLessThan(60)
  })

  it('none of the most common English words fires after "hey"', () => {
    const common = 'the be to of and a in that have i it for not on with he as you do at this but his by from they we say her she or an will my one all would there their what so up out if about who get which go me when make can like time no just him know take people into year your good some could them see other than then now look only come its over think also back after use two how our work first well way even new want because any these give day most us market marks mark marcus amelia america emily emilia marcia mercy mars march marble margin marry mary amy amelie camellia'.split(' ')
    const fired = common.filter((w) => matcher.match(`hey ${w}`) && !['marcus', 'amelia', 'emilia', 'amelie'].includes(w))
    expect(fired).toEqual([])
  })
})
